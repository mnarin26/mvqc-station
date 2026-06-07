"""GenICam / GigE-USB3 industrial camera backend via Aravis (best effort).

This is a thin stub showing the integration seam; finalize against the specific
camera/vendor SDK during station commissioning. Falls back with a clear error if
the Aravis GI bindings are unavailable.
"""

from __future__ import annotations

import logging

import numpy as np

from .base import CameraBackend, CameraError

logger = logging.getLogger(__name__)


class GenICamCamera(CameraBackend):
    name = "genicam"

    def __init__(self, settings) -> None:
        super().__init__(settings)
        self._camera = None
        self._stream = None

    def _open(self) -> None:  # pragma: no cover - hardware only
        try:
            import gi

            gi.require_version("Aravis", "0.8")
            from gi.repository import Aravis
        except Exception as exc:
            raise CameraError(
                "Aravis GI bindings not available; install gir1.2-aravis-0.8"
            ) from exc

        self._aravis = Aravis
        self._camera = Aravis.Camera.new(None)  # first detected device
        self._camera.set_region(0, 0, self.width, self.height)
        self._apply_controls()
        self._stream = self._camera.create_stream(None, None)
        payload = self._camera.get_payload()
        for _ in range(5):
            self._stream.push_buffer(Aravis.Buffer.new_allocate(payload))
        self._camera.start_acquisition()

    def _close(self) -> None:  # pragma: no cover - hardware only
        if self._camera is not None:
            self._camera.stop_acquisition()
            self._camera = None
            self._stream = None

    def _capture(self) -> np.ndarray:  # pragma: no cover - hardware only
        if self._stream is None:
            raise CameraError("camera not open")
        buffer = self._stream.pop_buffer()
        if buffer is None:
            raise CameraError("no buffer")
        try:
            w = buffer.get_image_width()
            h = buffer.get_image_height()
            data = buffer.get_data()
            mono = np.frombuffer(data, dtype=np.uint8).reshape(h, w)
            return np.repeat(mono[:, :, None], 3, axis=2)
        finally:
            self._stream.push_buffer(buffer)

    def _apply_controls(self) -> None:  # pragma: no cover - hardware only
        if self._camera is None:
            return
        try:
            self._camera.set_gain(float(self._gain))
            if self._exposure:
                self._camera.set_exposure_time(10000.0 * (2.0 ** self._exposure))
        except Exception:
            logger.debug("genicam control set failed", exc_info=True)
