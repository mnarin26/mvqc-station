"""Recipe + surface + ROI endpoints: read full recipe, edit ROIs, version and
activate."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException

from ..db.repositories import (
    ProductRepository,
    RecipeRepository,
    RoiRepository,
    SurfaceRepository,
)
from ..schemas.api import SurfaceRoisInput
from ..schemas.recipe import Geometry, RecipeSchema, RoiSchema, SurfaceSchema
from .deps import get_ctx

router = APIRouter(tags=["recipes"])


def serialize_recipe(recipe, product) -> RecipeSchema:
    surfaces = []
    for surface in sorted(recipe.surfaces, key=lambda s: s.surface_index):
        rois = []
        for roi in sorted(surface.rois, key=lambda r: r.roi_index):
            rois.append(
                RoiSchema(
                    id=roi.id,
                    name=roi.name,
                    roi_index=roi.roi_index,
                    inspector_type=roi.inspector_type,
                    geometry=Geometry(**json.loads(roi.geometry)),
                    params=json.loads(roi.params) if roi.params else None,
                    threshold=roi.threshold,
                )
            )
        surfaces.append(
            SurfaceSchema(
                id=surface.id,
                surface_index=surface.surface_index,
                name=surface.name,
                reference_image_path=surface.reference_image_path,
                capture_settings=json.loads(surface.capture_settings)
                if surface.capture_settings
                else None,
                rois=rois,
            )
        )
    return RecipeSchema(
        id=recipe.id,
        product_id=recipe.product_id,
        product_name=product.name if product else None,
        version=recipe.version,
        is_active=bool(recipe.is_active),
        pass_rule=recipe.pass_rule,
        surfaces=surfaces,
    )


@router.get("/recipes/{recipe_id}", response_model=RecipeSchema)
def get_recipe(recipe_id: int, ctx=Depends(get_ctx)) -> RecipeSchema:
    with ctx.db.session() as s:
        recipe = RecipeRepository(s).get_full(recipe_id)
        if not recipe:
            raise HTTPException(404, "recipe not found")
        product = ProductRepository(s).get(recipe.product_id)
        return serialize_recipe(recipe, product)


@router.get("/products/{product_id}/recipes", response_model=list[dict])
def list_recipes(product_id: int, ctx=Depends(get_ctx)) -> list[dict]:
    with ctx.db.session() as s:
        recipes = RecipeRepository(s).list_for_product(product_id)
        return [
            {
                "id": r.id,
                "version": r.version,
                "is_active": bool(r.is_active),
                "pass_rule": r.pass_rule,
                "created_at": str(r.created_at),
            }
            for r in recipes
        ]


@router.get("/products/{product_id}/active-recipe", response_model=RecipeSchema)
def active_recipe(product_id: int, ctx=Depends(get_ctx)) -> RecipeSchema:
    with ctx.db.session() as s:
        recipe = RecipeRepository(s).active_for_product(product_id)
        if not recipe:
            raise HTTPException(404, "no active recipe for product")
        product = ProductRepository(s).get(product_id)
        return serialize_recipe(recipe, product)


@router.post("/recipes/{recipe_id}/activate", status_code=200)
def activate_recipe(recipe_id: int, ctx=Depends(get_ctx)) -> dict:
    with ctx.db.session() as s:
        RecipeRepository(s).activate(recipe_id)
    return {"status": "activated", "recipe_id": recipe_id}


@router.get("/surfaces/{surface_id}", response_model=SurfaceSchema)
def get_surface(surface_id: int, ctx=Depends(get_ctx)) -> SurfaceSchema:
    with ctx.db.session() as s:
        surface = SurfaceRepository(s).with_rois(surface_id)
        if not surface:
            raise HTTPException(404, "surface not found")
        rois = [
            RoiSchema(
                id=roi.id,
                name=roi.name,
                roi_index=roi.roi_index,
                inspector_type=roi.inspector_type,
                geometry=Geometry(**json.loads(roi.geometry)),
                params=json.loads(roi.params) if roi.params else None,
                threshold=roi.threshold,
            )
            for roi in sorted(surface.rois, key=lambda r: r.roi_index)
        ]
        return SurfaceSchema(
            id=surface.id,
            surface_index=surface.surface_index,
            name=surface.name,
            reference_image_path=surface.reference_image_path,
            rois=rois,
        )


@router.put("/surfaces/{surface_id}/rois", response_model=SurfaceSchema)
def set_surface_rois(surface_id: int, payload: SurfaceRoisInput, ctx=Depends(get_ctx)) -> SurfaceSchema:
    with ctx.db.session() as s:
        surface = SurfaceRepository(s).get(surface_id)
        if not surface:
            raise HTTPException(404, "surface not found")
        roi_defs = [
            {
                "id": r.id,
                "name": r.name,
                "roi_index": r.roi_index or (i + 1),
                "inspector_type": r.inspector_type,
                "geometry": r.geometry.model_dump(),
                "params": r.params,
                "threshold": r.threshold,
            }
            for i, r in enumerate(payload.rois)
        ]
        RoiRepository(s).replace_for_surface(surface_id, roi_defs)
    return get_surface(surface_id, ctx)
