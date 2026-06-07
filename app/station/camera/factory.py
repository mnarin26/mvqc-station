"""Camera backend factory: selects an implementation from settings."""

from __future__ import annotations

import logging

from .base import CameraBackend

logger = logging.getLogger(__name__)


def create_camera(settings) -> CameraBackend:
    backend = settings.camera.backend.lower()
    if backend == "mock":
        from .mock import MockCamera

        return MockCamera(settings)
    if backend == "v4l2":
        from .v4l2 import V4l2Camera

        return V4l2Camera(settings)
    if backend == "picamera2":
        from .picamera2_backend import Picamera2Camera

        return Picamera2Camera(settings)
    if backend == "genicam":
        from .genicam import GenICamCamera

        return GenICamCamera(settings)
    raise ValueError(f"unknown camera backend: {settings.camera.backend}")
