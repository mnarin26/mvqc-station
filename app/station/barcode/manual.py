"""Manual barcode entry backend (HMI types or web-scans the code)."""

from __future__ import annotations

from .base import BarcodeReader


class ManualBarcodeReader(BarcodeReader):
    name = "manual"

    def start(self) -> None:
        # Nothing to run; scans arrive via submit() from the API.
        pass

    def stop(self) -> None:
        pass
