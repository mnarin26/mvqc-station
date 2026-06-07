"""Camera abstraction with pluggable hardware backends."""

from .base import CameraBackend, CameraError, encode_jpeg
from .factory import create_camera

__all__ = ["CameraBackend", "CameraError", "encode_jpeg", "create_camera"]
