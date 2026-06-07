"""ROI inspector plugins, selected per ROI by ``inspector_type``.

V1 ships ``presence`` (EMPTY/FILLED). Future capabilities (ocr, count, color,
anomaly, wrong_component) register here without touching the engine.
"""

from .base import RoiInspector, RoiOutcome
from .registry import get_inspector, register_inspector, available_inspectors

# Import implementations for their registration side effects.
from . import presence  # noqa: F401
from . import future_stubs  # noqa: F401

__all__ = [
    "RoiInspector",
    "RoiOutcome",
    "get_inspector",
    "register_inspector",
    "available_inspectors",
]
