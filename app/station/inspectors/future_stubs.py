"""Registered-but-unimplemented inspectors for future versions.

These reserve the ``inspector_type`` keys and demonstrate the plugin seam. They
raise ``NotImplementedError`` if used in V1, so a recipe can be authored against
them but inspection will clearly signal they are not yet available.
"""

from __future__ import annotations

from typing import Dict, Optional

import numpy as np

from .base import RoiInspector, RoiOutcome
from .registry import register_inspector


class _NotImplementedInspector(RoiInspector):
    inspector_type = "_abstract"

    def inspect(self, crop_bgr: np.ndarray, *, threshold: float, classifier=None,
                params: Optional[Dict] = None, positive_class: str = "FILLED") -> RoiOutcome:
        raise NotImplementedError(
            f"inspector '{self.inspector_type}' is planned for a future version"
        )


@register_inspector
class OcrInspector(_NotImplementedInspector):
    inspector_type = "ocr"


@register_inspector
class CountInspector(_NotImplementedInspector):
    inspector_type = "count"


@register_inspector
class ColorInspector(_NotImplementedInspector):
    inspector_type = "color"


@register_inspector
class AnomalyInspector(_NotImplementedInspector):
    inspector_type = "anomaly"


@register_inspector
class WrongComponentInspector(_NotImplementedInspector):
    inspector_type = "wrong_component"
