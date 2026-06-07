"""Model deployment endpoints: import a bundle (USB), list, rollback, coverage."""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from ..db.models import Model, ModelDeployment, Roi, Surface
from ..db.repositories import ModelRepository, ProductRepository, RecipeRepository
from ..schemas.api import DeployBy
from ..sync.sync_client import SyncError
from .deps import get_ctx

router = APIRouter(tags=["models"])


@router.post("/models/import")
async def import_bundle(file: UploadFile = File(...), deployed_by: str = "operator",
                        ctx=Depends(get_ctx)) -> dict:
    """Import an ONNX model bundle ZIP (from USB) and activate it."""
    suffix = Path(file.filename or "bundle.zip").suffix or ".zip"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name
    try:
        return ctx.sync.import_bundle(tmp_path, deployed_by=deployed_by)
    except SyncError as exc:
        raise HTTPException(400, str(exc))
    finally:
        Path(tmp_path).unlink(missing_ok=True)


@router.get("/models")
def list_models(ctx=Depends(get_ctx)) -> list[dict]:
    """List the active model deployment per ROI across all products."""
    out = []
    with ctx.db.session() as s:
        deployments = ModelRepository(s).all_active_deployments()
        for dep in deployments:
            model = s.get(Model, dep.model_id)
            roi = s.get(Roi, dep.roi_id)
            surface = s.get(Surface, roi.surface_id) if roi else None
            recipe = RecipeRepository(s).get(surface.recipe_id) if surface else None
            product = ProductRepository(s).get(recipe.product_id) if recipe else None
            out.append({
                "roi_id": dep.roi_id,
                "roi_name": roi.name if roi else None,
                "surface_index": surface.surface_index if surface else None,
                "product": product.name if product else None,
                "product_status": product.status if product else None,
                "version": model.version if model else None,
                "checksum": model.checksum[:12] if model else None,
                "deployed_at": str(dep.deployed_at),
                "source": dep.source,
                "has_rollback": dep.previous_model_id is not None,
                "loaded": ctx.model_registry.has(dep.roi_id),
            })
    return out


@router.post("/models/rollback/{roi_id}")
def rollback(roi_id: int, payload: DeployBy | None = None, ctx=Depends(get_ctx)) -> dict:
    by = payload.deployed_by if payload else "operator"
    try:
        return ctx.sync.rollback_roi(roi_id, deployed_by=by)
    except SyncError as exc:
        raise HTTPException(400, str(exc))


@router.get("/models/coverage/{product_id}")
def coverage(product_id: int, ctx=Depends(get_ctx)) -> dict:
    """Report which ROIs of a product's active recipe have a deployed model."""
    with ctx.db.session() as s:
        recipe = RecipeRepository(s).active_for_product(product_id)
        if not recipe:
            raise HTTPException(404, "no active recipe")
        models = ModelRepository(s)
        rois = []
        covered = 0
        total = 0
        for surface in recipe.surfaces:
            for roi in surface.rois:
                total += 1
                has_model = models.active_model(roi.id) is not None
                covered += 1 if has_model else 0
                rois.append({
                    "roi_id": roi.id, "surface_index": surface.surface_index,
                    "roi_index": roi.roi_index, "name": roi.name, "has_model": has_model,
                })
    return {"product_id": product_id, "covered": covered, "total": total,
            "ready": covered == total and total > 0, "rois": rois}
