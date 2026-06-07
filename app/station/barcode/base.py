"""Barcode reader interface.

Backends deliver decoded barcode strings. Each scan is (a) published on the
event bus as ``barcode_scan`` for the HMI and (b) dispatched to registered
handlers (the inspection engine subscribes here to start a cycle).
"""

from __future__ import annotations

import abc
import asyncio
import logging
from typing import Callable, List, Optional

logger = logging.getLogger(__name__)

ScanHandler = Callable[[str], None]


class BarcodeReader(abc.ABC):
    name: str = "base"

    def __init__(self, settings, event_bus=None, loop: Optional[asyncio.AbstractEventLoop] = None) -> None:
        self.settings = settings
        self.event_bus = event_bus
        self.loop = loop
        self._handlers: List[ScanHandler] = []

    def add_handler(self, handler: ScanHandler) -> None:
        self._handlers.append(handler)

    def _emit(self, code: str) -> None:
        code = (code or "").strip()
        if not code:
            return
        logger.info("barcode scan: %s", code)
        if self.event_bus and self.loop:
            self.event_bus.publish_threadsafe(self.loop, "barcode_scan", {"barcode": code})
        for handler in list(self._handlers):
            try:
                handler(code)
            except Exception:  # pragma: no cover - handler isolation
                logger.exception("barcode handler error")

    def submit(self, code: str) -> None:
        """Inject a scan from the HMI (manual entry / web scanner)."""
        self._emit(code)

    @abc.abstractmethod
    def start(self) -> None: ...

    @abc.abstractmethod
    def stop(self) -> None: ...
