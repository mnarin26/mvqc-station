"""Barcode reader abstraction with pluggable backends."""

from .base import BarcodeReader
from .factory import create_barcode_reader

__all__ = ["BarcodeReader", "create_barcode_reader"]
