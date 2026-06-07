"""Draw ROI result overlays: green rectangle for OK, red for NOK (failed)."""

from __future__ import annotations

from typing import Dict, List

import numpy as np

_GREEN = (0, 200, 0)
_RED = (0, 0, 255)
_YELLOW = (0, 200, 255)


def draw_overlay(frame: np.ndarray, roi_outcomes: List[Dict]) -> np.ndarray:
    """Return a copy of the frame with labelled ROI rectangles.

    Each outcome: {geometry:{x,y,w,h}, decision, label, confidence, name}.
    """
    import cv2

    out = frame.copy()
    for o in roi_outcomes:
        g = o["geometry"]
        x, y, w, h = int(g["x"]), int(g["y"]), int(g["w"]), int(g["h"])
        if o["decision"] == "OK":
            color = _GREEN
        elif o["decision"] == "WARN":
            color = _YELLOW
        else:
            color = _RED
        thickness = 3
        cv2.rectangle(out, (x, y), (x + w, y + h), color, thickness)
        label = f"{o.get('name') or 'ROI'} {o['label']} {o['confidence']*100:.0f}%"
        ytext = y - 8 if y - 8 > 10 else y + 18
        cv2.putText(out, label, (x, ytext), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2, cv2.LINE_AA)
    return out
