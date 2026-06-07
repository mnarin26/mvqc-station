"""Serial-controlled lighting controller (vendor ASCII protocol, hardware only)."""

from __future__ import annotations

from .base import LightingController


class SerialLighting(LightingController):  # pragma: no cover - hardware only
    name = "serial"

    def __init__(self, settings) -> None:
        super().__init__(settings)
        import serial

        self._serial = serial.Serial(settings.lighting_serial_port
                                      if hasattr(settings, "lighting_serial_port")
                                      else "/dev/ttyUSB1", 9600, timeout=1)

    def _send(self, cmd: str) -> None:
        self._serial.write((cmd + "\r\n").encode("ascii"))

    def on(self) -> None:
        self._send(f"LEVEL {int(self._level * 100)}")
        self._send("ON")

    def off(self) -> None:
        self._send("OFF")

    def _apply(self) -> None:
        self._send(f"LEVEL {int(self._level * 100)}")
