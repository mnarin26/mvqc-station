"""Typed application settings loaded from ``config/app.yaml``.

The YAML path can be overridden with the ``MVQC_CONFIG`` environment variable.
Settings are validated with Pydantic v2 and cached as a singleton so every
module shares one immutable view of configuration.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import List, Literal, Optional

import yaml
from pydantic import BaseModel, Field

# Default config path resolves relative to the repo root (../../../config/app.yaml).
_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG_PATH = _REPO_ROOT / "config" / "app.yaml"


class PathsConfig(BaseModel):
    database: Path
    logs: Path
    cache: Path
    models: Path
    frontend: Path


class StorageConfig(BaseModel):
    mount: Path = Path("/mnt/mvqc")
    device: str = ""  # selected block device, e.g. /dev/sda1
    full_images_subdir: str = "full_images"
    exports_subdir: str = "exports"
    roi_archive_subdir: str = "roi_archive"
    teaching_subdir: str = "teaching"
    missing_policy: Literal["block", "buffer"] = "block"
    min_free_mb: int = 500
    buffer_dir: Path
    buffer_max_mb: int = 2000
    require_mountpoint: bool = True

    @property
    def full_images_dir(self) -> Path:
        return self.mount / self.full_images_subdir

    @property
    def exports_dir(self) -> Path:
        return self.mount / self.exports_subdir

    @property
    def roi_archive_dir(self) -> Path:
        return self.mount / self.roi_archive_subdir


class CameraConfig(BaseModel):
    backend: Literal["mock", "picamera2", "v4l2", "genicam"] = "mock"
    device: str = "/dev/video0"
    width: int = 1920
    height: int = 1080
    fps: int = 15
    exposure_default: float = 0.0
    gain_default: float = 1.0


class BarcodeConfig(BaseModel):
    backend: Literal["manual", "evdev", "serial"] = "manual"
    device: str = "/dev/input/event0"
    serial_port: str = "/dev/ttyUSB0"
    serial_baud: int = 9600


class LightingConfig(BaseModel):
    backend: Literal["none", "gpio", "serial"] = "none"


class TeachingConfig(BaseModel):
    frames_per_label: int = 20
    # When false (default): every frame uses camera exposure/gain defaults — stable teaching.
    # Enable later when a real lighting rig is wired for deliberate condition diversity.
    condition_sweep: bool = False
    exposure_sweep: List[float] = Field(default_factory=lambda: [-0.3, 0.0, 0.3])
    gain_sweep: List[float] = Field(default_factory=lambda: [1.0, 1.2])


class InferenceConfig(BaseModel):
    default_threshold: float = 0.5
    positive_class: str = "FILLED"


class DataCollectionConfig(BaseModel):
    low_conf_threshold: float = 0.85
    pass_sample_rate: float = 0.02
    save_full_image_on_pass: bool = False


class ArchivingConfig(BaseModel):
    retention_days_full_images: int = 30
    retention_days_exports: int = 90


class ServerConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8000


class LoggingConfig(BaseModel):
    level: str = "INFO"
    max_bytes: int = 5 * 1024 * 1024
    backup_count: int = 5


class Settings(BaseModel):
    station_id: str = "cm5-101"
    paths: PathsConfig
    storage: StorageConfig
    camera: CameraConfig = Field(default_factory=CameraConfig)
    barcode: BarcodeConfig = Field(default_factory=BarcodeConfig)
    lighting: LightingConfig = Field(default_factory=LightingConfig)
    teaching: TeachingConfig = Field(default_factory=TeachingConfig)
    inference: InferenceConfig = Field(default_factory=InferenceConfig)
    data_collection: DataCollectionConfig = Field(default_factory=DataCollectionConfig)
    archiving: ArchivingConfig = Field(default_factory=ArchivingConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)

    # Path of the file this was loaded from (informational).
    config_path: Optional[Path] = None

    def ensure_local_dirs(self) -> None:
        """Create the eMMC-side directories that must always exist."""
        for p in (
            self.paths.database.parent,
            self.paths.logs,
            self.paths.cache,
            self.paths.models,
            self.storage.buffer_dir,
        ):
            Path(p).mkdir(parents=True, exist_ok=True)


def load_settings(config_path: Optional[os.PathLike | str] = None) -> Settings:
    """Load and validate settings from a YAML file."""
    path = Path(config_path or os.environ.get("MVQC_CONFIG", DEFAULT_CONFIG_PATH))
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    storage = raw.get("storage") or {}
    if "mount" not in storage:
        storage["mount"] = storage.get("ssd2_mount") or storage.get("ssd3_mount") or "/mnt/mvqc"
    raw["storage"] = storage
    raw["config_path"] = path
    return Settings.model_validate(raw)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide cached Settings singleton."""
    return load_settings()
