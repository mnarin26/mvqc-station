"""System endpoints: health, station info, settings, dashboard stats."""

from __future__ import annotations

import json
import subprocess
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Body

from ..config.runtime_settings import (
    ALL_KEYS,
    LEGACY_ALIASES,
    defaults_from_settings,
    load_merged,
    persist_updates,
    schema_for_ui,
)
from ..db.repositories import InspectionRepository, write_audit
from ..system.devices import list_input_devices, list_serial_ports, list_video_devices
from ..system.mounts import (
    device_select_value,
    list_storage_devices,
    list_storage_mountpoints,
    resolve_device_selection,
)
from .deps import get_ctx

router = APIRouter(tags=["system"])


def _normalize_updates(body: Dict[str, Any]) -> tuple[Dict[str, Any], bool]:
    reload_hw = bool(body.get("reload_hardware", True))
    updates: Dict[str, Any] = {}
    for k, v in body.items():
        if k == "reload_hardware" or v is None:
            continue
        canon = LEGACY_ALIASES.get(k, k)
        if canon in ALL_KEYS or k in LEGACY_ALIASES:
            updates[canon] = v
    return updates, reload_hw


def _resolve_storage_mounts(updates: Dict[str, Any], ctx) -> Dict[str, Any]:
    """Resolve storage volume selection to device + mount paths."""
    resolved = dict(updates)
    selection = None
    if "storage.device" in resolved:
        selection = resolved["storage.device"]
    elif "storage.mount" in resolved:
        selection = resolved["storage.mount"]
    if selection is None:
        return resolved
    try:
        result = resolve_device_selection(str(selection), str(ctx.settings.storage.mount))
    except subprocess.CalledProcessError as exc:
        raise HTTPException(500, f"could not mount storage: {exc}") from exc
    except OSError as exc:
        raise HTTPException(500, f"could not mount storage: {exc}") from exc
    resolved["storage.device"] = result["device"]
    resolved["storage.mount"] = result["mount"]
    return resolved


@router.get("/health")
def health(ctx=Depends(get_ctx)) -> dict:
    storage = ctx.storage.health() if ctx.storage else {"ok": False}
    return {
        "status": "ok",
        "station_id": ctx.settings.station_id,
        "camera": {
            "backend": ctx.camera.name if ctx.camera else None,
            "open": ctx.camera.is_open if ctx.camera else False,
            "device": ctx.settings.camera.device,
            "resolution": f"{ctx.settings.camera.width}x{ctx.settings.camera.height}",
        },
        "barcode": ctx.barcode.name if ctx.barcode else None,
        "lighting": ctx.lighting.name if ctx.lighting else None,
        "storage": storage,
        "models_loaded": ctx.model_registry.loaded_count() if ctx.model_registry else 0,
    }


@router.get("/info")
def info(ctx=Depends(get_ctx)) -> dict:
    from .. import __version__

    return {
        "app": "MVQC Station",
        "version": __version__,
        "station_id": ctx.settings.station_id,
        "positive_class": ctx.settings.inference.positive_class,
    }


@router.get("/settings")
def get_settings_endpoint(ctx=Depends(get_ctx)) -> dict:
    """Full settings for the HMI: schema sections + current values + YAML defaults."""
    defaults = defaults_from_settings(ctx.settings)
    # Re-merge from DB for current effective values.
    current = load_merged(ctx.settings, ctx.db)
    return {
        "values": current,
        "defaults": defaults,
        "sections": schema_for_ui(defaults, current),
        # Flat legacy shape for older clients.
        "low_conf_threshold": current.get("data_collection.low_conf_threshold"),
        "pass_sample_rate": current.get("data_collection.pass_sample_rate"),
        "save_full_image_on_pass": current.get("data_collection.save_full_image_on_pass"),
    }


@router.get("/settings/devices")
def settings_devices(ctx=Depends(get_ctx)) -> dict:
    """Hardware paths for dropdowns (video, evdev input, serial, storage mounts)."""
    storage_health = ctx.storage.health() if ctx.storage else {}
    extra = []
    if ctx.settings.storage.device:
        extra.append(device_select_value(ctx.settings.storage.device))
    extra.append(str(ctx.settings.storage.mount))
    return {
        "video": list_video_devices(),
        "input": list_input_devices(),
        "serial": list_serial_ports(),
        "mounts": list_storage_mountpoints(extra),
        "storage_devices": list_storage_devices(),
        "storage_health": storage_health,
    }


@router.put("/settings")
async def update_settings(body: Dict[str, Any] = Body(...), ctx=Depends(get_ctx)) -> dict:
    updates, reload_hw = _normalize_updates(body)
    if not updates:
        raise HTTPException(400, "no settings provided")

    try:
        updates = _resolve_storage_mounts(updates, ctx)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    persist_updates(ctx.db, updates)
    ctx._apply_runtime_settings()
    if ctx.storage is not None:
        ctx.storage.ensure_layout()

    hardware = {}
    if reload_hw:
        try:
            hardware = await ctx.reload_hardware()
        except Exception as exc:
            with ctx.db.session() as s:
                write_audit(s, "ERROR", "settings", f"hardware reload failed: {exc}")
            raise HTTPException(500, f"settings saved but hardware reload failed: {exc}") from exc

    with ctx.db.session() as s:
        write_audit(s, "INFO", "settings", "runtime settings updated", {"keys": list(updates)})

    current = load_merged(ctx.settings, ctx.db)
    return {
        "status": "ok",
        "values": current,
        "hardware": hardware,
        "storage": ctx.storage.health() if ctx.storage else {},
        "sections": schema_for_ui(defaults_from_settings(ctx.settings), current),
    }


@router.post("/settings/reload-hardware")
async def reload_hardware_endpoint(ctx=Depends(get_ctx)) -> dict:
    try:
        return {"status": "ok", "hardware": await ctx.reload_hardware()}
    except Exception as exc:
        raise HTTPException(500, str(exc)) from exc


@router.get("/dashboard")
def dashboard(ctx=Depends(get_ctx)) -> dict:
    with ctx.db.session() as s:
        repo = InspectionRepository(s)
        stats = repo.stats()
        recent = repo.recent(limit=20)
        recent_out = [
            {
                "id": i.id,
                "result": i.result,
                "surface_index": i.surface_index,
                "overall_confidence": i.overall_confidence,
                "saved": bool(i.saved),
                "saved_reason": i.saved_reason,
                "timestamp": str(i.timestamp),
            }
            for i in recent
        ]
    storage = ctx.storage.health() if ctx.storage else {"ok": False}
    return {"stats": stats, "recent": recent_out, "storage": storage}
