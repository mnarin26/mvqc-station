"""Recipe contract: product -> surfaces -> ROIs (geometry + inspector type)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from ..core.geometry import normalize_geometry_dict


class Geometry(BaseModel):
    """Closed polygon ROI in absolute pixel coordinates of the reference image.

  Stored as ``{"points": [[x,y], ...]}``. Legacy ``{x,y,w,h}`` rectangles are
  converted to 4-point polygons on load.
    """

    points: List[List[int]] = Field(min_length=3)

    @field_validator("points")
    @classmethod
    def _validate_points(cls, pts: List[List[int]]) -> List[List[int]]:
        out = [[int(p[0]), int(p[1])] for p in pts]
        if len(out) < 3:
            raise ValueError("polygon needs at least 3 points")
        return out

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy(cls, data: Any) -> Any:
        if isinstance(data, dict) and "points" not in data and "x" in data:
            return normalize_geometry_dict(data)
        return data


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
