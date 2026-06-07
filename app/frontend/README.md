# MVQC HMI (React + Vite + TypeScript + Konva)

Remote web operator interface for the MVQC station. Talks to the station's
FastAPI backend (REST + WebSocket + MJPEG).

## Develop

```bash
npm install
npm run dev          # http://localhost:5173, proxies /api, /ws, /stream to :8000
```

Run the station backend separately:

```bash
cd .. && MVQC_CONFIG=../config/app.yaml python -m station.cli serve
```

## Build (deploy to the station)

```bash
npm run build        # outputs static assets to ../station/web (served by FastAPI)
```

> The repository ships a dependency-free fallback HMI at `station/web/index.html`
> so the station is usable before this app is built. Running `npm run build`
> replaces it with the React build.

## Screens

- Dashboard — throughput, pass/fail, storage health, recent inspections
- Products — create product (name, barcode, surfaces, pass rule)
- Teaching — snapshot, draw ROIs (Konva), EMPTY/FILLED auto-capture
- Inspect — scan/select, run, annotated result image (red/green boxes), PASS/FAIL
- Models — import bundle (USB), view deployments, rollback, coverage
- Settings — data-collection thresholds
