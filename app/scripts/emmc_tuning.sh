#!/usr/bin/env bash
# eMMC longevity tuning: keep transient frame scratch off the eMMC and ensure
# the local app directories exist. Run via provision.sh (best effort).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

mkdir -p "${REPO_ROOT}/database" "${REPO_ROOT}/logs" \
         "${REPO_ROOT}/cache" "${REPO_ROOT}/cache/models" \
         "${REPO_ROOT}/cache/pending" "${REPO_ROOT}/cache/tmp"

# Mount /cache/tmp as tmpfs (RAM) so per-frame scratch never wears the eMMC.
TMP_DIR="${REPO_ROOT}/cache/tmp"
if ! mountpoint -q "${TMP_DIR}"; then
  FSTAB_LINE="tmpfs ${TMP_DIR} tmpfs nodev,nosuid,size=256M 0 0"
  if ! grep -qsF "${TMP_DIR}" /etc/fstab; then
    echo "${FSTAB_LINE}" | sudo tee -a /etc/fstab >/dev/null
    echo "[emmc] added tmpfs entry for ${TMP_DIR}"
  fi
  sudo mount "${TMP_DIR}" || true
fi

echo "[emmc] tuning complete"
