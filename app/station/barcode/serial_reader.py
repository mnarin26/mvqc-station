"""Serial barcode scanner backend (RS232/USB-CDC line protocol)."""

from __future__ import annotations

import logging
import threading

from .base import BarcodeReader

logger = logging.getLogger(__name__)


class SerialBarcodeReader(BarcodeReader):
    name = "serial"

    def __init__(self, settings, event_bus=None, loop=None) -> None:
        super().__init__(settings, event_bus, loop)
        self._thread = None
        self._stop = threading.Event()
        self._serial = None

    def start(self) -> None:
        try:
            import serial

            self._serial = serial.Serial(
                self.settings.barcode.serial_port,
                self.settings.barcode.serial_baud,
                timeout=1,
            )
        except Exception as exc:  # pragma: no cover - hardware only
            logger.error("serial scanner unavailable (%s); scans via HMI only", exc)
            self._serial = None
            return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info("serial barcode reader on %s", self.settings.barcode.serial_port)

    def stop(self) -> None:
        self._stop.set()
        if self._serial is not None:  # pragma: no cover - hardware only
            try:
                self._serial.close()
            except Exception:
                pass

    def _run(self) -> None:  # pragma: no cover - hardware only
        while not self._stop.is_set() and self._serial is not None:
            try:
                line = self._serial.readline().decode("ascii", errors="ignore")
                if line:
                    self._emit(line)
            except Exception:
                logger.exception("serial read error")
                break
