"""Discover storage volumes and resolve device selections for MVQC."""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

DEVICE_PREFIX = "device:"
AUTO_PREFIX = "__auto__:"  # legacy UI values

_SKIP_FSTYPES = frozenset({
    "swap", "tmpfs", "squashfs", "devtmpfs", "devpts", "proc", "sysfs", "cgroup2",
})
_USABLE_FSTYPES = frozenset({"ext4", "btrfs", "xfs", "ntfs", "exfat", "vfat", ""})
_SYSTEM_MOUNT_PREFIXES = ("/boot/firmware", "/boot")
_LAYOUT_SUBDIRS = ("full_images", "exports", "roi_archive", "teaching")


def device_select_value(device: str) -> str:
    return f"{DEVICE_PREFIX}{device}"


def parse_device_select(value: str) -> str:
    """Extract ``/dev/...`` from a UI/API selection value."""
    raw = str(value).strip()
    if raw.startswith(DEVICE_PREFIX):
        return raw[len(DEVICE_PREFIX):]
    if raw.startswith(AUTO_PREFIX):
        return raw[len(AUTO_PREFIX):]
    if raw.startswith("/dev/"):
        return raw
    return ""


def _free_mb(path: Path) -> float:
    try:
        return shutil.disk_usage(path).free / (1024 * 1024)
    except OSError:
        return 0.0


def _total_mb(path: Path) -> float:
    try:
        return shutil.disk_usage(path).total / (1024 * 1024)
    except OSError:
        return 0.0


def _writable(path: Path) -> bool:
    try:
        return path.is_dir() and os.access(path, os.W_OK)
    except OSError:
        return False


def _mounted(path: Path) -> bool:
    try:
        return path.exists() and os.path.ismount(path)
    except OSError:
        return False


def _transport_label(tran: str | None, rm: bool) -> str:
    if tran == "usb":
        return "USB"
    if tran == "nvme":
        return "NVMe"
    if tran == "mmc":
        return "eMMC/SD"
    if tran == "sata":
        return "SATA"
    return "Removable" if rm else "Disk"


def _partition_role(mount_path: str | None, name: str) -> str:
    if mount_path == "/":
        return "system"
    if mount_path and any(mount_path == p or mount_path.startswith(p + "/") for p in _SYSTEM_MOUNT_PREFIXES):
        return "boot"
    if name.startswith("mmcblk0"):
        return "emmc"
    return "data"


def _lsblk_tree() -> List[dict]:
    try:
        out = subprocess.run(
            ["lsblk", "-J", "-o", "NAME,SIZE,TYPE,FSTYPE,LABEL,UUID,MOUNTPOINTS,MODEL,TRAN,RM,PKNAME"],
            capture_output=True, text=True, timeout=5,
        )
        if out.returncode == 0 and out.stdout.strip():
            return json.loads(out.stdout).get("blockdevices", [])
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError, json.JSONDecodeError):
        logger.exception("lsblk failed")
    return []


def _first_mountpoint(node: dict) -> Optional[str]:
    for mp in node.get("mountpoints") or []:
        if mp and not str(mp).startswith("["):
            return mp
    mp = node.get("mountpoint")
    return mp if mp and not str(mp).startswith("[") else None


def device_exists(device: str) -> bool:
    return bool(device) and Path(device).exists()


def list_storage_devices() -> List[dict]:
    """All usable block partitions: USB, NVMe, eMMC, mounted or not."""
    devices: List[dict] = []
    for node in _lsblk_tree():
        _walk_partitions(node, None, devices)
    devices.sort(key=lambda d: (
        not d["recommended"],
        d["role"] == "system",
        d["role"] == "boot",
        not d["mounted"],
        -d.get("total_mb", 0),
    ))
    return devices


def _walk_partitions(node: dict, parent: dict | None, out: List[dict]) -> None:
    typ = node.get("type")
    if typ in ("disk", "part"):
        if typ == "part":
            entry = _partition_entry(node, parent)
            if entry:
                out.append(entry)
        for child in node.get("children") or []:
            _walk_partitions(child, node, out)
        return
    for child in node.get("children") or []:
        _walk_partitions(child, node, out)


def _partition_entry(part: dict, disk: dict | None) -> Optional[dict]:
    name = part.get("name") or ""
    if part.get("type") != "part":
        return None

    fstype = (part.get("fstype") or "").lower()
    if fstype in _SKIP_FSTYPES:
        return None
    if fstype and fstype not in _USABLE_FSTYPES:
        return None

    dev_path = f"/dev/{name}"
    vol_label = part.get("label") or ""
    model = ((disk or {}).get("model") or part.get("model") or "").strip()
    size = part.get("size") or (disk or {}).get("size") or "?"
    tran = (disk or {}).get("tran") or part.get("tran")
    removable = bool((disk or {}).get("rm") or part.get("rm"))
    transport = _transport_label(tran, removable)
    mount_path = _first_mountpoint(part)
    role = _partition_role(mount_path, name)

    if role == "boot":
        return None

    friendly = vol_label or model or dev_path
    display_bits = [friendly, transport, size]
    if fstype:
        display_bits.append(fstype.upper())
    if mount_path:
        display_bits.append(f"→ {mount_path}")
    else:
        display_bits.append("not mounted")

    recommended = (
        role == "data"
        and fstype in ("ext4", "btrfs", "xfs")
        and (mount_path is not None or removable)
    )
    selectable = role not in ("boot",)  # boot partition not selectable
    if role == "system":
        display_bits.append("system disk")

    mp = Path(mount_path) if mount_path else None
    if mount_path:
        status = "ready"
    elif fstype:
        status = "needs_mount"
    else:
        status = "unformatted"

    return {
        "id": dev_path,
        "device": dev_path,
        "name": friendly,
        "display_name": " · ".join(display_bits),
        "size": size,
        "fstype": fstype,
        "label": vol_label,
        "model": model,
        "transport": transport,
        "role": role,
        "removable": removable,
        "uuid": part.get("uuid") or "",
        "mounted": bool(mount_path),
        "mount_path": mount_path,
        "select_value": device_select_value(dev_path),
        "selectable": selectable,
        "recommended": recommended,
        "status": status,
        "writable": _writable(mp) if mp else False,
        "free_mb": round(_free_mb(mp), 1) if mp else 0.0,
        "total_mb": round(_total_mb(mp), 1) if mp else 0.0,
    }


def device_mountpoint(device: str) -> Optional[str]:
    dev_name = device.rsplit("/", 1)[-1]

    def walk(nodes: List[dict]) -> Optional[str]:
        for node in nodes:
            if node.get("name") == dev_name:
                return _first_mountpoint(node)
            found = walk(node.get("children") or [])
            if found:
                return found
        return None

    return walk(_lsblk_tree())


def device_for_mount(mount: str) -> Optional[str]:
    target = mount.rstrip("/") or "/"

    def walk(nodes: List[dict]) -> Optional[str]:
        for node in nodes:
            if node.get("type") == "part":
                mp = _first_mountpoint(node)
                if mp and (mp == target or mp.rstrip("/") == target):
                    return f"/dev/{node.get('name')}"
            found = walk(node.get("children") or [])
            if found:
                return found
        return None

    return walk(_lsblk_tree())


def ensure_layout(mount: str | Path) -> None:
    mp = Path(mount)
    if not mp.exists() or not _writable(mp):
        return
    for sub in _LAYOUT_SUBDIRS:
        (mp / sub).mkdir(parents=True, exist_ok=True)


def resolve_device_selection(value: str, fallback_mount: str) -> Dict[str, str]:
    """Resolve a UI selection to ``{device, mount}`` and ensure data folders exist."""
    device = parse_device_select(value)
    if not device:
        mount = str(value).strip()
        if mount.startswith("/"):
            dev = device_for_mount(mount) or ""
            if dev and device_exists(dev):
                ensure_layout(mount)
                return {"device": dev, "mount": mount}
        raise ValueError(f"invalid storage selection: {value}")

    if not device.startswith("/dev/"):
        raise ValueError(f"invalid storage device: {device}")

    existing = device_mountpoint(device)
    if existing:
        ensure_layout(existing)
        return {"device": device, "mount": existing}

    if not device_exists(device):
        raise ValueError(f"storage device not present: {device}")

    mount_partition(device, fallback_mount)
    return {"device": device, "mount": fallback_mount}


def mount_partition(device: str, mountpoint: str, *, persist_fstab: bool = True) -> str:
    mp = Path(mountpoint)
    subprocess.run(["sudo", "mkdir", "-p", str(mp)], check=True, timeout=30)

    if _mounted(mp) and _writable(mp):
        # Remount correct device if mountpoint holds a different volume.
        current = device_for_mount(str(mp))
        if current == device or current is None:
            ensure_layout(mp)
            return str(mp)

    uid = os.getuid()
    gid = os.getgid()
    subprocess.run(["sudo", "umount", str(mp)], check=False, timeout=30)
    subprocess.run(["sudo", "mount", device, str(mp)], check=True, timeout=30)
    subprocess.run(["sudo", "chown", f"{uid}:{gid}", str(mp)], check=True, timeout=30)

    uuid = _device_uuid(device)
    if persist_fstab and uuid:
        _ensure_fstab(uuid, str(mp))

    ensure_layout(mp)
    logger.info("Mounted %s at %s", device, mp)
    return str(mp)


def _device_uuid(device: str) -> str:
    try:
        out = subprocess.run(["lsblk", "-no", "UUID", device], capture_output=True, text=True, timeout=5)
        if out.returncode == 0:
            return out.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    return ""


def _ensure_fstab(uuid: str, mountpoint: str) -> None:
    line = f"UUID={uuid} {mountpoint} auto defaults,nofail,x-systemd.device-timeout=10 0 2"
    try:
        fstab = Path("/etc/fstab").read_text(encoding="utf-8")
    except OSError:
        return
    if f"UUID={uuid}" in fstab:
        return
    subprocess.run(["sudo", "sh", "-c", f"echo '{line}' >> /etc/fstab"], check=True, timeout=10)


def sync_storage_paths(device: str, mount: str, fallback_mount: str) -> Dict[str, str]:
    """Refresh mount path from device at runtime; detect absent devices."""
    if not device:
        return {"device": "", "mount": mount, "present": False, "needs_selection": True}
    if not device_exists(device):
        return {"device": device, "mount": mount, "present": False, "needs_selection": True}
    mp = device_mountpoint(device)
    if mp:
        ensure_layout(mp)
        return {"device": device, "mount": mp, "present": True, "needs_selection": False}
    try:
        resolved = resolve_device_selection(device_select_value(device), fallback_mount)
        return {**resolved, "present": True, "needs_selection": False}
    except (OSError, subprocess.CalledProcessError, ValueError) as exc:
        logger.warning("could not sync storage for %s: %s", device, exc)
        return {"device": device, "mount": mount, "present": True, "needs_selection": True}


def list_storage_mountpoints(extra_paths: List[str] | None = None) -> List[dict]:
    """Compatibility wrapper — device list is the primary source for the UI."""
    items = list_storage_devices()
    if extra_paths:
        known = {d.get("mount_path") for d in items} | {d["device"] for d in items}
        for raw in extra_paths:
            path = str(raw).strip()
            if not path or path in known or path.startswith(DEVICE_PREFIX):
                continue
            dev = device_for_mount(path) or ""
            items.append({
                "path": path,
                "device": dev,
                "display_name": f"{path} · configured",
                "select_value": device_select_value(dev) if dev else path,
                "selectable": bool(dev),
                "status": "configured",
                "recommended": False,
                "mounted": Path(path).exists() and _mounted(Path(path)),
                "writable": _writable(Path(path)) if Path(path).exists() else False,
                "free_mb": round(_free_mb(Path(path)), 1) if Path(path).exists() else 0.0,
                "total_mb": 0.0,
            })
    return items
