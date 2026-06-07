"""Repository helpers encapsulating common queries and write patterns.

Each repository is constructed with an open SQLAlchemy ``Session`` and performs
no transaction control itself; callers use ``Database.session()`` for that.
"""

from __future__ import annotations

import json
from typing import Iterable, List, Optional

from sqlalchemy import delete, desc, func, select
from sqlalchemy.orm import Session, selectinload

from .models import (
    AuditLog,
    Export,
    Inspection,
    InspectionCycle,
    InspectionRoiResult,
    Model,
    ModelDeployment,
    Product,
    Recipe,
    Roi,
    Setting,
    Surface,
    TeachingSample,
    TeachingSession,
)


class ProductRepository:
    def __init__(self, session: Session) -> None:
        self.s = session

    def create(self, name: str, barcode: Optional[str], surface_count: int) -> Product:
        product = Product(name=name, barcode=barcode, surface_count=surface_count)
        self.s.add(product)
        self.s.flush()
        return product

    def get(self, product_id: int) -> Optional[Product]:
        return self.s.get(Product, product_id)

    def by_barcode(self, barcode: str) -> Optional[Product]:
        return self.s.scalar(select(Product).where(Product.barcode == barcode))

    def by_name(self, name: str) -> Optional[Product]:
        return self.s.scalar(select(Product).where(Product.name == name))

    def list(self) -> List[Product]:
        return list(self.s.scalars(select(Product).order_by(Product.name)))

    def set_status(self, product_id: int, status: str) -> None:
        product = self.s.get(Product, product_id)
        if product:
            product.status = status
            product.updated_at = func.datetime("now")


class RecipeRepository:
    def __init__(self, session: Session) -> None:
        self.s = session

    def create_version(self, product_id: int, pass_rule: str = "all_filled") -> Recipe:
        """Create the next recipe version for a product (inactive by default)."""
        max_version = self.s.scalar(
            select(func.max(Recipe.version)).where(Recipe.product_id == product_id)
        )
        recipe = Recipe(
            product_id=product_id,
            version=(max_version or 0) + 1,
            is_active=0,
            pass_rule=pass_rule,
        )
        self.s.add(recipe)
        self.s.flush()
        return recipe

    def get(self, recipe_id: int) -> Optional[Recipe]:
        return self.s.get(Recipe, recipe_id)

    def get_full(self, recipe_id: int) -> Optional[Recipe]:
        """Recipe with surfaces and ROIs eagerly loaded."""
        return self.s.scalar(
            select(Recipe)
            .options(selectinload(Recipe.surfaces).selectinload(Surface.rois))
            .where(Recipe.id == recipe_id)
        )

    def active_for_product(self, product_id: int) -> Optional[Recipe]:
        return self.s.scalar(
            select(Recipe)
            .options(selectinload(Recipe.surfaces).selectinload(Surface.rois))
            .where(Recipe.product_id == product_id, Recipe.is_active == 1)
        )

    def list_for_product(self, product_id: int) -> List[Recipe]:
        return list(
            self.s.scalars(
                select(Recipe)
                .where(Recipe.product_id == product_id)
                .order_by(desc(Recipe.version))
            )
        )

    def activate(self, recipe_id: int) -> None:
        """Make this recipe the single active version for its product."""
        recipe = self.s.get(Recipe, recipe_id)
        if not recipe:
            raise ValueError(f"recipe {recipe_id} not found")
        for other in self.s.scalars(
            select(Recipe).where(Recipe.product_id == recipe.product_id)
        ):
            other.is_active = 1 if other.id == recipe_id else 0


class SurfaceRepository:
    def __init__(self, session: Session) -> None:
        self.s = session

    def create(self, recipe_id: int, surface_index: int, name: Optional[str] = None) -> Surface:
        surface = Surface(recipe_id=recipe_id, surface_index=surface_index, name=name)
        self.s.add(surface)
        self.s.flush()
        return surface

    def get(self, surface_id: int) -> Optional[Surface]:
        return self.s.get(Surface, surface_id)

    def with_rois(self, surface_id: int) -> Optional[Surface]:
        return self.s.scalar(
            select(Surface).options(selectinload(Surface.rois)).where(Surface.id == surface_id)
        )

    def set_reference(self, surface_id: int, path: str, capture_settings: dict | None = None) -> None:
        surface = self.s.get(Surface, surface_id)
        if surface:
            surface.reference_image_path = path
            if capture_settings is not None:
                surface.capture_settings = json.dumps(capture_settings)


class RoiRepository:
    def __init__(self, session: Session) -> None:
        self.s = session

    def replace_for_surface(self, surface_id: int, rois: Iterable[dict]) -> List[Roi]:
        """Sync a surface's ROIs to the provided definitions via an in-place diff.

        Existing ROI rows are matched (by ``id`` when supplied, otherwise by
        ``roi_index``) and updated in place so their primary keys survive. This
        keeps trained models, deployments, teaching samples and inspection
        history linked to the same ROI when adding/editing on an already-active
        product — the previous "delete all, recreate" approach raised a 500
        (inspection_roi_results.roi_id has no ON DELETE CASCADE) and silently
        cascaded away deployed models. ROIs absent from the payload are removed;
        their inspection-result rows are cleared first because that FK does not
        cascade.
        """
        payload = list(rois)
        existing = list(self.s.scalars(select(Roi).where(Roi.surface_id == surface_id)))
        by_id = {r.id: r for r in existing}
        by_index = {r.roi_index: r for r in existing}

        # Resolve each payload entry to an existing ROI (match) or None (new).
        plan: List[tuple] = []  # (matched_roi_or_None, target_index, data)
        claimed: set[int] = set()
        for i, r in enumerate(payload, start=1):
            target_index = r.get("roi_index") or i
            match = None
            rid = r.get("id")
            if rid is not None and rid in by_id and rid not in claimed:
                match = by_id[rid]
            elif rid is None and target_index in by_index and by_index[target_index].id not in claimed:
                match = by_index[target_index]
            if match is not None:
                claimed.add(match.id)
            plan.append((match, target_index, r))

        # Remove ROIs no longer present. Clear dependent inspection results first
        # (inspection_roi_results.roi_id is NO ACTION); models/deployments/teaching
        # samples cascade at the DB level.
        for roi in existing:
            if roi.id not in claimed:
                self.s.execute(
                    delete(InspectionRoiResult).where(InspectionRoiResult.roi_id == roi.id)
                )
                self.s.delete(roi)
        self.s.flush()

        # Vacate indices of kept rows to placeholder negatives so reassigning
        # final indices can't transiently violate UNIQUE(surface_id, roi_index).
        for roi in existing:
            if roi.id in claimed:
                roi.roi_index = -roi.id
        self.s.flush()

        result: List[Roi] = []
        for match, target_index, r in plan:
            roi = match
            if roi is None:
                roi = Roi(surface_id=surface_id, roi_index=target_index)
                self.s.add(roi)
            else:
                roi.roi_index = target_index
            roi.name = r.get("name")
            roi.inspector_type = r.get("inspector_type", "presence")
            roi.geometry = json.dumps(r["geometry"])
            roi.params = json.dumps(r["params"]) if r.get("params") is not None else None
            roi.threshold = float(r.get("threshold", 0.5))
            result.append(roi)
        self.s.flush()
        return result

    def get(self, roi_id: int) -> Optional[Roi]:
        return self.s.get(Roi, roi_id)

    def for_surface(self, surface_id: int) -> List[Roi]:
        return list(
            self.s.scalars(
                select(Roi).where(Roi.surface_id == surface_id).order_by(Roi.roi_index)
            )
        )


class ModelRepository:
    def __init__(self, session: Session) -> None:
        self.s = session

    def add_model(self, **kwargs) -> Model:
        model = Model(**kwargs)
        self.s.add(model)
        self.s.flush()
        return model

    def active_deployment(self, roi_id: int) -> Optional[ModelDeployment]:
        return self.s.scalar(
            select(ModelDeployment)
            .where(ModelDeployment.roi_id == roi_id, ModelDeployment.is_active == 1)
            .order_by(desc(ModelDeployment.deployed_at))
        )

    def active_model(self, roi_id: int) -> Optional[Model]:
        dep = self.active_deployment(roi_id)
        return self.s.get(Model, dep.model_id) if dep else None

    def all_active_deployments(self) -> List[ModelDeployment]:
        return list(
            self.s.scalars(select(ModelDeployment).where(ModelDeployment.is_active == 1))
        )

    def deploy(self, roi_id: int, model_id: int, source: str, deployed_by: Optional[str]) -> ModelDeployment:
        """Atomically activate a model for a ROI, keeping the previous for rollback."""
        previous = self.active_deployment(roi_id)
        if previous:
            previous.is_active = 0
        deployment = ModelDeployment(
            roi_id=roi_id,
            model_id=model_id,
            is_active=1,
            source=source,
            deployed_by=deployed_by,
            previous_model_id=previous.model_id if previous else None,
        )
        self.s.add(deployment)
        self.s.flush()
        return deployment

    def rollback(self, roi_id: int, deployed_by: Optional[str]) -> Optional[ModelDeployment]:
        current = self.active_deployment(roi_id)
        if not current or current.previous_model_id is None:
            return None
        current.is_active = 0
        deployment = ModelDeployment(
            roi_id=roi_id,
            model_id=current.previous_model_id,
            is_active=1,
            source="rollback",
            deployed_by=deployed_by,
            previous_model_id=current.model_id,
        )
        self.s.add(deployment)
        self.s.flush()
        return deployment


class TeachingRepository:
    def __init__(self, session: Session) -> None:
        self.s = session

    def create_session(self, surface_id: int, label: str) -> TeachingSession:
        session = TeachingSession(surface_id=surface_id, label=label, status="capturing")
        self.s.add(session)
        self.s.flush()
        return session

    def add_sample(self, **kwargs) -> TeachingSample:
        sample = TeachingSample(**kwargs)
        self.s.add(sample)
        self.s.flush()
        return sample

    def complete_session(self, session_id: int) -> None:
        session = self.s.get(TeachingSession, session_id)
        if session:
            session.status = "complete"

    def count_samples(self, surface_id: int, label: str) -> int:
        return (
            self.s.scalar(
                select(func.count(TeachingSample.id))
                .join(TeachingSession, TeachingSample.session_id == TeachingSession.id)
                .where(TeachingSession.surface_id == surface_id, TeachingSample.label == label)
            )
            or 0
        )


class InspectionRepository:
    def __init__(self, session: Session) -> None:
        self.s = session

    def create_cycle(self, **kwargs) -> InspectionCycle:
        cycle = InspectionCycle(**kwargs)
        self.s.add(cycle)
        self.s.flush()
        return cycle

    def finish_cycle(self, cycle_id: int, result: str) -> None:
        cycle = self.s.get(InspectionCycle, cycle_id)
        if cycle:
            cycle.result = result
            cycle.finished_at = func.datetime("now")

    def add_inspection(self, **kwargs) -> Inspection:
        inspection = Inspection(**kwargs)
        self.s.add(inspection)
        self.s.flush()
        return inspection

    def add_roi_result(self, **kwargs) -> InspectionRoiResult:
        result = InspectionRoiResult(**kwargs)
        self.s.add(result)
        self.s.flush()
        return result

    def recent(self, limit: int = 50) -> List[Inspection]:
        return list(
            self.s.scalars(
                select(Inspection).order_by(desc(Inspection.id)).limit(limit)
            )
        )

    def stats(self) -> dict:
        total = self.s.scalar(select(func.count(Inspection.id))) or 0
        fails = self.s.scalar(
            select(func.count(Inspection.id)).where(Inspection.result == "FAIL")
        ) or 0
        saved = self.s.scalar(
            select(func.count(Inspection.id)).where(Inspection.saved == 1)
        ) or 0
        passes = total - fails
        return {
            "total": total,
            "pass": passes,
            "fail": fails,
            "saved": saved,
            "pass_rate": (passes / total) if total else 0.0,
        }


class ExportRepository:
    def __init__(self, session: Session) -> None:
        self.s = session

    def upsert(self, export_date: str, zip_path: str) -> Export:
        existing = self.s.scalar(select(Export).where(Export.export_date == export_date))
        if existing:
            existing.zip_path = zip_path
            existing.status = "pending"
            return existing
        export = Export(export_date=export_date, zip_path=zip_path, status="pending")
        self.s.add(export)
        self.s.flush()
        return export

    def mark(self, export_date: str, status: str, size_bytes: int | None = None,
             item_count: int | None = None) -> None:
        export = self.s.scalar(select(Export).where(Export.export_date == export_date))
        if export:
            export.status = status
            if size_bytes is not None:
                export.size_bytes = size_bytes
            if item_count is not None:
                export.item_count = item_count

    def list(self, limit: int = 60) -> List[Export]:
        return list(
            self.s.scalars(select(Export).order_by(desc(Export.export_date)).limit(limit))
        )


class SettingsRepository:
    def __init__(self, session: Session) -> None:
        self.s = session

    def all(self) -> dict:
        return {row.key: row.value for row in self.s.scalars(select(Setting))}

    def set(self, key: str, value: str) -> None:
        row = self.s.get(Setting, key)
        if row:
            row.value = value
        else:
            self.s.add(Setting(key=key, value=value))

    def delete(self, key: str) -> None:
        row = self.s.get(Setting, key)
        if row:
            self.s.delete(row)


def write_audit(session: Session, level: str, category: str, message: str,
                payload: dict | None = None) -> None:
    session.add(
        AuditLog(
            level=level,
            category=category,
            message=message,
            payload=json.dumps(payload) if payload else None,
        )
    )
