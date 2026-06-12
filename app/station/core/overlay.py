"""Draw ROI result overlays: polygon outline green/yellow/red by decision."""

from __future__ import annotations

from typing import Dict, List

import numpy as np

from .geometry import bbox_from_points, geometry_points

_GREEN = (0, 200, 0)
_RED = (0, 0, 255)
_YELLOW = (0, 200, 255)


def draw_overlay(frame: np.ndarray, roi_outcomes: List[Dict]) -> np.ndarray:
    """Return a copy of the frame with labelled ROI polygons.

    Each outcome: {geometry:{points:[[x,y],...]}, decision, label, confidence, name}.
    """
    import cv2

    out = frame.copy()
    for o in roi_outcomes:
        points = geometry_points(o["geometry"])
        pts = np.array(points, dtype=np.int32).reshape(-1, 1, 2)
        if o["decision"] == "OK":
            color = _GREEN
        elif o["decision"] == "WARN":
            color = _YELLOW
        else:
            color = _RED
        thickness = 3
        cv2.polylines(out, [pts], isClosed=True, color=color, thickness=thickness)
        x1, y1, _, _ = bbox_from_points(points)
        label = f"{o.get('name') or 'ROI'} {o['label']} {o['confidence']*100:.0f}%"
        ytext = y1 - 8 if y1 - 8 > 10 else y1 + 18
        cv2.putText(out, label, (x1, ytext), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2, cv2.LINE_AA)
    return out
