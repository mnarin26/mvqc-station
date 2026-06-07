"""Shared FastAPI dependencies."""

from __future__ import annotations

from fastapi import Request

from ..core.context import AppContext


def get_ctx(request: Request) -> AppContext:
    return request.app.state.ctx
