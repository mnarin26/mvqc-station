"""USB-HID (keyboard-wedge) barcode scanner backend using evdev.

Reads key events from the configured input device on a daemon thread, assembles
characters until Enter, then emits the decoded barcode. Grabs the device so
keystrokes do not leak into other applications.
"""

from __future__ import annotations

import logging
import threading

from .base import BarcodeReader

logger = logging.getLogger(__name__)

# Minimal US-layout scancode map (digits + letters + common symbols).
_KEYMAP = {
    "KEY_0": "0", "KEY_1": "1", "KEY_2": "2", "KEY_3": "3", "KEY_4": "4",
    "KEY_5": "5", "KEY_6": "6", "KEY_7": "7", "KEY_8": "8", "KEY_9": "9",
    "KEY_MINUS": "-", "KEY_DOT": ".", "KEY_SLASH": "/", "KEY_SPACE": " ",
}
for _c in "abcdefghijklmnopqrstuvwxyz":
    _KEYMAP[f"KEY_{_c.upper()}"] = _c


class EvdevBarcodeReader(BarcodeReader):
    name = "evdev"

    def __init__(self, settings, event_bus=None, loop=None) -> None:
        super().__init__(settings, event_bus, loop)
        self._thread = None
        self._stop = threading.Event()
        self._device = None

    def start(self) -> None:
        try:
            from evdev import InputDevice

            self._device = InputDevice(self.settings.barcode.device)
            self._device.grab()
        except Exception as exc:  # pragma: no cover - hardware only
            logger.error("evdev scanner unavailable (%s); scans via HMI only", exc)
            self._device = None
            return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info("evdev barcode reader on %s", self.settings.barcode.device)

    def stop(self) -> None:
        self._stop.set()
        if self._device is not None:  # pragma: no cover - hardware only
            try:
                self._device.ungrab()
            except Exception:
                pass

    def _run(self) -> None:  # pragma: no cover - hardware only
        from evdev import categorize, ecodes

        buffer: list[str] = []
        shift = False
        for event in self._device.read_loop():
            if self._stop.is_set():
                break
            if event.type != ecodes.EV_KEY:
                continue
            data = categorize(event)
            if data.keystate != data.key_down:
                # Track shift release.
                if data.keycode in ("KEY_LEFTSHIFT", "KEY_RIGHTSHIFT"):
                    shift = False
                continue
            key = data.keycode if isinstance(data.keycode, str) else data.keycode[0]
            if key in ("KEY_LEFTSHIFT", "KEY_RIGHTSHIFT"):
                shift = True
            elif key == "KEY_ENTER":
                self._emit("".join(buffer))
                buffer.clear()
            elif key in _KEYMAP:
                ch = _KEYMAP[key]
                buffer.append(ch.upper() if shift and ch.isalpha() else ch)
