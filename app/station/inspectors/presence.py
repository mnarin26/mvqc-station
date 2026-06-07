"""Presence inspector: EMPTY / FILLED / per-ROI defect classification.

Decision mapping (argmax class from the deployed model):
- FILLED  -> OK   (component present and healthy)
- EMPTY   -> NOK  (missing component, severity=error)
- defect  -> NOK or WARN depending on ROI params.defects[].severity
"""

from __future__ import annotations

from typing import Dict, Optional

import numpy as np

from .base import RoiInspector, RoiOutcome
from .registry import register_inspector


@register_inspector
class PresenceInspector(RoiInspector):
    inspector_type = "presence"

    def inspect(
        self,
        crop_bgr: np.ndarray,
        *,
        threshold: float,
        classifier=None,
        params: Optional[Dict] = None,
        positive_class: str = "FILLED",
    ) -> RoiOutcome:
        if classifier is None:
            raise RuntimeError("presence inspector requires a deployed model")

        result = classifier.classify(crop_bgr)
        pred_label = result.label
        pred_conf = float(result.confidence)
        defects = (params or {}).get("defects") or []
        defect_map = {
            str(d.get("label", "")).upper(): str(d.get("severity", "error")).lower()
            for d in defects
            if d.get("label")
        }

        if pred_label == positive_class:
            decision, severity = "OK", "ok"
            confidence = pred_conf
        elif pred_label == "EMPTY":
            decision, severity = "NOK", "error"
            confidence = pred_conf
        elif pred_label.upper() in defect_map:
            sev = defect_map[pred_label.upper()]
            if sev == "warning":
                decision, severity = "WARN", "warning"
            else:
                decision, severity = "NOK", "error"
            confidence = pred_conf
        else:
            # Unknown / legacy binary fallback: treat non-FILLED as missing.
            positive_prob = result.probabilities.get(positive_class, 0.0)
            present = positive_prob >= threshold
            pred_label = positive_class if present else _negative_class(result.probabilities, positive_class)
            decision = "OK" if present else "NOK"
            severity = "ok" if present else "error"
            confidence = positive_prob if present else (1.0 - positive_prob)

        return RoiOutcome(
            label=pred_label,
            confidence=float(confidence),
            decision=decision,
            probabilities=result.probabilities,
            detail={
                "severity": severity,
                "threshold": threshold,
                "defects": list(defect_map.keys()),
            },
        )


def _negative_class(probabilities: Dict[str, float], positive_class: str) -> str:
    for cls in probabilities:
        if cls != positive_class:
            return cls
    return "EMPTY"
