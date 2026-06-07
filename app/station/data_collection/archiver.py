"""Result archiver: persists saved inspections to SSD-2 (full image) and SSD-3
(per-ROI crops + metadata.json), honoring the storage policy.

Layout (SSD-3): roi_archive/inspection_000123/{roi_1.jpg, roi_2.jpg, metadata.json}
Layout (SSD-2): full_images/YYYY-MM-DD/YYYYMMDD_HHMMSS_<Product>_<PASS|FAIL>.jpg
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Dict, List

import numpy as np

from ..camera.base import encode_jpeg
from ..schemas.metadata import InspectionMetadata, RoiDetail
from ..storage.manager import StorageUnavailableError

logger = logging.getLogger(__name__)


class ResultArchiver:
    def __init__(self, settings, storage) -> None:
        self.settings = settings
        self.storage = storage

    def archive(
        self,
        *,
        inspection_id: int,
        product_name: str,
        barcode: str | None,
        surface_index: int,
        result: str,
        overall_confidence: float,
        saved_reason: str,
        recipe_version: int | None,
        roi_crops: List[np.ndarray],
        roi_outcomes: List[dict],
        full_image: np.ndarray,
        save_full_image: bool,
        when: datetime | None = None,
    ) -> Dict[str, str | None]:
        """Write ROI crops, metadata.json (always for saved inspections) and the
        full image (when requested). Returns the stored paths."""
        when = when or datetime.now()
        roi_dir = self.storage.roi_archive_dir(inspection_id)

        paths: Dict[str, str | None] = {"roi_archive_dir": str(roi_dir), "full_image_path": None}

        # ROI crops -> SSD-3.
        roi_image_paths: List[str] = []
        for i, crop in enumerate(roi_crops, start=1):
            roi_path = roi_dir / f"roi_{i}.jpg"
            self.storage.write_bytes(roi_path, encode_jpeg(crop))
            roi_image_paths.append(str(roi_path))

        # metadata.json -> SSD-3.
        metadata = self._build_metadata(
            inspection_id, product_name, barcode, surface_index, result,
            overall_confidence, saved_reason, recipe_version, roi_outcomes, when,
        )
        self.storage.write_text(roi_dir / "metadata.json", metadata.model_dump_json(indent=2))

        # Full image -> SSD-2 (always for FAIL; for PASS only if configured).
        if save_full_image:
            full_path = self.storage.full_image_path(product_name, result, when)
            self.storage.write_bytes(full_path, encode_jpeg(full_image))
            paths["full_image_path"] = str(full_path)

        paths["roi_image_paths"] = roi_image_paths  # type: ignore[assignment]
        return paths

    def _build_metadata(self, inspection_id, product_name, barcode, surface_index,
                        result, overall_confidence, saved_reason, recipe_version,
                        roi_outcomes, when) -> InspectionMetadata:
        roi_results = {}
        roi_detail = []
        for o in roi_outcomes:
            key = f"roi{o['roi_index']}"
            roi_results[key] = o["label"]
            roi_detail.append(
                RoiDetail(
                    name=o.get("name") or key,
                    label=o["label"],
                    confidence=round(float(o["confidence"]), 4),
                    decision=o["decision"],
                    model_version=o.get("model_version"),
                )
            )
        return InspectionMetadata(
            inspection_id=f"{inspection_id:06d}",
            product=product_name,
            barcode=barcode,
            surface=surface_index,
            timestamp=when.strftime("%Y-%m-%d %H:%M:%S"),
            result=result,
            confidence=round(float(overall_confidence), 4),
            saved_reason=saved_reason,
            recipe_version=recipe_version,
            station_id=self.settings.station_id,
            roi_results=roi_results,
            roi_detail=roi_detail,
        )
