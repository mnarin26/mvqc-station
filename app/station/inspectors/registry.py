"""Inspector registry: maps ``inspector_type`` -> RoiInspector instance."""

from __future__ import annotations

from typing import Dict, List, Type

from .base import RoiInspector

_REGISTRY: Dict[str, RoiInspector] = {}


def register_inspector(cls: Type[RoiInspector]) -> Type[RoiInspector]:
    """Class decorator that registers an inspector by its ``inspector_type``."""
    instance = cls()
    _REGISTRY[cls.inspector_type] = instance
    return cls


def get_inspector(inspector_type: str) -> RoiInspector:
    try:
        return _REGISTRY[inspector_type]
    except KeyError as exc:
        raise KeyError(
            f"no inspector registered for type '{inspector_type}'; "
            f"available: {sorted(_REGISTRY)}"
        ) from exc


def available_inspectors() -> List[str]:
    return sorted(_REGISTRY)
