"""Inspection engine: orchestrates a full OK/NOK cycle.

Flow: resolve product (barcode/id) -> load active recipe + models -> per surface
capture -> crop ROIs -> inspect (presence) -> aggregate PASS/FAIL -> persist ->
apply data-collection policy -> archive -> stream results to the HMI.

``run_cycle`` is synchronous and CPU-bound; call it from a threadpool in the API
layer. Events are published to the async event bus in a thread-safe way.
"""

from __future__ import annotations

import base64
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional

from ..camera.base import encode_jpeg
from ..data_collection.archiver import ResultArchiver
from ..data_collection.policy import DataCollectionPolicy
from ..db.repositories import (
    InspectionRepository,
    ProductRepository,
    RecipeRepository,
    write_audit,
)
from ..decision.rules import aggregate_surface
from ..inference.preprocess import crop_roi
from ..inspectors import get_inspector
from .geometry import normalize_geometry_dict
from .overlay import draw_overlay

logger = logging.getLogger(__name__)


class EngineError(RuntimeError):
    pass


class ProductNotReadyError(EngineError):
    pass


class InspectionEngine:
    def __init__(self, ctx) -> None:
        self.ctx = ctx
        self.settings = ctx.settings
        self.db = ctx.db
        self.storage = ctx.storage
        self.camera = ctx.camera
        self.lighting = ctx.lighting
        self.model_registry = ctx.model_registry
        self.event_bus = ctx.event_bus
        self.loop = ctx.loop
        self.policy = DataCollectionPolicy(self.db)
        self.archiver = ResultArchiver(self.settings, self.storage)

    # ----------------------------------------------------------------- events
    def _emit(self, event_type: str, payload: dict) -> None:
        if self.event_bus and self.loop:
            self.event_bus.publish_threadsafe(self.loop, event_type, payload)

    # ------------------------------------------------------------- resolution
    def _resolve_recipe(self, s, barcode: Optional[str], product_id: Optional[int]):
        products = ProductRepository(s)
        if product_id is not None:
            product = products.get(product_id)
        elif barcode:
            product = products.by_barcode(barcode)
        else:
            raise EngineError("either barcode or product_id is required")
        if not product:
            raise EngineError("product not found for the given barcode/id")

        recipe = RecipeRepository(s).active_for_product(product.id)
        if not recipe:
            raise ProductNotReadyError(f"product '{product.name}' has no active recipe")
        return product, recipe

    def _check_models(self, recipe) -> List[int]:
        """Return ROI ids missing a deployed model."""
        missing = []
        for surface in recipe.surfaces:
            for roi in surface.rois:
                if roi.inspector_type == "presence" and not self.model_registry.has(roi.id):
                    missing.append(roi.id)
        return missing

    # ----------------------------------------------------------------- cycle
    def run_cycle(self, *, barcode: Optional[str] = None, product_id: Optional[int] = None,
                  surface_index: Optional[int] = None, operator: Optional[str] = None) -> Dict:
        with self.db.session() as s:
            product, recipe = self._resolve_recipe(s, barcode, product_id)
            # Detach the data we need (ids/geometry) before the session closes.
            product_id = product.id
            product_name = product.name
            product_barcode = product.barcode
            recipe_id = recipe.id
            recipe_version = recipe.version
            pass_rule = recipe.pass_rule
            surfaces_data = []
            for surface in sorted(recipe.surfaces, key=lambda x: x.surface_index):
                if surface_index is not None and surface.surface_index != surface_index:
                    continue
                rois = []
                for roi in sorted(surface.rois, key=lambda r: r.roi_index):
                    rois.append({
                        "id": roi.id,
                        "name": roi.name,
                        "roi_index": roi.roi_index,
                        "inspector_type": roi.inspector_type,
                        "geometry": normalize_geometry_dict(json.loads(roi.geometry)),
                        "params": json.loads(roi.params) if roi.params else None,
                        "threshold": roi.threshold,
                    })
                surfaces_data.append({
                    "id": surface.id,
                    "surface_index": surface.surface_index,
                    "name": surface.name,
                    "rois": rois,
                })

            missing = self._check_models(recipe)
            if missing:
                raise ProductNotReadyError(
                    f"product '{product_name}' missing models for ROIs {missing}; "
                    "train and deploy first"
                )

        self._emit("scan", {"barcode": barcode, "product": product_name})
        self._emit("recipe_loaded", {
            "product": product_name,
            "recipe_version": recipe_version,
            "surfaces": [sd["surface_index"] for sd in surfaces_data],
        })

        # Persist a cycle, then inspect each surface.
        with self.db.session() as s:
            cycle = InspectionRepository(s).create_cycle(
                product_id=product_id, recipe_id=recipe_id, barcode=barcode or product_barcode,
                operator=operator, station_id=self.settings.station_id,
            )
            cycle_id = cycle.id

        surface_results = []
        any_fail = False
        for sd in surfaces_data:
            result = self._inspect_surface(
                cycle_id=cycle_id, product_name=product_name, barcode=barcode or product_barcode,
                recipe_version=recipe_version, pass_rule=pass_rule, surface=sd,
            )
            surface_results.append(result)
            any_fail = any_fail or (result["result"] == "FAIL")

        overall = "FAIL" if any_fail else "PASS"
        with self.db.session() as s:
            InspectionRepository(s).finish_cycle(cycle_id, overall)
            write_audit(s, "INFO", "inspection",
                        f"cycle {cycle_id} {overall}",
                        {"product": product_name, "barcode": barcode})

        self._emit("result", {"cycle_id": cycle_id, "result": overall, "product": product_name})

        return {
            "cycle_id": cycle_id,
            "product": product_name,
            "barcode": barcode or product_barcode,
            "result": overall,
            "surfaces": surface_results,
        }

    def _inspect_surface(self, *, cycle_id: int, product_name: str, barcode: Optional[str],
                         recipe_version: int, pass_rule: str, surface: Dict) -> Dict:
        when = datetime.now()
        if self.lighting:
            self.lighting.on()
        frame = self.camera.capture()

        roi_outcomes: List[Dict] = []
        roi_crops = []
        for roi in surface["rois"]:
            crop = crop_roi(frame, roi["geometry"])
            roi_crops.append(crop)
            inspector = get_inspector(roi["inspector_type"])
            classifier = self.model_registry.get(roi["id"])
            outcome = inspector.inspect(
                crop, threshold=roi["threshold"], classifier=classifier,
                params=roi["params"], positive_class=self.settings.inference.positive_class,
            )
            severity = outcome.detail.get("severity", "ok")
            roi_outcomes.append({
                "roi_id": roi["id"],
                "roi_index": roi["roi_index"],
                "name": roi["name"],
                "geometry": roi["geometry"],
                "label": outcome.label,
                "confidence": outcome.confidence,
                "decision": outcome.decision,
                "severity": severity,
                "model_version": self.model_registry.version_for(roi["id"]),
            })
            self._emit("roi_result", {
                "surface_index": surface["surface_index"],
                "roi_index": roi["roi_index"],
                "name": roi["name"],
                "label": outcome.label,
                "confidence": round(outcome.confidence, 4),
                "decision": outcome.decision,
                "severity": severity,
            })

        decision = aggregate_surface(roi_outcomes, pass_rule)
        annotated = draw_overlay(frame, roi_outcomes)

        # Persist inspection + ROI results.
        with self.db.session() as s:
            repo = InspectionRepository(s)
            inspection = repo.add_inspection(
                cycle_id=cycle_id, surface_id=surface["id"],
                surface_index=surface["surface_index"], result=decision.result,
                overall_confidence=decision.overall_confidence,
            )
            inspection_id = inspection.id
            for o in roi_outcomes:
                repo.add_roi_result(
                    inspection_id=inspection_id, roi_id=o["roi_id"], roi_name=o["name"],
                    predicted_label=o["label"], confidence=o["confidence"],
                    decision=o["decision"], severity=o.get("severity", "ok"),
                )

        # Data-collection policy + archiving.
        save = self.policy.decide(decision.result, decision.overall_confidence)
        full_image_path = None
        roi_archive_dir = None
        if save.save:
            try:
                paths = self.archiver.archive(
                    inspection_id=inspection_id, product_name=product_name, barcode=barcode,
                    surface_index=surface["surface_index"], result=decision.result,
                    overall_confidence=decision.overall_confidence, saved_reason=save.reason,
                    recipe_version=recipe_version, roi_crops=roi_crops,
                    roi_outcomes=roi_outcomes, full_image=annotated,
                    save_full_image=save.save_full_image, when=when,
                )
                full_image_path = paths.get("full_image_path")
                roi_archive_dir = paths.get("roi_archive_dir")
                self._persist_save_meta(inspection_id, save.reason, full_image_path,
                                        roi_archive_dir, roi_outcomes)
            except Exception as exc:  # storage unavailable etc.
                logger.error("archive failed for inspection %s: %s", inspection_id, exc)
                self._emit("archive_error", {"inspection_id": inspection_id, "error": str(exc)})

        annotated_b64 = base64.b64encode(encode_jpeg(annotated)).decode("ascii")
        result = {
            "inspection_id": inspection_id,
            "surface_index": surface["surface_index"],
            "result": decision.result,
            "overall_confidence": decision.overall_confidence,
            "full_image_path": full_image_path,
            "saved": save.save,
            "saved_reason": save.reason,
            "roi_results": [
                {
                    "roi_id": o["roi_id"], "roi_index": o["roi_index"], "name": o["name"],
                    "label": o["label"], "confidence": round(o["confidence"], 4),
                    "decision": o["decision"], "severity": o.get("severity", "ok"),
                    "geometry": o["geometry"],
                }
                for o in roi_outcomes
            ],
            "annotated_image": f"data:image/jpeg;base64,{annotated_b64}",
        }
        self._emit("surface_result", {
            "inspection_id": inspection_id,
            "surface_index": surface["surface_index"],
            "result": decision.result,
            "overall_confidence": decision.overall_confidence,
            "failed_rois": decision.failed_roi_indices,
            "warning_rois": decision.warning_roi_indices,
        })
        return result

    def _persist_save_meta(self, inspection_id, reason, full_image_path, roi_archive_dir,
                           roi_outcomes) -> None:
        from ..db.models import Inspection, InspectionRoiResult

        with self.db.session() as s:
            inspection = s.get(Inspection, inspection_id)
            if inspection:
                inspection.saved = 1
                inspection.saved_reason = reason
                inspection.full_image_path = full_image_path
                inspection.roi_archive_dir = roi_archive_dir
            # Attach ROI crop paths back to the result rows (best effort).
            results = (
                s.query(InspectionRoiResult)
                .filter(InspectionRoiResult.inspection_id == inspection_id)
                .order_by(InspectionRoiResult.id)
                .all()
            )
            for i, row in enumerate(results, start=1):
                if roi_archive_dir:
                    row.roi_image_path = f"{roi_archive_dir}/roi_{i}.jpg"

    # ---------------------------------------------------------------- preview
    def preview_jpeg(self) -> bytes:
        """One annotated-free preview frame for the MJPEG stream."""
        return encode_jpeg(self.camera.capture())
