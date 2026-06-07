"""Storage layer: mount-aware SSD routing, buffering, archiving, retention."""

from .manager import StorageManager, StorageUnavailableError

__all__ = ["StorageManager", "StorageUnavailableError"]
