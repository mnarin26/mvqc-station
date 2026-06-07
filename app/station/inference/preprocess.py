"""ROI cropping and image preprocessing for ONNX classifiers.

``input_spec`` (from the model bundle manifest) drives preprocessing so the
station matches exactly what the training server used:

    {
      "layout": "NCHW",          # or NHWC
      "size": [224, 224],        # (w, h)
      "color": "RGB",            # or BGR / GRAY
      "mean": [0.485, 0.456, 0.406],
      "std":  [0.229, 0.224, 0.225],
      "scale": 0.00392156862     # applied before mean/std (1/255 typical)
    }
"""

from __future__ import annotations

from typing import Dict, Tuple

import numpy as np

DEFAULT_INPUT_SPEC: Dict = {
    "layout": "NCHW",
    "size": [224, 224],
    "color": "RGB",
    "mean": [0.485, 0.456, 0.406],
    "std": [0.229, 0.224, 0.225],
    "scale": 1.0 / 255.0,
}


def crop_roi(frame: np.ndarray, geometry: Dict) -> np.ndarray:
    """Crop an axis-aligned ROI (clamped to image bounds). Frame is BGR HxWx3."""
    h, w = frame.shape[:2]
    x = max(0, int(geometry["x"]))
    y = max(0, int(geometry["y"]))
    rw = int(geometry["w"])
    rh = int(geometry["h"])
    x2 = min(w, x + rw)
    y2 = min(h, y + rh)
    if x2 <= x or y2 <= y:
        raise ValueError(f"empty ROI crop for geometry {geometry} on {w}x{h} frame")
    return frame[y:y2, x:x2].copy()


def preprocess(crop_bgr: np.ndarray, input_spec: Dict | None = None) -> np.ndarray:
    """Resize, recolor, normalize and lay out a crop into a model input tensor."""
    import cv2

    spec = {**DEFAULT_INPUT_SPEC, **(input_spec or {})}
    size: Tuple[int, int] = (int(spec["size"][0]), int(spec["size"][1]))

    img = cv2.resize(crop_bgr, size, interpolation=cv2.INTER_AREA)

    color = spec.get("color", "RGB").upper()
    if color == "RGB":
        img = img[:, :, ::-1]
    elif color == "GRAY":
        img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)[:, :, None]
    # BGR: leave as-is.

    arr = img.astype(np.float32) * float(spec.get("scale", 1.0 / 255.0))
    mean = np.array(spec.get("mean", [0, 0, 0]), dtype=np.float32)
    std = np.array(spec.get("std", [1, 1, 1]), dtype=np.float32)
    if arr.shape[2] == len(mean):
        arr = (arr - mean) / std

    if spec.get("layout", "NCHW").upper() == "NCHW":
        arr = np.transpose(arr, (2, 0, 1))  # HWC -> CHW
    return np.expand_dims(arr, 0).astype(np.float32)  # add batch dim
