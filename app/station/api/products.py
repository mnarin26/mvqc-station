"""Product CRUD + setup. Creating a product also creates its draft recipe v1
with one row per surface, so teaching can begin immediately."""

from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete

from ..db.models import InspectionCycle
from ..db.repositories import ProductRepository, RecipeRepository, SurfaceRepository
from ..schemas.api import ProductCreate, ProductOut
from .deps import get_ctx

router = APIRouter(tags=["products"])


def _product_out(product, active_recipe_id=None) -> ProductOut:
    return ProductOut(
        id=product.id,
        name=product.name,
        barcode=product.barcode,
        surface_count=product.surface_count,
        status=product.status,
        active_recipe_id=active_recipe_id,
        created_at=str(product.created_at),
    )


@router.post("/products", response_model=ProductOut, status_code=201)
def create_product(payload: ProductCreate, ctx=Depends(get_ctx)) -> ProductOut:
    with ctx.db.session() as s:
        products = ProductRepository(s)
        if products.by_name(payload.name):
            raise HTTPException(409, f"product '{payload.name}' already exists")
        if payload.barcode and products.by_barcode(payload.barcode):
            raise HTTPException(409, f"barcode '{payload.barcode}' already in use")

        product = products.create(payload.name, payload.barcode, payload.surface_count)
        recipes = RecipeRepository(s)
        recipe = recipes.create_version(product.id, pass_rule=payload.pass_rule)
        surfaces = SurfaceRepository(s)
        for idx in range(1, payload.surface_count + 1):
            surfaces.create(recipe.id, idx, name=f"Surface {idx}")
        return _product_out(product, active_recipe_id=None)


@router.get("/products", response_model=list[ProductOut])
def list_products(ctx=Depends(get_ctx)) -> list[ProductOut]:
    with ctx.db.session() as s:
        products = ProductRepository(s)
        recipes = RecipeRepository(s)
        out = []
        for p in products.list():
            active = recipes.active_for_product(p.id)
            out.append(_product_out(p, active.id if active else None))
        return out


@router.get("/products/{product_id}", response_model=ProductOut)
def get_product(product_id: int, ctx=Depends(get_ctx)) -> ProductOut:
    with ctx.db.session() as s:
        product = ProductRepository(s).get(product_id)
        if not product:
            raise HTTPException(404, "product not found")
        active = RecipeRepository(s).active_for_product(product_id)
        return _product_out(product, active.id if active else None)


@router.delete("/products/{product_id}", status_code=204)
def delete_product(product_id: int, ctx=Depends(get_ctx)) -> None:
    """Delete a product and all dependent data (recipes, ROIs, models, teaching).

    Inspection cycles must be removed first because their FK constraints are
    NO ACTION; everything else cascades from the product row.
    """
    product_name: str | None = None
    with ctx.db.session() as s:
        product = ProductRepository(s).get(product_id)
        if not product:
            raise HTTPException(404, "product not found")
        product_name = product.name
        s.execute(delete(InspectionCycle).where(InspectionCycle.product_id == product_id))
        s.delete(product)

    if product_name:
        models_root = Path(ctx.settings.paths.models) / product_name
        if models_root.exists():
            shutil.rmtree(models_root, ignore_errors=True)
    if ctx.model_registry is not None:
        ctx.model_registry.load_active()
