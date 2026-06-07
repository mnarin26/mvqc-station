"""Inspector interface and result type."""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Dict, Optional

import numpy as np


@dataclass
class RoiOutcome:
    label: str
    confidence: float
    decision: str                      # OK | WARN | NOK
    probabilities: Dict[str, float] = field(default_factory=dict)
    detail: Dict = field(default_factory=dict)


class RoiInspector(abc.ABC):
    """Stateless inspector. Receives the ROI crop plus its configuration and a
    classifier (may be None for non-ML inspectors) and returns a RoiOutcome."""

    inspector_type: str = "base"

    @abc.abstractmethod
    def inspect(
        self,
        crop_bgr: np.ndarray,
        *,
        threshold: float,
        classifier=None,
        params: Optional[Dict] = None,
        positive_class: str = "FILLED",
    ) -> RoiOutcome: ...
