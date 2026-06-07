"""Lightweight, forward-only migration runner.

Applied versions are tracked in ``schema_migrations``. Version 1 creates the
full schema from the ORM metadata plus indexes. Future additive changes append
new ``Migration`` entries; they run in order, each in its own transaction.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, List

from sqlalchemy import text
from sqlalchemy.engine import Engine

from .models import Base

logger = logging.getLogger(__name__)

_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_inspections_ts ON inspections(timestamp)",
    "CREATE INDEX IF NOT EXISTS idx_cycles_barcode ON inspection_cycles(barcode)",
    "CREATE INDEX IF NOT EXISTS idx_roi_results_insp ON inspection_roi_results(inspection_id)",
    "CREATE INDEX IF NOT EXISTS idx_rois_surface ON rois(surface_id)",
    "CREATE INDEX IF NOT EXISTS idx_surfaces_recipe ON surfaces(recipe_id)",
    "CREATE INDEX IF NOT EXISTS idx_recipes_product ON recipes(product_id)",
    "CREATE INDEX IF NOT EXISTS idx_deployments_roi ON model_deployments(roi_id)",
]


@dataclass
class Migration:
    version: int
    description: str
    apply: Callable[[Engine], None]


def _v1_create_schema(engine: Engine) -> None:
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        for ddl in _INDEXES:
            conn.execute(text(ddl))


def _v2_roi_severity(engine: Engine) -> None:
    """Add severity column to inspection_roi_results (OK/WARN/NOK companion)."""
    with engine.begin() as conn:
        cols = conn.execute(text("PRAGMA table_info(inspection_roi_results)")).fetchall()
        if not any(row[1] == "severity" for row in cols):
            conn.execute(
                text(
                    "ALTER TABLE inspection_roi_results "
                    "ADD COLUMN severity TEXT NOT NULL DEFAULT 'ok'"
                )
            )


MIGRATIONS: List[Migration] = [
    Migration(1, "initial schema", _v1_create_schema),
    Migration(2, "inspection_roi_results.severity", _v2_roi_severity),
]


def _current_version(engine: Engine) -> int:
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                "version INTEGER PRIMARY KEY, "
                "description TEXT, "
                "applied_at TEXT NOT NULL DEFAULT (datetime('now')))"
            )
        )
        row = conn.execute(text("SELECT MAX(version) FROM schema_migrations")).scalar()
    return int(row or 0)


def run_migrations(engine: Engine) -> int:
    """Apply pending migrations; return the resulting schema version."""
    current = _current_version(engine)
    applied = current
    for migration in sorted(MIGRATIONS, key=lambda m: m.version):
        if migration.version <= current:
            continue
        logger.info("Applying migration %s: %s", migration.version, migration.description)
        migration.apply(engine)
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO schema_migrations (version, description) "
                    "VALUES (:v, :d)"
                ),
                {"v": migration.version, "d": migration.description},
            )
        applied = migration.version
    return applied
