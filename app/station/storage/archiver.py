"""Daily archiver: bundle a day's saved data into an export ZIP on SSD-2.

ZIP layout:
    full_images/<filename>.jpg
    roi_archive/inspection_000123/{roi_*.jpg, metadata.json}
    metadata/inspection_000123.json     (flat copy for convenience)

After a verified ZIP is written it records an ``exports`` row and applies
retention (pruning old local full images + old export ZIPs).
"""

from __future__ import annotations

import logging
import os
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List

from sqlalchemy import select

from ..db.models import Inspection
from ..db.repositories import ExportRepository
from .manager import StorageManager

logger = logging.getLogger(__name__)


class DailyArchiver:
    def __init__(self, settings, db, storage: StorageManager) -> None:
        self.settings = settings
        self.db = db
        self.storage = storage

    def _saved_inspections_for(self, date_str: str) -> List[Inspection]:
        with self.db.session() as s:
            rows = list(
                s.scalars(
                    select(Inspection).where(
                        Inspection.saved == 1,
                        Inspection.timestamp.like(f"{date_str}%"),
                    )
                )
            )
            # Detach plain dicts.
            s.expunge_all()
            return rows

    def create_daily_zip(self, date_str: str) -> Dict:
        # Validate target availability up front.
        if not self.storage.available(StorageManager.SSD2):
            return {"status": "failed", "reason": "SSD-2 unavailable", "date": date_str}

        zip_path = self.storage.export_zip_path(date_str)
        zip_path.parent.mkdir(parents=True, exist_ok=True)

        inspections = self._saved_inspections_for(date_str)
        full_images_dir = self.storage.full_images_dir / date_str

        with self.db.session() as s:
            ExportRepository(s).upsert(date_str, str(zip_path))

        item_count = 0
        try:
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                # Full images for the day.
                if full_images_dir.is_dir():
                    for img in sorted(full_images_dir.glob("*.jpg")):
                        zf.write(img, f"full_images/{img.name}")
                        item_count += 1
                # ROI archives + metadata for saved inspections.
                for insp in inspections:
                    if insp.roi_archive_dir and Path(insp.roi_archive_dir).is_dir():
                        roi_dir = Path(insp.roi_archive_dir)
                        for f in sorted(roi_dir.rglob("*")):
                            if f.is_file():
                                rel = f.relative_to(roi_dir.parent)
                                zf.write(f, f"roi_archive/{rel}")
                                item_count += 1
                        meta = roi_dir / "metadata.json"
                        if meta.exists():
                            zf.write(meta, f"metadata/{roi_dir.name}.json")
                            item_count += 1
        except Exception as exc:
            logger.exception("daily zip failed for %s", date_str)
            with self.db.session() as s:
                ExportRepository(s).mark(date_str, "failed")
            return {"status": "failed", "reason": str(exc), "date": date_str}

        # Verify the archive integrity.
        if not self._verify(zip_path):
            with self.db.session() as s:
                ExportRepository(s).mark(date_str, "failed")
            return {"status": "failed", "reason": "verification failed", "date": date_str}

        size = zip_path.stat().st_size
        with self.db.session() as s:
            ExportRepository(s).mark(date_str, "done", size_bytes=size, item_count=item_count)

        pruned = self.apply_retention()
        logger.info("daily zip %s done (%d items, %d bytes)", date_str, item_count, size)
        return {
            "status": "done",
            "date": date_str,
            "zip_path": str(zip_path),
            "items": item_count,
            "size_bytes": size,
            "pruned": pruned,
        }

    @staticmethod
    def _verify(zip_path: Path) -> bool:
        try:
            with zipfile.ZipFile(zip_path) as zf:
                return zf.testzip() is None
        except Exception:
            return False

    def apply_retention(self) -> Dict[str, int]:
        """Prune old local full images and old export ZIPs (best effort)."""
        result = {"full_images": 0, "exports": 0}
        if not self.storage.available(StorageManager.SSD2):
            return result

        now = datetime.now()
        # Full image day-folders older than retention_days_full_images.
        fi_cutoff = now - timedelta(days=self.settings.archiving.retention_days_full_images)
        fi_root = self.storage.full_images_dir
        if fi_root.is_dir():
            for day_dir in fi_root.iterdir():
                if not day_dir.is_dir():
                    continue
                try:
                    day = datetime.strptime(day_dir.name, "%Y-%m-%d")
                except ValueError:
                    continue
                if day < fi_cutoff:
                    for f in day_dir.rglob("*"):
                        if f.is_file():
                            f.unlink(missing_ok=True)
                            result["full_images"] += 1
                    self._rmtree_empty(day_dir)

        # Export ZIPs older than retention_days_exports.
        ex_cutoff = now - timedelta(days=self.settings.archiving.retention_days_exports)
        ex_root = self.storage.exports_dir
        if ex_root.is_dir():
            for zf in ex_root.glob("*.zip"):
                try:
                    day = datetime.strptime(zf.stem, "%Y-%m-%d")
                except ValueError:
                    continue
                if day < ex_cutoff:
                    zf.unlink(missing_ok=True)
                    result["exports"] += 1
        return result

    @staticmethod
    def _rmtree_empty(path: Path) -> None:
        try:
            for d in sorted(path.rglob("*"), reverse=True):
                if d.is_dir() and not any(d.iterdir()):
                    d.rmdir()
            if path.is_dir() and not any(path.iterdir()):
                path.rmdir()
        except OSError:
            pass
