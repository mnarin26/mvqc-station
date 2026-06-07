"""Lighting controller factory."""

from __future__ import annotations

import logging

from .base import LightingController, NoLighting

logger = logging.getLogger(__name__)


def create_lighting(settings) -> LightingController:
    backend = settings.lighting.backend.lower()
    if backend == "none":
        return NoLighting(settings)
    if backend == "gpio":
        try:
            from .gpio import GpioLighting

            return GpioLighting(settings)
        except Exception as exc:  # pragma: no cover - hardware only
            logger.error("gpio lighting unavailable (%s); using NoLighting", exc)
            return NoLighting(settings)
    if backend == "serial":
        try:
            from .serial_light import SerialLighting

            return SerialLighting(settings)
        except Exception as exc:  # pragma: no cover - hardware only
            logger.error("serial lighting unavailable (%s); using NoLighting", exc)
            return NoLighting(settings)
    raise ValueError(f"unknown lighting backend: {settings.lighting.backend}")
