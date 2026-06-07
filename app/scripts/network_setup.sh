#!/usr/bin/env bash
# Headless network + host configuration for the CM5 station.
# Sets hostname, ensures SSH is enabled, and (optionally) a static IP via
# NetworkManager so the remote HMI is reachable at a stable address.
#
# Usage:
#   sudo ./network_setup.sh <hostname> [static_ip/cidr] [gateway] [iface]
# Example:
#   sudo ./network_setup.sh cm5-101 192.168.1.50/24 192.168.1.1 eth0
set -euo pipefail

HOSTNAME_NEW="${1:-cm5-101}"
STATIC_CIDR="${2:-}"
GATEWAY="${3:-}"
IFACE="${4:-eth0}"

echo "[net] setting hostname -> ${HOSTNAME_NEW}"
sudo hostnamectl set-hostname "${HOSTNAME_NEW}"

echo "[net] enabling SSH"
sudo systemctl enable --now ssh 2>/dev/null || sudo raspi-config nonint do_ssh 0 || true

if [ -n "${STATIC_CIDR}" ]; then
  echo "[net] configuring static IP ${STATIC_CIDR} on ${IFACE} via NetworkManager"
  CON="mvqc-${IFACE}"
  sudo nmcli con add type ethernet ifname "${IFACE}" con-name "${CON}" 2>/dev/null || true
  sudo nmcli con mod "${CON}" ipv4.addresses "${STATIC_CIDR}" ipv4.method manual
  [ -n "${GATEWAY}" ] && sudo nmcli con mod "${CON}" ipv4.gateway "${GATEWAY}"
  sudo nmcli con mod "${CON}" ipv4.dns "8.8.8.8 1.1.1.1"
  sudo nmcli con up "${CON}" || echo "[net] bring up after reboot"
fi

echo "[net] done. HMI will be at http://${HOSTNAME_NEW}.local:8000 (or the static IP)."
