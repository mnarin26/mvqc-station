"""Model-bundle manifest contract (produced by the training server).

A bundle is a ZIP containing ``manifest.json`` plus one ONNX file per ROI. The
manifest maps each model to a ROI (by index within a surface, plus product
identity) so the station can match it to its local recipe and verify integrity.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class ModelEntry(BaseModel):
    surface_index: int
    roi_index: int
    roi_name: Optional[str] = None
    version: str
    onnx_file: str                     # path within the ZIP
    classes: List[str]                 # e.g. ["EMPTY", "FILLED"]
    input_spec: Dict                   # {layout, size, mean, std, color}
    checksum_sha256: str
    metrics: Optional[Dict] = None
    training_run_id: Optional[str] = None


class ModelBundleManifest(BaseModel):
    bundle_version: str = "1.0"
    product_name: str
    product_barcode: Optional[str] = None
    recipe_version: Optional[int] = None
    created_at: Optional[str] = None
    source: str = "manual_usb"         # manual_usb | network
    models: List[ModelEntry] = Field(default_factory=list)
