"""ROI polygon geometry and masked crop."""

from __future__ import annotations

import numpy as np

from station.core.geometry import bbox_from_points, normalize_geometry_dict
from station.inference.preprocess import crop_roi


def test_legacy_rect_to_polygon():
    g = normalize_geometry_dict({"x": 10, "y": 20, "w": 30, "h": 40})
    assert g["points"] == [[10, 20], [40, 20], [40, 60], [10, 60]]


def test_masked_crop_zeros_outside_polygon():
    frame = np.ones((100, 100, 3), dtype=np.uint8) * 255
    frame[30:70, 30:70] = (0, 128, 0)
    crop = crop_roi(frame, {"points": [[30, 30], [70, 30], [70, 70], [30, 70]]})
    x1, y1, x2, y2 = bbox_from_points([(30, 30), (70, 70)])
    assert crop.shape[0] == y2 - y1 + 1
    assert crop[0, 0].sum() == 0
    cx = crop.shape[1] // 2
    cy = crop.shape[0] // 2
    assert crop[cy, cx].sum() > 0
