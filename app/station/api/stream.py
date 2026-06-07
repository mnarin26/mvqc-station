"""Live preview (MJPEG) and event stream (WebSocket)."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

from .deps import get_ctx

logger = logging.getLogger(__name__)
router = APIRouter(tags=["stream"])

_BOUNDARY = "frame"


@router.get("/stream/preview")
async def preview(request: Request) -> StreamingResponse:
    ctx = get_ctx(request)
    fps = max(1, min(ctx.settings.camera.fps, 25))
    interval = 1.0 / fps

    async def gen():
        while True:
            if await request.is_disconnected():
                break
            try:
                jpeg = await asyncio.to_thread(ctx.engine.preview_jpeg)
            except Exception:  # pragma: no cover
                logger.exception("preview frame failed")
                await asyncio.sleep(0.5)
                continue
            yield (
                b"--" + _BOUNDARY.encode() + b"\r\n"
                b"Content-Type: image/jpeg\r\n"
                b"Content-Length: " + str(len(jpeg)).encode() + b"\r\n\r\n"
                + jpeg + b"\r\n"
            )
            await asyncio.sleep(interval)

    return StreamingResponse(
        gen(), media_type=f"multipart/x-mixed-replace; boundary={_BOUNDARY}"
    )


@router.websocket("/ws")
async def ws_events(websocket: WebSocket) -> None:
    ctx = websocket.app.state.ctx
    await websocket.accept()
    queue = await ctx.event_bus.subscribe()
    try:
        # Greet with a snapshot so late joiners have immediate context.
        await websocket.send_json({"type": "hello", "payload": {
            "station_id": ctx.settings.station_id,
        }})
        while True:
            event = await queue.get()
            await websocket.send_json(event.to_json())
    except WebSocketDisconnect:
        pass
    except Exception:  # pragma: no cover
        logger.exception("websocket error")
    finally:
        await ctx.event_bus.unsubscribe(queue)
