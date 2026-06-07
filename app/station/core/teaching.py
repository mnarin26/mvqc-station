"""Teaching service: EMPTY/FILLED/defect auto-capture for a surface."""

from __future__ import annotations

import itertools
import json
import logging
import time
from datetime import datetime
from typing import Dict, List, Set

from sqlalchemy import func, select

from ..camera.base import encode_jpeg
from ..db.models import TeachingSample, TeachingSession
from ..db.repositories import (
    ProductRepository,
    RoiRepository,
    SurfaceRepository,
    TeachingRepository,
)
from ..inference.preprocess import crop_roi

logger = logging.getLogger(__name__)

_BASE_LABELS = {"EMPTY", "FILLED"}


class TeachingService:
    def __init__(self, ctx) -> None:
        self.ctx = ctx
        self.settings = ctx.settings
        self.db = ctx.db
        self.storage = ctx.storage
        self.camera = ctx.camera
        self.lighting = ctx.lighting
        self.event_bus = ctx.event_bus
        self.loop = ctx.loop

    def _emit(self, event_type: str, payload: dict) -> None:
        if self.event_bus and self.loop:
            self.event_bus.publish_threadsafe(self.loop, event_type, payload)

    def snapshot(self) -> Dict:
        """Capture a single frame for ROI drawing in the HMI."""
        import base64

        frame = self.camera.capture()
        h, w = frame.shape[:2]
        b64 = base64.b64encode(encode_jpeg(frame, quality=90)).decode("ascii")
        return {"image": f"data:image/jpeg;base64,{b64}", "width": w, "height": h}

    def _defect_labels_for_roi(self, roi) -> Set[str]:
        labels: Set[str] = set()
        if not roi.params:
            return labels
        try:
            params = json.loads(roi.params)
        except json.JSONDecodeError:
            return labels
        for d in params.get("defects") or []:
            lbl = str(d.get("label", "")).strip().upper()
            if lbl:
                labels.add(lbl)
        return labels

    def _labels_for_roi(self, roi) -> Set[str]:
        """Labels teachable on a single ROI (EMPTY/FILLED + its own defects)."""
        return _BASE_LABELS | self._defect_labels_for_roi(roi)

    def _surface_allowed_labels(self, rois) -> Set[str]:
        """Union of all labels any ROI on this surface can be taught."""
        labels = set(_BASE_LABELS)
        for roi in rois:
            labels |= self._defect_labels_for_roi(roi)
        return labels

    def _rois_for_label(self, rois, label: str) -> List:
        """EMPTY/FILLED -> every ROI; defect labels -> only ROIs that define them."""
        if label in _BASE_LABELS:
            return list(rois)
        matched = [r for r in rois if label in self._defect_labels_for_roi(r)]
        if not matched:
            raise ValueError(
                f"label '{label}' is not defined on any ROI "
                f"(add it under that ROI's defect classes and Save ROIs)"
            )
        return matched

    def capture(self, surface_id: int, label: str, frames: int | None = None) -> Dict:
        label = label.strip().upper()
        if not label:
            raise ValueError("label is required")
        frames = frames or self.settings.teaching.frames_per_label

        with self.db.session() as s:
            surface = SurfaceRepository(s).with_rois(surface_id)
            if not surface:
                raise ValueError("surface not found")
            rois = RoiRepository(s).for_surface(surface_id)
            if not rois:
                raise ValueError("define ROIs before teaching")
            allowed = self._surface_allowed_labels(rois)
            if label not in allowed:
                raise ValueError(
                    f"label '{label}' is not defined for this surface "
                    f"(allowed: {', '.join(sorted(allowed))})"
                )
            target_rois = self._rois_for_label(rois, label)
            all_roi_indices = [r.roi_index for r in rois]
            recipe = surface.recipe
            product = ProductRepository(s).get(recipe.product_id)
            product_name = product.name
            surface_index = surface.surface_index
            roi_defs = [
                {"id": r.id, "roi_index": r.roi_index, "geometry": json.loads(r.geometry)}
                for r in target_rois
            ]
            session = TeachingRepository(s).create_session(surface_id, label)
            session_id = session.id

        exposures = self.settings.teaching.exposure_sweep or [0.0]
        gains = self.settings.teaching.gain_sweep or [1.0]
        if self.settings.teaching.condition_sweep:
            sweep = list(itertools.product(exposures, gains))
        else:
            sweep = [(self.settings.camera.exposure_default, self.settings.camera.gain_default)]

        settle_s = 0.12 if not self.settings.teaching.condition_sweep else 0.04
        # Report counts for all surface ROIs; only targets are incremented.
        samples_per_roi: Dict[str, int] = {f"roi_{idx}": 0 for idx in all_roi_indices}
        captured = 0

        try:
            if self.lighting:
                self.lighting.on()
            for i in range(frames):
                exposure, gain = sweep[i % len(sweep)]
                try:
                    self.camera.set_exposure(exposure)
                    self.camera.set_gain(gain)
                    if self.lighting and self.settings.teaching.condition_sweep:
                        self.lighting.set_level(0.6 + 0.4 * ((i % 3) / 2.0))
                except Exception:
                    logger.debug("control set unsupported", exc_info=True)
                time.sleep(settle_s)
                frame = self.camera.capture()
                ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                for r in roi_defs:
                    crop = crop_roi(frame, r["geometry"])
                    roi_dir = self.storage.teaching_roi_dir(
                        product_name, surface_index, label, r["roi_index"]
                    )
                    img_path = roi_dir / f"{ts}_{i:03d}.jpg"
                    self.storage.write_bytes(img_path, encode_jpeg(crop))
                    with self.db.session() as s:
                        TeachingRepository(s).add_sample(
                            session_id=session_id, roi_id=r["id"], label=label,
                            image_path=str(img_path), exposure=float(exposure),
                            gain=float(gain), lighting=str(self.lighting.level) if self.lighting else None,
                        )
                    samples_per_roi[f"roi_{r['roi_index']}"] += 1
                captured += 1
                self._emit("teaching_progress", {
                    "surface_id": surface_id, "label": label,
                    "frame": i + 1, "frames": frames,
                })
            with self.db.session() as s:
                TeachingRepository(s).complete_session(session_id)
        finally:
            try:
                self.camera.reset_controls()
            except Exception:
                pass
            self._mark_teaching(surface_id)

        return {
            "session_id": session_id,
            "label": label,
            "frames_captured": captured,
            "target_rois": [r["roi_index"] for r in roi_defs],
            "samples_per_roi": samples_per_roi,
        }

    def status(self, surface_id: int) -> Dict:
        with self.db.session() as s:
            rows = s.execute(
                select(TeachingSample.label, func.count(TeachingSample.id))
                .join(TeachingSession, TeachingSample.session_id == TeachingSession.id)
                .where(TeachingSession.surface_id == surface_id)
                .group_by(TeachingSample.label)
            ).all()
        out: Dict = {"surface_id": surface_id, "EMPTY": 0, "FILLED": 0}
        for label, cnt in rows:
            out[str(label).upper()] = int(cnt)
        return out

    def _mark_teaching(self, surface_id: int) -> None:
        from ..db.models import Recipe, Surface

        with self.db.session() as s:
            surface = s.get(Surface, surface_id)
            if not surface:
                return
            recipe = s.get(Recipe, surface.recipe_id)
            if recipe:
                ProductRepository(s).set_status(recipe.product_id, "teaching")
