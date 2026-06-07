#!/usr/bin/env bash
# Quick station health probe for cron/monitoring.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MVQC_CONFIG="${REPO_ROOT}/config/app.yaml" \
  "${REPO_ROOT}/.venv/bin/python" -m station.cli healthcheck
