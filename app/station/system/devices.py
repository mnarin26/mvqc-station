"""Discover hardware device paths for the settings UI."""

from __future__ import annotations

import glob
import os
import subprocess
from pathlib import Path
from typing import List


def list_video_devices() -> List[dict]:
    """Return capture-capable video nodes for the camera device dropdown."""
    devices: List[dict] = []
    seen = set()

    # Prefer v4l2-ctl names when available.
    try:
        out = subprocess.run(
            ["v4l2-ctl", "--list-devices"],
            capture_output=True, text=True, timeout=5,
        )
        if out.returncode == 0 and out.stdout.strip():
            block_name = ""
            for line in out.stdout.splitlines():
                if not line.startswith("\t") and line.strip():
                    block_name = line.strip().rstrip(":")
                elif line.strip().startswith("/dev/video"):
                    path = line.strip()
                    if path not in seen:
                        seen.add(path)
                        devices.append({"path": path, "label": f"{path} ({block_name})"})
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass

    for path in sorted(glob.glob("/dev/video*")):
        if path in seen:
            continue
        # Skip obvious non-capture ISP nodes when unlabeled.
        devices.append({"path": path, "label": path})

    return devices


def list_input_devices() -> List[dict]:
    """Return evdev input nodes (barcode scanners often appear as keyboard HID)."""
    devices: List[dict] = []
    for path in sorted(glob.glob("/dev/input/event*")):
        label = path
        name = _evdev_name(path)
        if name:
            label = f"{path} ({name})"
        devices.append({"path": path, "label": label})
    return devices


def _evdev_name(path: str) -> str | None:
    try:
        from evdev import InputDevice

        return InputDevice(path).name
    except Exception:
        return None


def list_serial_ports() -> List[dict]:
    """Return common serial/USB CDC ports."""
    ports: List[dict] = []
    for pattern in ("/dev/ttyUSB*", "/dev/ttyACM*", "/dev/serial/by-id/*"):
        for path in sorted(glob.glob(pattern)):
            if os.path.exists(path):
                ports.append({"path": path, "label": path})
    return ports
