"""Model registry: holds the active ONNX classifier per ROI, hot-reloadable.

Active models are resolved from ``model_deployments`` (is_active=1) -> ``models``.
After a bundle import/activation/rollback the engine calls ``load_active`` (or
``reload_roi``) to swap classifiers atomically with no process restart.
"""

from __future__ import annotations

import json
import logging
import threading
from typing import Dict, Optional

from ..db.repositories import ModelRepository
from .classifier import OnnxClassifier

logger = logging.getLogger(__name__)


class ModelRegistry:
    def __init__(self, settings, db) -> None:
        self.settings = settings
        self.db = db
        self._classifiers: Dict[int, OnnxClassifier] = {}
        self._meta: Dict[int, dict] = {}
        self._lock = threading.RLock()

    def load_active(self) -> int:
        """(Re)load all active ROI models from the database."""
        from ..db.models import Model

        pairs = []
        with self.db.session() as s:
            for dep in ModelRepository(s).all_active_deployments():
                model = s.get(Model, dep.model_id)
                if model is not None:
                    pairs.append((dep.roi_id, model))

        loaded = 0
        with self._lock:
            self._classifiers.clear()
            self._meta.clear()
            for roi_id, model in pairs:
                if self._load_one(roi_id, model):
                    loaded += 1
        logger.info("Loaded %d active ROI models", loaded)
        return loaded

    def _load_one(self, roi_id: int, model) -> bool:
        try:
            classes = json.loads(model.classes)
            input_spec = json.loads(model.input_spec)
            classifier = OnnxClassifier(model.onnx_path, classes, input_spec)
            self._classifiers[roi_id] = classifier
            self._meta[roi_id] = {
                "model_id": model.id,
                "version": model.version,
                "classes": classes,
                "onnx_path": model.onnx_path,
            }
            return True
        except Exception:
            logger.exception("failed to load model for roi %s (%s)", roi_id, model.onnx_path)
            return False

    def reload_roi(self, roi_id: int) -> bool:
        with self.db.session() as s:
            model = ModelRepository(s).active_model(roi_id)
        if model is None:
            with self._lock:
                self._classifiers.pop(roi_id, None)
                self._meta.pop(roi_id, None)
            return False
        with self._lock:
            return self._load_one(roi_id, model)

    def get(self, roi_id: int) -> Optional[OnnxClassifier]:
        with self._lock:
            return self._classifiers.get(roi_id)

    def version_for(self, roi_id: int) -> Optional[str]:
        with self._lock:
            meta = self._meta.get(roi_id)
            return meta["version"] if meta else None

    def has(self, roi_id: int) -> bool:
        with self._lock:
            return roi_id in self._classifiers

    def loaded_count(self) -> int:
        with self._lock:
            return len(self._classifiers)
