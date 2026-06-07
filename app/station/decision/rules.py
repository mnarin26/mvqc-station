"""Aggregate per-ROI outcomes into a surface PASS/FAIL decision.

Pass rules:
- ``all_filled`` (V1 default): PASS iff every ROI decision is OK or WARN.
  WARN does not fail the surface but is surfaced in ``warning_roi_indices``.
- ``any_filled``: PASS if at least one ROI is OK (WARN alone is not enough).

Overall confidence is the worst-case (minimum) ROI confidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class SurfaceDecision:
    result: str                        # PASS | FAIL
    overall_confidence: float
    failed_roi_indices: List[int]
    warning_roi_indices: List[int] = field(default_factory=list)


def aggregate_surface(roi_outcomes: List[dict], pass_rule: str = "all_filled") -> SurfaceDecision:
    """``roi_outcomes`` items: {roi_index, decision, confidence}."""
    if not roi_outcomes:
        return SurfaceDecision(result="FAIL", overall_confidence=0.0, failed_roi_indices=[])

    failed = [o["roi_index"] for o in roi_outcomes if o["decision"] == "NOK"]
    warnings = [o["roi_index"] for o in roi_outcomes if o["decision"] == "WARN"]
    oks = [o for o in roi_outcomes if o["decision"] == "OK"]
    confidences = [float(o["confidence"]) for o in roi_outcomes]
    overall = min(confidences) if confidences else 0.0

    if pass_rule == "any_filled":
        passed = len(oks) >= 1
    else:  # all_filled (default): NOK fails; WARN passes with warning flag
        passed = len(failed) == 0

    return SurfaceDecision(
        result="PASS" if passed else "FAIL",
        overall_confidence=round(overall, 4),
        failed_roi_indices=failed,
        warning_roi_indices=warnings,
    )
