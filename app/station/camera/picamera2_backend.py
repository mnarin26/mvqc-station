"""Picamera2 / libcamera backend for CSI cameras on the Raspberry Pi 5 / CM5.

Requires the system package ``python3-picamera2`` (installed via apt, exposed to
the venv with ``--system-site-packages`` or by running with system Python).
"""

from __future__ import annotations

import logging

import numpy as np

from .base import CameraBackend, CameraError

logger = logging.getLogger(__name__)


class Picamera2Camera(CameraBackend):
    name = "picamera2"

    def __init__(self, settings) -> None:
        super().__init__(settings)
        self._picam = None

    def _open(self) -> None:
        try:
            from picamera2 import Picamera2
        except ImportError as exc:  # pragma: no cover - hardware only
            raise CameraError(
                "picamera2 not available; install python3-picamera2"
            ) from exc

        self._picam = Picamera2()
        config = self._picam.create_still_configuration(
            main={"size": (self.width, self.height), "format": "RGB888"}
        )
        self._picam.configure(config)
        self._picam.start()
        self._apply_controls()

    def _close(self) -> None:  # pragma: no cover - hardware only
        if self._picam is not None:
            self._picam.stop()
            self._picam.close()
            self._picam = None

    def _capture(self) -> np.ndarray:  # pragma: no cover - hardware only
        if self._picam is None:
            raise CameraError("camera not open")
        rgb = self._picam.capture_array()
        # Convert RGB -> BGR for OpenCV convention.
        return rgb[:, :, ::-1].copy()

    def _apply_controls(self) -> None:  # pragma: no cover - hardware only
        if self._picam is None:
            return
        try:
            controls = {"AnalogueGain": float(max(self._gain, 1.0))}
            if self._exposure:
                # Treat _exposure as an EV offset -> exposure time multiplier.
                base_us = 10000
                controls["ExposureTime"] = int(base_us * (2.0 ** self._exposure))
                controls["AeEnable"] = False
            self._picam.set_controls(controls)
        except Exception:
            logger.debug("picamera2 control set failed", exc_info=True)
