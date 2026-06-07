"""Tests for storage volume discovery, selection persistence, and absent detection."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from station.config.runtime_settings import load_merged, persist_updates
from station.config.settings import load_settings
from station.db.database import Database
from station.storage.manager import StorageManager
from station.system import mounts as mounts_mod

MOCK_LSBLK = {
    "blockdevices": [
        {
            "name": "sda",
            "size": "29.7G",
            "type": "disk",
            "model": "Mass-Storage",
            "tran": "usb",
            "rm": True,
            "children": [
                {
                    "name": "sda1",
                    "size": "29.7G",
                    "type": "part",
                    "fstype": "ext4",
                    "label": "mvqc-ssd2",
                    "mountpoints": [],
                    "rm": True,
                }
            ],
        },
        {
            "name": "sdb",
            "size": "7.2G",
            "type": "disk",
            "model": "TransMemory",
            "tran": "usb",
            "rm": True,
            "children": [
                {
                    "name": "sdb1",
                    "size": "7.2G",
                    "type": "part",
                    "fstype": "vfat",
                    "label": "",
                    "mountpoints": ["/media/test/FLASH-A"],
                    "rm": True,
                }
            ],
        },
        {
            "name": "mmcblk0",
            "size": "58G",
            "type": "disk",
            "tran": "mmc",
            "rm": False,
            "children": [
                {
                    "name": "mmcblk0p1",
                    "size": "512M",
                    "type": "part",
                    "fstype": "vfat",
                    "label": "bootfs",
                    "mountpoints": ["/boot/firmware"],
                    "rm": False,
                },
                {
                    "name": "mmcblk0p2",
                    "size": "57G",
                    "type": "part",
                    "fstype": "ext4",
                    "label": "rootfs",
                    "mountpoints": ["/"],
                    "rm": False,
                },
            ],
        },
        {
            "name": "nvme0n1",
            "size": "256G",
            "type": "disk",
            "model": "Samsung SSD",
            "tran": "nvme",
            "rm": False,
            "children": [
                {
                    "name": "nvme0n1p1",
                    "size": "256G",
                    "type": "part",
                    "fstype": "ext4",
                    "label": "nvme-data",
                    "mountpoints": ["/mnt/nvme"],
                    "rm": False,
                }
            ],
        },
    ]
}


@pytest.fixture
def mock_lsblk():
    with patch.object(mounts_mod, "_lsblk_tree", return_value=MOCK_LSBLK["blockdevices"]):
        yield


def test_lists_usb_nvme_emmc(mock_lsblk):
    devices = mounts_mod.list_storage_devices()
    ids = {d["device"] for d in devices}
    assert "/dev/sda1" in ids
    assert "/dev/sdb1" in ids
    assert "/dev/nvme0n1p1" in ids
    assert "/dev/mmcblk0p2" in ids
    assert "/dev/mmcblk0p1" not in ids  # boot not selectable


def test_select_value_is_stable_device_key(mock_lsblk):
    devices = {d["device"]: d for d in mounts_mod.list_storage_devices()}
    assert devices["/dev/sda1"]["select_value"] == "device:/dev/sda1"
    assert devices["/dev/sdb1"]["mount_path"] == "/media/test/FLASH-A"


def test_resolve_mounted_usb(mock_lsblk):
    result = mounts_mod.resolve_device_selection("device:/dev/sdb1", "/mnt/mvqc")
    assert result == {"device": "/dev/sdb1", "mount": "/media/test/FLASH-A"}


def test_resolve_unmounted_mounts(mock_lsblk, tmp_path):
    fallback = str(tmp_path / "mvqc")
    with patch.object(mounts_mod, "device_exists", return_value=True), \
         patch.object(mounts_mod, "mount_partition", return_value=fallback) as mount:
        result = mounts_mod.resolve_device_selection("device:/dev/sda1", fallback)
    mount.assert_called_once_with("/dev/sda1", fallback)
    assert result["device"] == "/dev/sda1"
    assert result["mount"] == fallback


def test_device_for_mount(mock_lsblk):
    assert mounts_mod.device_for_mount("/media/test/FLASH-A") == "/dev/sdb1"


def test_absent_device_needs_selection(mock_lsblk, tmp_path):
    settings = load_settings(Path(__file__).resolve().parents[2] / "config" / "app.yaml")
    settings.storage.device = "/dev/sdb1"
    settings.storage.mount = Path("/media/test/FLASH-A")

    with patch.object(mounts_mod, "device_exists", return_value=False):
        health = StorageManager(settings).health()

    assert health["ok"] is False
    assert health["needs_selection"] is True
    assert health["absent"] is True


def test_persist_device_switch_and_reload(mock_lsblk, tmp_path):
    cfg = tmp_path / "app.yaml"
    db_path = tmp_path / "station.db"
    cfg.write_text(
        (Path(__file__).resolve().parents[2] / "config" / "app.yaml").read_text(),
        encoding="utf-8",
    )
    settings = load_settings(cfg)
    settings.paths.database = db_path
    db = Database(db_path)
    db.migrate()

    with patch.object(mounts_mod, "device_exists", return_value=True), \
         patch.object(mounts_mod, "mount_partition", return_value="/mnt/mvqc") as mount:
        persist_updates(db, {
            "storage.device": "device:/dev/sda1",
            "storage.mount": "/mnt/mvqc",
        })
        mount.assert_not_called()  # resolve happens in API layer

    persist_updates(db, {"storage.device": "/dev/sdb1", "storage.mount": "/media/test/FLASH-A"})
    merged = load_merged(settings, db)
    assert merged["storage.device"] == "/dev/sdb1"
    assert merged["storage.mount"] == "/media/test/FLASH-A"


def test_api_resolve_persists_both_fields(mock_lsblk, tmp_path):
    from station.api import system as system_mod

    class Ctx:
        class settings:
            storage = type("S", (), {"mount": Path("/mnt/mvqc")})()

    with patch.object(system_mod, "resolve_device_selection", return_value={
        "device": "/dev/sdb1", "mount": "/media/test/FLASH-A",
    }) as resolve:
        out = system_mod._resolve_storage_mounts({"storage.device": "device:/dev/sdb1"}, Ctx())
    resolve.assert_called_once()
    assert out["storage.device"] == "/dev/sdb1"
    assert out["storage.mount"] == "/media/test/FLASH-A"


def test_ensure_layout_creates_subdirs(tmp_path):
    root = tmp_path / "data"
    root.mkdir()
    mounts_mod.ensure_layout(root)
    for name in ("full_images", "exports", "roi_archive", "teaching"):
        assert (root / name).is_dir()
