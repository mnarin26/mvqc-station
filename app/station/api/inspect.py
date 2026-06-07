"""Inspection endpoints: run a cycle, list recent results, inject a scan."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException

from ..core.engine import EngineError, ProductNotReadyError
from ..db.repositories import InspectionRepository
from ..schemas.api import BarcodeSubmit, InspectRequest
from .deps import get_ctx

logger = logging.getLogger(__name__)
router = APIRouter(tags=["inspect"])


@router.post("/inspect")
async def run_inspection(payload: InspectRequest, ctx=Depends(get_ctx)) -> dict:
    if not payload.barcode and payload.product_id is None:
        raise HTTPException(400, "barcode or product_id required")
    try:
        result = await asyncio.to_thread(
            ctx.engine.run_cycle,
            barcode=payload.barcode,
            product_id=payload.product_id,
            surface_index=payload.surface_index,
        )
        return result
    except ProductNotReadyError as exc:
        raise HTTPException(409, str(exc))
    except EngineError as exc:
        raise HTTPException(400, str(exc))


@router.get("/inspect/recent")
def recent_inspections(limit: int = 50, ctx=Depends(get_ctx)) -> list[dict]:
    with ctx.db.session() as s:
        repo = InspectionRepository(s)
        return [
            {
                "id": i.id,
                "cycle_id": i.cycle_id,
                "surface_index": i.surface_index,
                "result": i.result,
                "overall_confidence": i.overall_confidence,
                "saved": bool(i.saved),
                "saved_reason": i.saved_reason,
                "full_image_path": i.full_image_path,
                "timestamp": str(i.timestamp),
            }
            for i in repo.recent(limit)
        ]


@router.post("/barcode/submit")
def submit_barcode(payload: BarcodeSubmit, ctx=Depends(get_ctx)) -> dict:
    """Inject a barcode (manual entry or web scanner) into the reader pipeline."""
    ctx.barcode.submit(payload.barcode)
    return {"status": "ok", "barcode": payload.barcode}
