"""SQLite database handle: engine, pragmas, sessions, migrations, seeding."""

from __future__ import annotations

import json
import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .migrations import run_migrations
from .models import Setting
from ..config.runtime_settings import ALL_KEYS, LEGACY_ALIASES, defaults_from_settings

logger = logging.getLogger(__name__)


@event.listens_for(Engine, "connect")
def _set_sqlite_pragmas(dbapi_conn, _record):  # pragma: no cover - driver hook
    """Apply eMMC-friendly, integrity-preserving pragmas on every connection."""
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


class Database:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.engine: Engine = create_engine(
            f"sqlite:///{self.db_path}",
            connect_args={"check_same_thread": False},
            future=True,
        )
        self._session_factory = sessionmaker(
            bind=self.engine, autoflush=False, expire_on_commit=False, future=True
        )

    def migrate(self) -> int:
        version = run_migrations(self.engine)
        logger.info("Database at schema version %s (%s)", version, self.db_path)
        return version

    def seed_defaults(self, settings) -> None:
        """Insert default runtime settings rows if absent (idempotent)."""
        import json

        flat = defaults_from_settings(settings)
        with self.session() as s:
            existing = {row.key for row in s.query(Setting).all()}
            for key in ALL_KEYS:
                if key not in existing:
                    val = flat[key]
                    store = json.dumps(val) if isinstance(val, bool) else str(val)
                    s.add(Setting(key=key, value=store))
                    existing.add(key)
            # Migrate legacy flat keys into canonical names (one-time upgrade).
            for alias, canon in LEGACY_ALIASES.items():
                if alias in existing and canon not in existing:
                    row = s.get(Setting, alias)
                    if row:
                        s.add(Setting(key=canon, value=row.value))
                        existing.add(canon)

    @contextmanager
    def session(self) -> Iterator[Session]:
        """Transactional session scope: commit on success, rollback on error."""
        s = self._session_factory()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()

    def checkpoint(self) -> None:
        """Force a WAL checkpoint (call periodically / before backups)."""
        with self.engine.begin() as conn:
            conn.execute(text("PRAGMA wal_checkpoint(TRUNCATE)"))

    def get_setting(self, key: str, default: Optional[str] = None) -> Optional[str]:
        with self.session() as s:
            row = s.get(Setting, key)
            return row.value if row else default

    def set_setting(self, key: str, value: str) -> None:
        with self.session() as s:
            row = s.get(Setting, key)
            if row:
                row.value = value
            else:
                s.add(Setting(key=key, value=value))
