"""GPIO-driven lighting (PWM dimming) via gpiozero (hardware only)."""

from __future__ import annotations

from .base import LightingController


class GpioLighting(LightingController):  # pragma: no cover - hardware only
    name = "gpio"

    def __init__(self, settings) -> None:
        super().__init__(settings)
        from gpiozero import PWMLED

        # Default to BCM pin 18; expose via params later if needed.
        self._led = PWMLED(18)

    def on(self) -> None:
        self._led.value = self._level

    def off(self) -> None:
        self._led.value = 0

    def _apply(self) -> None:
        if self._led.value > 0:
            self._led.value = self._level
