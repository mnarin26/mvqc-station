"""Lighting controller interface.

The external lighting system can be toggled and (where supported) dimmed. During
teaching sweeps the engine varies ``level`` to diversify samples; during
inspection a fixed level is set for repeatability.
"""

from __future__ import annotations

import abc


class LightingController(abc.ABC):
    name: str = "base"

    def __init__(self, settings) -> None:
        self.settings = settings
        self._level = 1.0

    @abc.abstractmethod
    def on(self) -> None: ...

    @abc.abstractmethod
    def off(self) -> None: ...

    def set_level(self, level: float) -> None:
        """Set brightness 0.0..1.0 (no-op where dimming is unsupported)."""
        self._level = max(0.0, min(1.0, level))
        self._apply()

    def _apply(self) -> None:  # pragma: no cover - overridden by HW backends
        pass

    @property
    def level(self) -> float:
        return self._level


class NoLighting(LightingController):
    name = "none"

    def on(self) -> None:
        pass

    def off(self) -> None:
        pass
