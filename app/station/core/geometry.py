"""ROI geometry helpers: polygon points with legacy rectangle migration."""

from __future__ import annotations

from typing import Dict, List, Sequence, Tuple

Point = Tuple[int, int]


def rect_to_points(x: int, y: int, w: int, h: int) -> List[Point]:
    """Convert axis-aligned rectangle to 4-point polygon (clockwise)."""
    return [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]


def normalize_geometry_dict(data: Dict) -> Dict:
    """Return ``{"points": [[x,y], ...]}``; migrate legacy ``{x,y,w,h}``."""
    if not isinstance(data, dict):
        raise ValueError(f"geometry must be a dict, got {type(data)}")
    if "points" in data and data["points"]:
        pts = [[int(p[0]), int(p[1])] for p in data["points"]]
        if len(pts) < 3:
            raise ValueError("polygon needs at least 3 points")
        return {"points": pts}
    if all(k in data for k in ("x", "y", "w", "h")):
        x, y, w, h = int(data["x"]), int(data["y"]), int(data["w"]), int(data["h"])
        if w <= 0 or h <= 0:
            raise ValueError(f"invalid rectangle geometry: {data}")
        return {"points": [list(p) for p in rect_to_points(x, y, w, h)]}
    raise ValueError(f"unsupported geometry: {data}")


def geometry_points(geometry: Dict) -> List[Point]:
    """Extract polygon vertices from geometry dict (any supported format)."""
    return [tuple(p) for p in normalize_geometry_dict(geometry)["points"]]


def bbox_from_points(points: Sequence[Point]) -> Tuple[int, int, int, int]:
    """Return (x_min, y_min, x_max, y_max) inclusive of edge pixels."""
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return min(xs), min(ys), max(xs), max(ys)
