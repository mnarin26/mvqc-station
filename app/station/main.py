"""FastAPI application entry point for the MVQC station.

Single deployable for V1: REST API + WebSocket event bus + MJPEG live preview +
static frontend, with the inspection engine running in-process. Launched by
``uvicorn station.main:app`` under systemd.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .core.context import AppContext
from .logging_setup import configure_logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings)
    ctx = AppContext(settings)
    await ctx.start()
    app.state.ctx = ctx
    try:
        yield
    finally:
        await ctx.stop()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="MVQC Station",
        version="1.0.0",
        description="Machine Vision QC production station (component presence).",
        lifespan=lifespan,
    )

    # Permissive CORS: HMI is served from a LAN browser (separate origin).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from .api import (
        products,
        recipes,
        teaching,
        inspect,
        models,
        system,
        stream,
    )

    app.include_router(system.router, prefix="/api")
    app.include_router(products.router, prefix="/api")
    app.include_router(recipes.router, prefix="/api")
    app.include_router(teaching.router, prefix="/api")
    app.include_router(inspect.router, prefix="/api")
    app.include_router(models.router, prefix="/api")
    app.include_router(stream.router)  # MJPEG + WebSocket (no /api prefix)

    # Serve the built frontend (SPA) if present.
    frontend_dir = Path(settings.paths.frontend)
    assets_dir = frontend_dir / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.get("/", include_in_schema=False)
    async def index():
        index_file = frontend_dir / "index.html"
        if index_file.exists():
            return FileResponse(str(index_file))
        return {"app": "MVQC Station", "status": "ok", "hint": "Frontend not built yet."}

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        # Client-side routing fallback for the SPA.
        index_file = frontend_dir / "index.html"
        if index_file.exists():
            return FileResponse(str(index_file))
        return {"detail": "Not found"}

    return app


app = create_app()
