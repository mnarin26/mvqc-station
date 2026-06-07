"""Teaching endpoints: snapshot for ROI drawing + EMPTY/FILLED auto-capture."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException

from ..schemas.api import TeachingResult, TeachingStart
from .deps import get_ctx

router = APIRouter(tags=["teaching"])


@router.get("/teaching/snapshot")
async def snapshot(ctx=Depends(get_ctx)) -> dict:
    """Freeze a single frame (data URL) for drawing ROIs in the HMI."""
    return await asyncio.to_thread(ctx.teaching.snapshot)


@router.post("/teaching/capture", response_model=TeachingResult)
async def capture(payload: TeachingStart, ctx=Depends(get_ctx)) -> TeachingResult:
    try:
        result = await asyncio.to_thread(
            ctx.teaching.capture, payload.surface_id, payload.label, payload.frames
        )
        return TeachingResult(**result)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.get("/teaching/status/{surface_id}")
def status(surface_id: int, ctx=Depends(get_ctx)) -> dict:
    return ctx.teaching.status(surface_id)
