"""Centralized logging configuration with size-capped rotation (eMMC-friendly)."""

from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

from .config import Settings

_CONFIGURED = False


def configure_logging(settings: Settings) -> None:
    """Configure root logging once: console + rotating file handler.

    Rotation keeps total log footprint bounded so the 64 GB eMMC never fills
    from logs alone.
    """
    global _CONFIGURED
    if _CONFIGURED:
        return

    log_dir = Path(settings.paths.logs)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "station.log"

    level = getattr(logging, settings.logging.level.upper(), logging.INFO)
    fmt = logging.Formatter(
        "%(asctime)s %(levelname)-7s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root = logging.getLogger()
    root.setLevel(level)

    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=settings.logging.max_bytes,
        backupCount=settings.logging.backup_count,
        encoding="utf-8",
    )
    file_handler.setFormatter(fmt)

    console = logging.StreamHandler()
    console.setFormatter(fmt)

    root.handlers.clear()
    root.addHandler(file_handler)
    root.addHandler(console)

    # Quiet noisy third-party loggers.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("multipart").setLevel(logging.WARNING)

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
