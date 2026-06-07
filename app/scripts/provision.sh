#!/usr/bin/env bash
# Provision the MVQC station on a fresh CM5 / Raspberry Pi 5 (Bookworm, aarch64).
# Idempotent: safe to re-run.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VENV="${REPO_ROOT}/.venv"

echo "[provision] repo root: ${REPO_ROOT}"

echo "[provision] system packages"
sudo apt-get update
sudo apt-get install -y \
  python3-venv python3-pip libgl1 libglib2.0-0 sqlite3 \
  python3-picamera2 python3-libcamera libcamera-tools

echo "[provision] python venv (with system site-packages for picamera2/libcamera)"
if [ -d "${VENV}" ] && ! grep -q 'include-system-site-packages = true' "${VENV}/pyvenv.cfg" 2>/dev/null; then
  echo "  enabling system-site-packages on existing venv"
  sed -i 's/include-system-site-packages = false/include-system-site-packages = true/' "${VENV}/pyvenv.cfg" || true
fi
if [ ! -d "${VENV}" ]; then
  python3 -m venv --system-site-packages "${VENV}"
fi
# shellcheck disable=SC1091
source "${VENV}/bin/activate"
pip install --upgrade pip wheel
pip install -r "${REPO_ROOT}/requirements.txt"

echo "[provision] optional hardware backends (best effort)"
pip install evdev pyserial || echo "  (skipped evdev/pyserial)"

echo "[provision] eMMC tuning + directories"
bash "${REPO_ROOT}/app/scripts/emmc_tuning.sh" || true

echo "[provision] database migrate"
MVQC_CONFIG="${REPO_ROOT}/config/app.yaml" "${VENV}/bin/python" -m station.cli migrate

echo "[provision] install systemd units"
sudo cp "${REPO_ROOT}/app/systemd/"*.service /etc/systemd/system/
sudo cp "${REPO_ROOT}/app/systemd/"*.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now mvqc-app.service
sudo systemctl enable --now mvqc-archive.timer

echo "[provision] done. App should be live on port 8000."
