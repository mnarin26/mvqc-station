"""Admin CLI for the MVQC station.

Usage:
    python -m station.cli migrate
    python -m station.cli serve [--host H] [--port P]
    python -m station.cli archive [--date YYYY-MM-DD]
    python -m station.cli import-model <bundle.zip> [--by NAME]
    python -m station.cli healthcheck
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date

from .config import get_settings
from .logging_setup import configure_logging, get_logger

logger = get_logger("station.cli")


def cmd_migrate(args: argparse.Namespace) -> int:
    settings = get_settings()
    from .db.database import Database

    db = Database(settings.paths.database)
    db.migrate()
    db.seed_defaults(settings)
    print(f"Database migrated at {settings.paths.database}")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    settings = get_settings()
    host = args.host or settings.server.host
    port = args.port or settings.server.port
    uvicorn.run(
        "station.main:app",
        host=host,
        port=port,
        log_level=settings.logging.level.lower(),
    )
    return 0


def cmd_archive(args: argparse.Namespace) -> int:
    settings = get_settings()
    from .db.database import Database
    from .storage.manager import StorageManager
    from .storage.archiver import DailyArchiver

    db = Database(settings.paths.database)
    db.migrate()
    storage = StorageManager(settings, event_bus=None, loop=None)
    target = args.date or date.today().isoformat()
    archiver = DailyArchiver(settings, db, storage)
    result = archiver.create_daily_zip(target)
    print(json.dumps(result, indent=2))
    return 0 if result.get("status") == "done" else 1


def cmd_import_model(args: argparse.Namespace) -> int:
    settings = get_settings()
    from .db.database import Database
    from .inference.registry import ModelRegistry
    from .sync.sync_client import LocalUsbSyncClient

    db = Database(settings.paths.database)
    db.migrate()
    registry = ModelRegistry(settings, db)
    client = LocalUsbSyncClient(settings, db, registry)
    result = client.import_bundle(args.bundle, deployed_by=args.by or "cli")
    print(json.dumps(result, indent=2))
    return 0 if result.get("status") == "activated" else 1


def cmd_healthcheck(args: argparse.Namespace) -> int:
    settings = get_settings()
    from .storage.manager import StorageManager

    storage = StorageManager(settings, event_bus=None, loop=None)
    health = storage.health()
    print(json.dumps(health, indent=2))
    return 0 if health.get("ok") else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="station", description="MVQC station admin CLI")
    parser.add_argument("--config", help="Path to app.yaml (overrides MVQC_CONFIG)")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("migrate", help="Create/upgrade the SQLite schema")

    p_serve = sub.add_parser("serve", help="Run the FastAPI server")
    p_serve.add_argument("--host")
    p_serve.add_argument("--port", type=int)

    p_arch = sub.add_parser("archive", help="Build the daily export ZIP")
    p_arch.add_argument("--date", help="YYYY-MM-DD (default: today)")

    p_imp = sub.add_parser("import-model", help="Import an ONNX model bundle (USB)")
    p_imp.add_argument("bundle", help="Path to the model bundle .zip")
    p_imp.add_argument("--by", help="Operator/admin name for the audit log")

    sub.add_parser("healthcheck", help="Report storage/mount health")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.config:
        # Point the settings loader at an explicit file, then clear the cache.
        import os

        os.environ["MVQC_CONFIG"] = args.config
        get_settings.cache_clear()  # type: ignore[attr-defined]

    configure_logging(get_settings())

    dispatch = {
        "migrate": cmd_migrate,
        "serve": cmd_serve,
        "archive": cmd_archive,
        "import-model": cmd_import_model,
        "healthcheck": cmd_healthcheck,
    }
    return dispatch[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
