"""Application dependency container.

Builds and wires every long-lived component (DB, storage, camera, barcode,
lighting, model registry, inspection engine, event bus) from Settings. Routers
read the shared instance from ``request.app.state.ctx``.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from ..config import Settings, get_settings
from .events import EventBus

logger = logging.getLogger(__name__)


class AppContext:
    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()
        self.settings.ensure_local_dirs()

        self.event_bus = EventBus()
        self.loop: Optional[asyncio.AbstractEventLoop] = None

        # Built lazily in start() so heavy/hardware imports stay out of import time.
        self.db = None
        self.storage = None
        self.camera = None
        self.barcode = None
        self.lighting = None
        self.model_registry = None
        self.engine = None
        self.teaching = None
        self.sync = None

    async def start(self) -> None:
        self.loop = asyncio.get_running_loop()

        # Database + migrations.
        from ..db.database import Database
        self.db = Database(self.settings.paths.database)
        self.db.migrate()
        self.db.seed_defaults(self.settings)

        # Apply any UI-saved overrides before hardware init.
        self._apply_runtime_settings()

        # Storage manager (mount detection + routing).
        from ..storage.manager import StorageManager
        self.storage = StorageManager(self.settings, self.event_bus, self.loop)
        await self.storage.start()

        # Hardware backends via factories.
        from ..camera.factory import create_camera
        self.camera = create_camera(self.settings)
        await asyncio.get_running_loop().run_in_executor(None, self.camera.open)

        from ..barcode.factory import create_barcode_reader
        self.barcode = create_barcode_reader(self.settings, self.event_bus, self.loop)
        self.barcode.start()

        from ..lighting.factory import create_lighting
        self.lighting = create_lighting(self.settings)

        # Model registry (active ONNX per ROI, hot-reloadable).
        from ..inference.registry import ModelRegistry
        self.model_registry = ModelRegistry(self.settings, self.db)
        self.model_registry.load_active()

        # Inspection engine orchestrator.
        from .engine import InspectionEngine
        self.engine = InspectionEngine(self)

        # Teaching service (EMPTY/FILLED auto-capture).
        from .teaching import TeachingService
        self.teaching = TeachingService(self)

        # Model sync/deploy client (USB now, network-ready).
        from ..sync.sync_client import LocalUsbSyncClient
        self.sync = LocalUsbSyncClient(self.settings, self.db, self.model_registry)

        logger.info("AppContext started (station_id=%s)", self.settings.station_id)

    async def stop(self) -> None:
        try:
            if self.camera is not None:
                self.camera.close()
        except Exception:  # pragma: no cover - best effort shutdown
            logger.exception("camera close failed")
        try:
            if self.barcode is not None:
                self.barcode.stop()
        except Exception:  # pragma: no cover
            logger.exception("barcode stop failed")
        try:
            if self.storage is not None:
                await self.storage.stop()
        except Exception:  # pragma: no cover
            logger.exception("storage stop failed")
        logger.info("AppContext stopped")

    def _apply_runtime_settings(self) -> None:
        from ..config.runtime_settings import apply_to_settings, load_merged

        merged = load_merged(self.settings, self.db)
        self.settings = apply_to_settings(self.settings, merged)

    async def reload_hardware(self) -> dict:
        """Re-read settings from DB and hot-reload camera, barcode, lighting."""
        loop = asyncio.get_running_loop()
        self._apply_runtime_settings()

        # Camera
        try:
            if self.camera is not None:
                await loop.run_in_executor(None, self.camera.close)
        except Exception:
            logger.exception("camera close during reload")
        from ..camera.factory import create_camera

        self.camera = create_camera(self.settings)
        await loop.run_in_executor(None, self.camera.open)

        # Barcode
        try:
            if self.barcode is not None:
                self.barcode.stop()
        except Exception:
            logger.exception("barcode stop during reload")
        from ..barcode.factory import create_barcode_reader

        self.barcode = create_barcode_reader(self.settings, self.event_bus, self.loop)
        self.barcode.start()

        # Lighting
        from ..lighting.factory import create_lighting

        self.lighting = create_lighting(self.settings)

        # Re-wire dependents.
        if self.engine is not None:
            self.engine.settings = self.settings
            self.engine.camera = self.camera
            self.engine.lighting = self.lighting
        if self.teaching is not None:
            self.teaching.settings = self.settings
            self.teaching.camera = self.camera
            self.teaching.lighting = self.lighting
        if self.storage is not None:
            self.storage.settings = self.settings
            self.storage.ensure_layout()

        return {
            "camera": self.camera.name,
            "barcode": self.barcode.name,
            "lighting": self.lighting.name,
            "camera_open": self.camera.is_open,
        }
