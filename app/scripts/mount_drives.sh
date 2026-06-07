#!/usr/bin/env bash
# Helper to set up persistent mountpoints for SSD-2 and SSD-3 by UUID.
# Usage: sudo ./mount_drives.sh <ssd2-uuid> <ssd3-uuid>
# Find UUIDs with: lsblk -f
set -euo pipefail

SSD2_UUID="${1:-}"
SSD3_UUID="${2:-}"

if [ -z "${SSD2_UUID}" ] || [ -z "${SSD3_UUID}" ]; then
  echo "Usage: sudo $0 <ssd2-uuid> <ssd3-uuid>"
  echo "Discover UUIDs with: lsblk -f"
  exit 1
fi

sudo mkdir -p /mnt/ssd2 /mnt/ssd3

add_fstab() {
  local uuid="$1" mnt="$2"
  if ! grep -qsF "UUID=${uuid}" /etc/fstab; then
    echo "UUID=${uuid} ${mnt} ext4 defaults,nofail,x-systemd.device-timeout=10 0 2" \
      | sudo tee -a /etc/fstab >/dev/null
    echo "[mount] added fstab entry: ${mnt}"
  fi
}

# 'nofail' ensures the station still boots when a drive is absent.
add_fstab "${SSD2_UUID}" /mnt/ssd2
add_fstab "${SSD3_UUID}" /mnt/ssd3

sudo systemctl daemon-reload
sudo mount -a || true
echo "[mount] done. Verify with: df -h /mnt/ssd2 /mnt/ssd3"
