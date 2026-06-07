"""Runtime settings: UI-editable values stored in SQLite, merged over app.yaml.

Flat keys use dot notation (``camera.backend``). Legacy flat keys
(``low_conf_threshold``) remain supported for backward compatibility.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from .settings import Settings

# Field schema for the HMI: (key, label, type, options?, min?, max?, step?)
FieldDef = Tuple[str, str, str, Optional[List[str]], Optional[float], Optional[float], Optional[float]]

SECTIONS: List[Tuple[str, str, List[FieldDef]]] = [
    (
        "camera",
        "Camera",
        [
            ("camera.backend", "Backend", "select", ["mock", "picamera2", "v4l2", "genicam"], None, None, None),
            ("camera.device", "Device path", "device_video", None, None, None, None),
            ("camera.width", "Width (px)", "number", None, 320, 4096, 1),
            ("camera.height", "Height (px)", "number", None, 240, 4096, 1),
            ("camera.fps", "FPS", "number", None, 1, 60, 1),
            ("camera.exposure_default", "Default exposure (0=auto)", "number", None, -8, 8, 0.1),
            ("camera.gain_default", "Default gain", "number", None, 0.1, 16, 0.1),
        ],
    ),
    (
        "barcode",
        "Barcode scanner",
        [
            ("barcode.backend", "Backend", "select", ["manual", "evdev", "serial"], None, None, None),
            ("barcode.device", "Evdev device", "device_input", None, None, None, None),
            ("barcode.serial_port", "Serial port", "device_serial", None, None, None, None),
            ("barcode.serial_baud", "Serial baud", "number", None, 1200, 921600, 1),
        ],
    ),
    (
        "lighting",
        "Lighting",
        [
            ("lighting.backend", "Backend", "select", ["none", "gpio", "serial"], None, None, None),
        ],
    ),
    (
        "teaching",
        "Teaching capture",
        [
            ("teaching.frames_per_label", "Frames per EMPTY/FILLED", "number", None, 5, 60, 1),
            ("teaching.condition_sweep", "Vary exposure/gain per frame", "boolean", None, None, None, None),
        ],
    ),
    (
        "inference",
        "Inference",
        [
            ("inference.default_threshold", "Default ROI threshold", "number", None, 0.01, 1, 0.01),
        ],
    ),
    (
        "data_collection",
        "Data collection",
        [
            ("data_collection.low_conf_threshold", "Low-confidence threshold", "number", None, 0, 1, 0.01),
            ("data_collection.pass_sample_rate", "Random PASS sample rate", "number", None, 0, 1, 0.01),
            ("data_collection.save_full_image_on_pass", "Save full image on PASS", "boolean", None, None, None, None),
        ],
    ),
    (
        "storage",
        "Storage",
        [
            ("storage.device", "Storage volume", "storage_device", None, None, None, None),
            ("storage.missing_policy", "When storage missing", "select", ["block", "buffer"], None, None, None),
            ("storage.min_free_mb", "Min free space (MB)", "number", None, 50, 50000, 50),
            ("storage.require_mountpoint", "Require real mountpoint", "boolean", None, None, None, None),
        ],
    ),
    (
        "archiving",
        "Archiving & retention",
        [
            ("archiving.retention_days_full_images", "Keep full images (days)", "number", None, 1, 3650, 1),
            ("archiving.retention_days_exports", "Keep export ZIPs (days)", "number", None, 1, 3650, 1),
        ],
    ),
]

# Legacy DB keys -> canonical dotted keys.
LEGACY_ALIASES = {
    "low_conf_threshold": "data_collection.low_conf_threshold",
    "pass_sample_rate": "data_collection.pass_sample_rate",
    "save_full_image_on_pass": "data_collection.save_full_image_on_pass",
    "storage.ssd2_mount": "storage.mount",
    "storage.ssd3_mount": "storage.mount",
}

ALL_KEYS = [f[0] for _, _, fields in SECTIONS for f in fields]
PERSIST_KEYS = set(ALL_KEYS) | {"storage.mount"}


def defaults_from_settings(settings: Settings) -> Dict[str, Any]:
    """Flatten a Settings object into canonical dotted keys."""
    return {
        "camera.backend": settings.camera.backend,
        "camera.device": settings.camera.device,
        "camera.width": settings.camera.width,
        "camera.height": settings.camera.height,
        "camera.fps": settings.camera.fps,
        "camera.exposure_default": settings.camera.exposure_default,
        "camera.gain_default": settings.camera.gain_default,
        "barcode.backend": settings.barcode.backend,
        "barcode.device": settings.barcode.device,
        "barcode.serial_port": settings.barcode.serial_port,
        "barcode.serial_baud": settings.barcode.serial_baud,
        "lighting.backend": settings.lighting.backend,
        "teaching.frames_per_label": settings.teaching.frames_per_label,
        "teaching.condition_sweep": settings.teaching.condition_sweep,
        "inference.default_threshold": settings.inference.default_threshold,
        "data_collection.low_conf_threshold": settings.data_collection.low_conf_threshold,
        "data_collection.pass_sample_rate": settings.data_collection.pass_sample_rate,
        "data_collection.save_full_image_on_pass": settings.data_collection.save_full_image_on_pass,
        "storage.device": settings.storage.device,
        "storage.mount": str(settings.storage.mount),
        "storage.missing_policy": settings.storage.missing_policy,
        "storage.min_free_mb": settings.storage.min_free_mb,
        "storage.require_mountpoint": settings.storage.require_mountpoint,
        "archiving.retention_days_full_images": settings.archiving.retention_days_full_images,
        "archiving.retention_days_exports": settings.archiving.retention_days_exports,
    }


def _normalize_key(key: str) -> str:
    return LEGACY_ALIASES.get(key, key)


def _coerce_value(key: str, raw: str) -> Any:
    """Parse a stored string into the correct Python type for ``key``."""
    key = _normalize_key(key)
    if key.endswith(".save_full_image_on_pass") or key.endswith(".require_mountpoint") or key.endswith(".condition_sweep"):
        if isinstance(raw, bool):
            return raw
        return str(raw).lower() in ("true", "1", "yes")
    if key.endswith(".backend") or key.endswith(".device") or key.endswith(".serial_port"):
        return str(raw)
    if key.endswith(".mount") or key.endswith("_mount") or key == "storage.device":
        return str(raw).strip()
    if key.endswith(".missing_policy"):
        return str(raw)
    # numeric
    if isinstance(raw, (int, float)):
        return raw
    if "." in str(raw):
        return float(raw)
    return int(raw)


def load_merged(settings: Settings, db) -> Dict[str, Any]:
    """YAML defaults merged with SQLite overrides (canonical keys)."""
    from ..system.mounts import device_for_mount, device_select_value

    merged = defaults_from_settings(settings)
    from ..db.repositories import SettingsRepository

    with db.session() as s:
        stored = SettingsRepository(s).all()
    has_saved_mount = "storage.mount" in stored
    for k, v in stored.items():
        if has_saved_mount and k in ("storage.ssd2_mount", "storage.ssd3_mount"):
            continue
        canon = _normalize_key(k)
        if canon in merged or k in LEGACY_ALIASES or k in PERSIST_KEYS:
            merged[canon] = _coerce_value(canon, v)
    if not has_saved_mount:
        if "storage.ssd2_mount" in stored:
            merged["storage.mount"] = _coerce_value("storage.mount", stored["storage.ssd2_mount"])
        elif "storage.ssd3_mount" in stored:
            merged["storage.mount"] = _coerce_value("storage.mount", stored["storage.ssd3_mount"])
    if not merged.get("storage.device") and merged.get("storage.mount"):
        dev = device_for_mount(str(merged["storage.mount"]))
        if dev:
            merged["storage.device"] = dev
    if merged.get("storage.mount"):
        merged["storage.mount"] = str(merged["storage.mount"]).strip()
    if merged.get("storage.device"):
        merged["storage.device"] = str(merged["storage.device"]).strip()
    return merged


def persist_updates(db, updates: Dict[str, Any]) -> Dict[str, Any]:
    """Write partial updates to SQLite; return canonical keys written."""
    from ..db.repositories import SettingsRepository

    written = {}
    with db.session() as s:
        repo = SettingsRepository(s)
        for key, val in updates.items():
            canon = _normalize_key(key)
            if canon not in PERSIST_KEYS and key not in LEGACY_ALIASES:
                continue
            store_key = canon
            if isinstance(val, bool):
                store_val = json.dumps(val)
            else:
                store_val = str(val)
            repo.set(store_key, store_val)
            written[canon] = _coerce_value(canon, store_val)
        if "storage.mount" in written:
            for legacy in ("storage.ssd2_mount", "storage.ssd3_mount"):
                repo.delete(legacy)
    return written


def apply_to_settings(base: Settings, values: Dict[str, Any]) -> Settings:
    """Build a new Settings from ``base`` with ``values`` (dotted keys) applied."""
    data = base.model_dump(mode="python")

    def set_nested(section: str, field: str, val: Any) -> None:
        if section not in data:
            return
        sec = data[section]
        if not isinstance(sec, dict):
            return
        sec[field] = val

    for key, val in values.items():
        canon = _normalize_key(key)
        if "." not in canon:
            continue
        section, field = canon.split(".", 1)
        set_nested(section, field, val)

    return Settings.model_validate({**data, "config_path": base.config_path})


def schema_for_ui(defaults: Dict[str, Any], current: Dict[str, Any]) -> List[dict]:
    """Sections + fields for the HMI form renderer."""
    out = []
    for sec_id, title, fields in SECTIONS:
        field_list = []
        for f in fields:
            key, label, ftype, options, vmin, vmax, step = f
            field_list.append({
                "key": key,
                "label": label,
                "type": ftype,
                "options": options,
                "min": vmin,
                "max": vmax,
                "step": step,
                "value": current.get(key, defaults.get(key)),
                "default": defaults.get(key),
            })
        out.append({"id": sec_id, "title": title, "fields": field_list})
    return out
