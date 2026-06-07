"""Lighting controller abstraction (optional in V1)."""

from .base import LightingController
from .factory import create_lighting

__all__ = ["LightingController", "create_lighting"]
