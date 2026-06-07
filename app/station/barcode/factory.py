"""Barcode reader factory: selects a backend from settings."""

from __future__ import annotations

from .base import BarcodeReader


def create_barcode_reader(settings, event_bus=None, loop=None) -> BarcodeReader:
    backend = settings.barcode.backend.lower()
    if backend == "manual":
        from .manual import ManualBarcodeReader

        return ManualBarcodeReader(settings, event_bus, loop)
    if backend == "evdev":
        from .evdev_reader import EvdevBarcodeReader

        return EvdevBarcodeReader(settings, event_bus, loop)
    if backend == "serial":
        from .serial_reader import SerialBarcodeReader

        return SerialBarcodeReader(settings, event_bus, loop)
    raise ValueError(f"unknown barcode backend: {settings.barcode.backend}")
