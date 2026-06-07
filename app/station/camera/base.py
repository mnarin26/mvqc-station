"""Camera backend interface and shared helpers.

A backend yields BGR ``numpy`` frames (OpenCV convention). Exposure/gain are
expressed in backend-relative units; teaching sweeps call ``set_exposure`` /
``set_gain`` to vary lighting conditions across the ~20 captured frames.
"""

from __future__ import annotations

import abc
import threading
from typing import Optional

import numpy as np


class CameraError(RuntimeError):
    pass


class CameraBackend(abc.ABC):
    """Thread-safe-ish camera contract used by the engine and preview stream."""

    name: str = "base"

    def __init__(self, settings) -> None:
        self.settings = settings
        self.width = settings.camera.width
        self.height = settings.camera.height
        self._lock = threading.Lock()
        self._opened = False
        self._exposure = settings.camera.exposure_default
        self._gain = settings.camera.gain_default

    @abc.abstractmethod
    def _open(self) -> None: ...

    @abc.abstractmethod
    def _capture(self) -> np.ndarray: ...

    @abc.abstractmethod
    def _close(self) -> None: ...

    def open(self) -> None:
        with self._lock:
            if not self._opened:
                self._open()
                self._opened = True

    def close(self) -> None:
        with self._lock:
            if self._opened:
                try:
                    self._close()
                finally:
                    self._opened = False

    def capture(self) -> np.ndarray:
        """Return one BGR frame (HxWx3 uint8)."""
        with self._lock:
            if not self._opened:
                self._open()
                self._opened = True
            frame = self._capture()
        if frame is None:
            raise CameraError("camera returned no frame")
        return frame

    # Exposure/gain controls. Backends override _apply_controls to push to HW.
    def set_exposure(self, value: float) -> None:
        self._exposure = value
        self._apply_controls()

    def set_gain(self, value: float) -> None:
        self._gain = value
        self._apply_controls()

    def reset_controls(self) -> None:
        self._exposure = self.settings.camera.exposure_default
        self._gain = self.settings.camera.gain_default
        self._apply_controls()

    def _apply_controls(self) -> None:  # pragma: no cover - overridden by HW backends
        pass

    @property
    def is_open(self) -> bool:
        return self._opened


def encode_jpeg(frame: np.ndarray, quality: int = 85) -> bytes:
    """Encode a BGR frame to JPEG bytes (OpenCV, falls back to Pillow)."""
    try:
        import cv2

        ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
        if not ok:
            raise CameraError("cv2 JPEG encode failed")
        return buf.tobytes()
    except ImportError:  # pragma: no cover - cv2 always present on station
        from io import BytesIO

        from PIL import Image

        rgb = frame[:, :, ::-1]
        out = BytesIO()
        Image.fromarray(rgb).save(out, format="JPEG", quality=quality)
        return out.getvalue()
