"""Per-inspection ``metadata.json`` contract written to the ROI archive (SSD-3).

Superset of the spec example, kept backward compatible: the flat ``roi_results``
map is always present; ``roi_detail`` adds confidence/decision/model version.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class RoiDetail(BaseModel):
    name: str
    label: str
    confidence: float
    decision: str                      # OK | NOK
    model_version: Optional[str] = None


class InspectionMetadata(BaseModel):
    inspection_id: str
    product: str
    barcode: Optional[str] = None
    surface: int
    timestamp: str
    result: str                        # PASS | FAIL
    confidence: float
    saved_reason: Optional[str] = None
    recipe_version: Optional[int] = None
    station_id: Optional[str] = None
    roi_results: Dict[str, str] = Field(default_factory=dict)
    roi_detail: List[RoiDetail] = Field(default_factory=list)
