# MVQC — Machine Vision QC Platform (V1: Component Presence)

A local-first machine-vision quality-control platform for industrial
manufacturing. A headless **CM5 production station** (`cm5-101`) performs barcode
reading, image acquisition, ROI extraction, ONNX presence inference, OK/NOK
decisions and data collection behind a **remote web HMI**. A separate **Ubuntu +
RTX training server** owns all model training. They are connected by a **hybrid**
(USB-now, network-ready) model/data sync.

> V1 inspects **component presence** (EMPTY vs FILLED per ROI). OCR, counting,
> color, anomaly and wrong-component inspection are reserved via a plugin seam.

## Roles & hardware

| Node | Role |
|------|------|
| `cm5-101` (CM5, aarch64) | Production station: camera, barcode, inference, data collection, HMI |
| Ubuntu + RTX GPU | Training server: all training, ONNX export, model bundles |

Station storage (the **64 GB eMMC is SSD-1**):

- **SSD-1 / eMMC** — OS, app, SQLite DB, config, logs, cache. *No images.*
- **SSD-2** — full inspection images + daily export ZIPs.
- **SSD-3** — ROI archive (crops + `metadata.json`) + teaching samples.

SSD-2/SSD-3 may be absent at runtime; the app stays up and (by policy) blocks
image writes + alarms the operator, protecting the eMMC.

## Repository layout

```
mvqc/
  app/
    station/        # FastAPI app + inspection engine (the station service)
      api/          # REST + WebSocket + MJPEG routers
      camera/ barcode/ lighting/   # pluggable hardware backends
      inference/ inspectors/ decision/   # ONNX, presence plugin, OK/NOK rules
      core/         # context, event bus, engine, teaching, overlay
      storage/      # mount-aware routing, daily archiver, retention
      data_collection/  # save policy + metadata.json writer
      db/           # SQLAlchemy models, migrations, repositories
      sync/         # USB bundle import (network-ready)
      schemas/      # recipe / manifest / metadata contracts
      web/          # served HMI (dependency-free fallback)
    frontend/       # React + Vite + TS + Konva HMI source
    systemd/        # mvqc-app.service, mvqc-archive.{service,timer}
    scripts/        # provision / mount / eMMC / network / healthcheck
  config/app.yaml   # station configuration
  training-server/  # ingest, datasets, training, export, registry, deploy, pipelines
  requirements.txt  # station runtime deps
```

## Hızlı başlangıç — CM5 (canlı istasyon)

İstasyon zaten kuruluysa (`~/mvqc` mevcut, venv hazır):

```bash
cd ~/mvqc && source .venv/bin/activate
cd app && MVQC_CONFIG=../config/app.yaml python -m station.cli serve
```

Tarayıcı: **http://cm5-101.local:8000** (veya `http://<istasyon-ip>:8000`)

Kapatmak için terminalde `Ctrl+C`. Arka planda systemd kullanıyorsan: `systemctl restart mvqc-app.service`

---

## Quick start — station (ilk kurulum / development)

```bash
cd ~/mvqc   # veya klonladığın dizin
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cd app && MVQC_CONFIG=../config/app.yaml python -m station.cli migrate
cd app && MVQC_CONFIG=../config/app.yaml python -m station.cli serve
# http://localhost:8000  (mock camera works with no hardware)
```

The served HMI at `station/web/index.html` is dependency-free and works
immediately (Help sekmesi dahil). To build the richer React HMI, see `app/frontend/README.md`.

## Provisioning — station (production)

```bash
# 1. App + venv + systemd + eMMC tuning + DB migrate
sudo bash app/scripts/provision.sh

# 2. Persistent SSD mounts by UUID (lsblk -f to find them)
sudo bash app/scripts/mount_drives.sh <ssd2-uuid> <ssd3-uuid>

# 3. Headless host/network (stable address for the remote HMI)
sudo bash app/scripts/network_setup.sh cm5-101 192.168.1.50/24 192.168.1.1 eth0
```

Then set real hardware backends in `config/app.yaml`:

```yaml
camera:  { backend: picamera2 }   # or v4l2 / genicam
barcode: { backend: evdev, device: /dev/input/event0 }
storage: { require_mountpoint: true, missing_policy: block }
```

Install the optional backend libs on the station as needed:
`sudo apt install python3-picamera2` · `pip install evdev pyserial`.

Services:

```bash
systemctl status mvqc-app.service       # the station
systemctl list-timers mvqc-archive.timer # nightly export at 23:55
```

## Operator workflow (HMI)

1. **Products** — create product: name, barcode, surface count, pass rule.
2. **Teaching** — pick product/surface → *Capture snapshot* → draw ROIs (name
   them, e.g. Screw/Cap/Tape) → *Save ROIs* → *Capture EMPTY (~20)* without
   components → *Capture FILLED (~20)* assembled. (~5–10 min onboarding.)
3. Export SSD-3 to the training server, train, and **import the model bundle**
   (Models tab). The product flips to `ready`.
4. **Inspect** — scan barcode (auto-runs) or pick product → annotated result
   image with **red boxes on failed ROIs**, per-ROI confidence, PASS/FAIL banner.
5. **Dashboard** — throughput, pass/fail, storage health, recent inspections.

## Admin / CLI

```bash
python -m station.cli migrate                 # create/upgrade schema
python -m station.cli serve                   # run the server
python -m station.cli healthcheck             # storage/mount status (JSON)
python -m station.cli archive --date 2026-08-01   # build a daily export ZIP
python -m station.cli import-model bundle.zip --by alice  # deploy from USB
```

## Data collection & archiving

- **Always** save FAIL (full image → SSD-2; ROI crops + `metadata.json` → SSD-3).
- **Additionally** save PASS below `low_conf_threshold`.
- **Optionally** save a random `pass_sample_rate` of PASS.
- Thresholds are editable live in **Settings**.
- A nightly timer ZIPs the day's `full_images/`, `roi_archive/`, `metadata/`
  into `SSD-2/exports/YYYY-MM-DD.zip`, verifies it, and applies retention.

## Monthly improvement loop (training server)

`SSD-3 → ingest → train per ROI → export ONNX → registry (gate) → bundle → import`

```bash
cd training-server
python pipelines/monthly_retrain.py --lake data/lake --product Product_A \
    --barcode 8691234567890 --recipe-version 1 --registry registry --out data/bundles
```

Acceptance gate: FILLED recall ≥ 0.99, EMPTY recall ≥ 0.97 before deploy.

## Scalability roadmap

- **V1** single station, presence only, USB sync, per-ROI ONNX on CPU.
- **V1.x** PCIe NPU (Hailo) + INT8; split engine into its own service.
- **V2** networked fleet: central registry, OTA deploy, telemetry — flip the
  already-abstracted `SyncClient` to network mode.
- **V2.x** new inspectors via the plugin seam: OCR, counting, color, anomaly,
  wrong-component.
- **V3** active learning, drift detection, full MLOps, fleet analytics.

## Troubleshooting

| Symptom | Check |
|---------|-------|
| `storage ok=false`, writes blocked | SSD-2/3 mounted? `station.cli healthcheck`; `lsblk -f` |
| Inspection returns 409 "not ready" | Product needs models — import a bundle (Models tab) |
| Camera not opening | `config/app.yaml camera.backend`; device perms (video group) |
| Barcode scans not arriving | scanner backend/device; HMI manual entry always works |
| Bundle import "checksum mismatch" | rebuild the bundle on the server (corrupt transfer) |
