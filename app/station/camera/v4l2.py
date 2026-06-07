"""V4L2 / UVC camera backend via OpenCV (USB industrial / webcams)."""

from __future__ import annotations

import logging

import numpy as np

from .base import CameraBackend, CameraError

logger = logging.getLogger(__name__)


class V4l2Camera(CameraBackend):
    name = "v4l2"

    def __init__(self, settings) -> None:
        super().__init__(settings)
        self._cap = None

    def _device_index(self):
        dev = self.settings.camera.device
        # OpenCV accepts an int index or a device path.
        if isinstance(dev, str) and dev.startswith("/dev/video"):
            try:
                return int(dev.replace("/dev/video", ""))
            except ValueError:
                return dev
        return dev

    def _open(self) -> None:
        import cv2

        self._cap = cv2.VideoCapture(self._device_index())
        if not self._cap or not self._cap.isOpened():
            raise CameraError(f"cannot open camera {self.settings.camera.device}")
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self._cap.set(cv2.CAP_PROP_FPS, self.settings.camera.fps)
        self._apply_controls()

    def _close(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    def _capture(self) -> np.ndarray:
        if self._cap is None:
            raise CameraError("camera not open")
        # Flush one stale buffered frame, then read a fresh one.
        self._cap.grab()
        ok, frame = self._cap.read()
        if not ok or frame is None:
            raise CameraError("frame grab failed")
        return frame

    def _apply_controls(self) -> None:
        if self._cap is None:
            return
        import cv2

        try:
            # Manual exposure (driver-dependent). _exposure is treated as a raw
            # control value when non-zero; 0 leaves auto-exposure enabled.
            if self._exposure:
                self._cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.25)
                self._cap.set(cv2.CAP_PROP_EXPOSURE, float(self._exposure))
            self._cap.set(cv2.CAP_PROP_GAIN, float(self._gain))
        except Exception:  # pragma: no cover - driver variance
            logger.debug("exposure/gain control not supported by driver")
