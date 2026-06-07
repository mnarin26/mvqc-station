"""Request/response DTOs for the HTTP API."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from .recipe import Geometry


# ----------------------------------------------------------------- products
class ProductCreate(BaseModel):
    name: str
    barcode: Optional[str] = None
    surface_count: int = Field(default=1, ge=1, le=64)
    pass_rule: str = "all_filled"


class ProductOut(BaseModel):
    id: int
    name: str
    barcode: Optional[str]
    surface_count: int
    status: str
    active_recipe_id: Optional[int] = None
    created_at: str


# ------------------------------------------------------------------ recipes
class RoiInput(BaseModel):
    id: Optional[int] = None  # existing ROI id; enables in-place edit instead of recreate
    name: Optional[str] = None
    roi_index: Optional[int] = None
    inspector_type: str = "presence"
    geometry: Geometry
    params: Optional[Dict[str, Any]] = None
    threshold: float = 0.5


class SurfaceRoisInput(BaseModel):
    rois: List[RoiInput]


# ----------------------------------------------------------------- teaching
class TeachingStart(BaseModel):
    surface_id: int
    label: str                         # EMPTY | FILLED
    frames: Optional[int] = None       # default from config


class TeachingResult(BaseModel):
    session_id: int
    label: str
    frames_captured: int
    samples_per_roi: Dict[str, int]


# ----------------------------------------------------------------- inspect
class InspectRequest(BaseModel):
    barcode: Optional[str] = None
    product_id: Optional[int] = None
    surface_index: Optional[int] = None  # default: all surfaces in sequence


class RoiResultOut(BaseModel):
    roi_id: int
    roi_index: int
    name: Optional[str]
    label: str
    confidence: float
    decision: str                      # OK | WARN | NOK
    severity: Optional[str] = "ok"     # ok | warning | error
    geometry: Geometry


class SurfaceResultOut(BaseModel):
    inspection_id: int
    surface_index: int
    result: str
    overall_confidence: float
    full_image_path: Optional[str]
    roi_results: List[RoiResultOut]
    saved: bool
    saved_reason: Optional[str]


class InspectResponse(BaseModel):
    cycle_id: int
    product: str
    barcode: Optional[str]
    result: str
    surfaces: List[SurfaceResultOut]


# ------------------------------------------------------------------- models
class DeployBy(BaseModel):
    deployed_by: Optional[str] = "operator"


class SettingsUpdate(BaseModel):
    """Partial runtime settings update. Keys use dot notation (``camera.backend``)
    or legacy flat names (``low_conf_threshold``)."""

    model_config = {"extra": "allow"}

    # Explicit fields kept for backward compatibility with older HMI builds.
    low_conf_threshold: Optional[float] = None
    pass_sample_rate: Optional[float] = None
    save_full_image_on_pass: Optional[bool] = None
    reload_hardware: bool = True


class BarcodeSubmit(BaseModel):
    barcode: str
