"""StorageManager: single configurable volume for all image/ROI/teaching data."""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from ..system.mounts import device_exists, device_mountpoint, ensure_layout

logger = logging.getLogger(__name__)

_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


class StorageUnavailableError(RuntimeError):
    """Raised when storage is unavailable under ``block`` policy."""


def _sanitize(name: str) -> str:
    return _SAFE.sub("_", name).strip("_") or "x"


class StorageManager:
    TARGET = "storage"

    def __init__(self, settings, event_bus=None, loop: Optional[asyncio.AbstractEventLoop] = None) -> None:
        self.settings = settings
        self.event_bus = event_bus
        self.loop = loop
        self._poll_task: Optional[asyncio.Task] = None
        self._last_health: Dict = {}
        self._buffer_root = Path(settings.storage.buffer_dir)

    def root(self) -> Path:
        device = self.settings.storage.device
        if device:
            live = device_mountpoint(device)
            if live:
                return Path(live)
        return Path(self.settings.storage.mount)

    def _is_mounted(self, path: Path) -> bool:
        try:
            if not path.exists():
                return False
            if self.settings.storage.require_mountpoint:
                return os.path.ismount(path)
            return path.is_dir()
        except OSError:
            return False

    @staticmethod
    def _writable(path: Path) -> bool:
        return os.access(path, os.W_OK)

    @staticmethod
    def _free_mb(path: Path) -> float:
        try:
            return shutil.disk_usage(path).free / (1024 * 1024)
        except OSError:
            return 0.0

    def status(self) -> Dict:
        device = self.settings.storage.device or ""
        configured_mount = str(self.settings.storage.mount)

        if device and not device_exists(device):
            return {
                "device": device,
                "mount": configured_mount,
                "mounted": False,
                "writable": False,
                "free_mb": 0.0,
                "ok": False,
                "absent": True,
                "needs_selection": True,
                "message": "Storage device removed — select a volume in Settings",
            }

        if not device and not Path(configured_mount).exists():
            return {
                "device": "",
                "mount": configured_mount,
                "mounted": False,
                "writable": False,
                "free_mb": 0.0,
                "ok": False,
                "absent": False,
                "needs_selection": True,
                "message": "No storage selected — choose a volume in Settings",
            }

        mount = self.root()
        mounted = self._is_mounted(mount)
        writable = mounted and self._writable(mount)
        free_mb = self._free_mb(mount) if mounted else 0.0
        ok = mounted and writable and free_mb >= self.settings.storage.min_free_mb
        return {
            "device": device,
            "mount": str(mount),
            "mounted": mounted,
            "writable": writable,
            "free_mb": round(free_mb, 1),
            "ok": ok,
            "absent": False,
            "needs_selection": not ok,
            "message": "" if ok else "Storage unavailable — check Settings",
        }

    def health(self) -> Dict:
        st = self.status()
        health = {
            "ok": st["ok"],
            "policy": self.settings.storage.missing_policy,
            "min_free_mb": self.settings.storage.min_free_mb,
            "device": st.get("device", ""),
            "mount": st["mount"],
            "mounted": st["mounted"],
            "writable": st["writable"],
            "free_mb": st["free_mb"],
            "absent": st.get("absent", False),
            "needs_selection": st.get("needs_selection", False),
            "message": st.get("message", ""),
            "buffered_files": self._buffer_pending_count(),
        }
        self._last_health = health
        return health

    def available(self, target: str | None = None) -> bool:  # noqa: ARG002
        return self.status()["ok"]

    def ensure_layout(self) -> None:
        st = self.status()
        if not st["ok"] and st.get("needs_selection"):
            return
        mount = self.root()
        if mount.exists() and self._writable(mount):
            ensure_layout(mount)

    def full_image_path(self, product_name: str, result: str, when: Optional[datetime] = None) -> Path:
        when = when or datetime.now()
        day = when.strftime("%Y-%m-%d")
        fname = f"{when.strftime('%Y%m%d_%H%M%S')}_{_sanitize(product_name)}_{result.upper()}.jpg"
        return self.root() / self.settings.storage.full_images_subdir / day / fname

    def roi_archive_dir(self, inspection_id: int) -> Path:
        name = f"inspection_{inspection_id:06d}"
        return self.root() / self.settings.storage.roi_archive_subdir / name

    @property
    def full_images_dir(self) -> Path:
        return self.root() / self.settings.storage.full_images_subdir

    @property
    def exports_dir(self) -> Path:
        return self.root() / self.settings.storage.exports_subdir

    def export_zip_path(self, export_date: str) -> Path:
        return self.exports_dir / f"{export_date}.zip"

    def teaching_roi_dir(self, product_name: str, surface_index: int, label: str,
                         roi_index: int) -> Path:
        return (
            self.root()
            / "teaching"
            / _sanitize(product_name)
            / f"surface_{surface_index}"
            / label.upper()
            / f"roi_{roi_index}"
        )

    def write_bytes(self, path: Path, data: bytes) -> Path:
        if self.available():
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "wb") as fh:
                fh.write(data)
            return path
        return self._handle_unavailable(path, data)

    def write_text(self, path: Path, text: str) -> Path:
        return self.write_bytes(path, text.encode("utf-8"))

    def copy_into(self, src: Path, dest: Path) -> Path:
        with open(src, "rb") as fh:
            return self.write_bytes(dest, fh.read())

    def _handle_unavailable(self, path: Path, data: bytes) -> Path:
        policy = self.settings.storage.missing_policy
        if policy == "block":
            self._alarm(f"storage unavailable; write blocked: {path.name}")
            raise StorageUnavailableError("storage unavailable (policy=block)")
        rel = self._relative_to_root(path)
        buffer_path = self._buffer_root / self.TARGET / rel
        if self._buffer_size_mb() >= self.settings.storage.buffer_max_mb:
            self._alarm("buffer full; dropping write")
            raise StorageUnavailableError("buffer full")
        buffer_path.parent.mkdir(parents=True, exist_ok=True)
        with open(buffer_path, "wb") as fh:
            fh.write(data)
        logger.warning("Buffered write -> %s", buffer_path)
        return buffer_path

    def _relative_to_root(self, path: Path) -> Path:
        try:
            return path.relative_to(self.root())
        except ValueError:
            return Path(path.name)

    def _buffer_pending_count(self) -> int:
        base = self._buffer_root / self.TARGET
        if not base.exists():
            return 0
        return sum(1 for _ in base.rglob("*") if _.is_file())

    def _buffer_size_mb(self) -> float:
        base = self._buffer_root / self.TARGET
        if not base.exists():
            return 0.0
        total = sum(f.stat().st_size for f in base.rglob("*") if f.is_file())
        return total / (1024 * 1024)

    def flush_buffer(self) -> int:
        base = self._buffer_root / self.TARGET
        if not base.exists() or not self.available():
            return 0
        mount = self.root()
        flushed = 0
        for src in list(base.rglob("*")):
            if not src.is_file():
                continue
            rel = src.relative_to(base)
            dest = mount / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dest))
            flushed += 1
        for d in sorted(base.rglob("*"), reverse=True):
            if d.is_dir() and not any(d.iterdir()):
                d.rmdir()
        if flushed:
            logger.info("Flushed %d buffered files to storage", flushed)
        return flushed

    def _alarm(self, message: str) -> None:
        logger.error("STORAGE ALARM: %s", message)
        if self.event_bus and self.loop:
            self.event_bus.publish_threadsafe(
                self.loop, "storage_alarm", {"target": self.TARGET, "message": message}
            )

    async def start(self) -> None:
        self.health()
        try:
            self.flush_buffer()
        except Exception:  # pragma: no cover
            logger.exception("initial buffer flush failed")
        self.ensure_layout()
        if self.loop is not None:
            self._poll_task = asyncio.create_task(self._poll_loop())

    async def stop(self) -> None:
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass

    async def _poll_loop(self, interval: float = 15.0) -> None:
        prev_ok = None
        while True:
            try:
                health = self.health()
                if health["ok"]:
                    self.flush_buffer()
                if prev_ok is not None and prev_ok != health["ok"]:
                    if self.event_bus:
                        await self.event_bus.publish("storage_health", health)
                prev_ok = health["ok"]
            except asyncio.CancelledError:
                raise
            except Exception:  # pragma: no cover
                logger.exception("storage poll error")
            await asyncio.sleep(interval)

    SSD2 = TARGET
