"""Recipe contract: product -> surfaces -> ROIs (geometry + inspector type)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class Geometry(BaseModel):
    """Axis-aligned ROI rectangle in absolute pixel coordinates of the surface
    reference image."""

    x: int = Field(ge=0)
    y: int = Field(ge=0)
    w: int = Field(gt=0)
    h: int = Field(gt=0)


class RoiSchema(BaseModel):
    id: Optional[int] = None
    name: Optional[str] = None
    roi_index: int
    inspector_type: str = "presence"
    geometry: Geometry
    params: Optional[Dict[str, Any]] = None
    threshold: float = 0.5


class SurfaceSchema(BaseModel):
    id: Optional[int] = None
    surface_index: int
    name: Optional[str] = None
    reference_image_path: Optional[str] = None
    capture_settings: Optional[Dict[str, Any]] = None
    rois: List[RoiSchema] = Field(default_factory=list)


class RecipeSchema(BaseModel):
    id: Optional[int] = None
    product_id: int
    product_name: Optional[str] = None
    version: int
    is_active: bool = False
    pass_rule: str = "all_filled"
    surfaces: List[SurfaceSchema] = Field(default_factory=list)
