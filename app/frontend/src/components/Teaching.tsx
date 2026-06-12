import { useEffect, useRef, useState } from "react";
import { Stage, Layer, Image as KImage, Line, Circle, Rect, Text } from "react-konva";
import { api } from "../api";
import type { Recipe } from "../types";
import { dist, normalizeGeometry, rectFromDrag, type Geometry } from "../geometry";

interface EditRoi { name: string; geometry: Geometry; }

type DrawTool = "polygon" | "rect";

const VERT_R = 3;
const VERT_HIT = 5;
const CLOSE_PX = 5;

export function Teaching() {
  const [products, setProducts] = useState<any[]>([]);
  const [recipe, setRecipe] = useState<Recipe | null>(null);
  const [surfaceId, setSurfaceId] = useState<number | "">("");
  const [img, setImg] = useState<HTMLImageElement | null>(null);
  const [imgSize, setImgSize] = useState({ w: 600, h: 300 });
  const [scale, setScale] = useState(1);
  const [rois, setRois] = useState<EditRoi[]>([]);
  const [progress, setProgress] = useState("");
  const [status, setStatus] = useState<{ EMPTY: number; FILLED: number } | null>(null);
  const [tool, setTool] = useState<DrawTool>("polygon");
  const [draftPts, setDraftPts] = useState<[number, number][]>([]);
  const [draftRect, setDraftRect] = useState<{ x: number; y: number; w: number; h: number } | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const rectStart = useRef<{ x: number; y: number } | null>(null);

  useEffect(() => { api.products().then(setProducts); }, []);

  const selectProduct = async (id: number) => {
    setRecipe(null); setSurfaceId(""); setRois([]); setDraftPts([]);
    try { setRecipe(await api.activeRecipe(id)); }
    catch {
      const recs = await api.recipes(id);
      if (recs.length) setRecipe(await api.recipe(recs[0].id));
    }
  };

  const selectSurface = (sid: number) => {
    setSurfaceId(sid);
    const s = recipe?.surfaces.find((x) => x.id === sid);
    setRois((s?.rois ?? []).map((r) => ({
      name: r.name ?? "",
      geometry: normalizeGeometry(r.geometry as Geometry & { x?: number; y?: number; w?: number; h?: number }),
    })));
    api.teachStatus(sid).then(setStatus);
    setDraftPts([]); setSelected(null);
  };

  const snapshot = async () => {
    const snap = await api.snapshot();
    const image = new window.Image();
    image.onload = () => {
      const maxW = 600; const sc = Math.min(1, maxW / snap.width);
      setScale(sc); setImgSize({ w: snap.width * sc, h: snap.height * sc }); setImg(image);
    };
    image.src = snap.image;
  };

  const getPointer = (e: { target: { getStage: () => any }; evt?: MouseEvent | TouchEvent }) => {
    const stage = e.target.getStage();
    if (!stage) return null;
    const box = stage.container().getBoundingClientRect();
    const evt = e.evt as MouseEvent;
    const clientX = evt.clientX ?? (evt as TouchEvent).changedTouches?.[0]?.clientX;
    const clientY = evt.clientY ?? (evt as TouchEvent).changedTouches?.[0]?.clientY;
    if (clientX == null || clientY == null) return null;
    const sx = stage.width() / box.width;
    const sy = stage.height() / box.height;
    return { x: (clientX - box.left) * sx, y: (clientY - box.top) * sy };
  };

  const toImage = (sx: number, sy: number): [number, number] => [
    Math.round(sx / scale), Math.round(sy / scale),
  ];

  const closePolygon = (pts: [number, number][]) => {
    if (pts.length < 3) return;
    setRois([...rois, { name: "", geometry: { points: pts.map((p) => [...p] as [number, number]) } }]);
    setDraftPts([]);
  };

  const onDown = (e: { target: { getStage: () => unknown }; evt?: MouseEvent | TouchEvent }) => {
    const p = getPointer(e as Parameters<typeof getPointer>[0]);
    if (!p) return;
    if (tool === "rect") {
      rectStart.current = p;
      return;
    }
    const imgPt = toImage(p.x, p.y);
    if (draftPts.length >= 3 && dist(imgPt, draftPts[0]) < CLOSE_PX / scale) {
      closePolygon(draftPts);
      return;
    }
    setDraftPts([...draftPts, imgPt]);
  };

  const onMove = (e: { target: { getStage: () => unknown }; evt?: MouseEvent | TouchEvent }) => {
    if (tool !== "rect" || !rectStart.current) return;
    const p = getPointer(e as Parameters<typeof getPointer>[0]);
    if (!p) return;
    const s = rectStart.current;
    setDraftRect({
      x: Math.min(s.x, p.x), y: Math.min(s.y, p.y),
      w: Math.abs(p.x - s.x), h: Math.abs(p.y - s.y),
    });
  };

  const onUp = () => {
    if (tool === "rect" && draftRect && draftRect.w > 8 && draftRect.h > 8) {
      const g = rectFromDrag(
        draftRect.x, draftRect.y,
        draftRect.x + draftRect.w, draftRect.y + draftRect.h,
        scale,
      );
      setRois([...rois, { name: "", geometry: g }]);
    }
    rectStart.current = null;
    setDraftRect(null);
  };

  const onDblClick = () => {
    if (tool === "polygon" && draftPts.length >= 3) closePolygon(draftPts);
  };

  const moveVertex = (roiIdx: number, vIdx: number, sx: number, sy: number) => {
    const c = [...rois];
    const pts = c[roiIdx].geometry.points.map((p) => [...p] as [number, number]);
    pts[vIdx] = toImage(sx, sy);
    c[roiIdx] = { ...c[roiIdx], geometry: { points: pts } };
    setRois(c);
  };

  const flatPts = (pts: [number, number][]) => pts.flatMap((p) => [p[0] * scale, p[1] * scale]);

  const saveRois = async () => {
    if (!surfaceId) return;
    await api.setRois(surfaceId, rois.map((r, i) => ({
      name: r.name || null, roi_index: i + 1, geometry: r.geometry,
    })));
  };

  const teach = async (label: string) => {
    if (!surfaceId) return;
    const r = await api.teach(surfaceId, label);
    setProgress(`${label}: ${r.frames_captured} frames`);
    api.teachStatus(surfaceId).then(setStatus);
  };

  return (
    <>
      <div className="card">
        <h2>1 · Select product &amp; surface</h2>
        <div className="grid cols-2">
          <div><label>Product</label>
            <select onChange={(e) => e.target.value && selectProduct(+e.target.value)}>
              <option value="">--</option>{products.map((p) => <option key={p.id} value={p.id}>{p.name} ({p.status})</option>)}</select></div>
          <div><label>Surface</label>
            <select value={surfaceId} onChange={(e) => e.target.value && selectSurface(+e.target.value)}>
              <option value="">--</option>{recipe?.surfaces.map((s) => <option key={s.id} value={s.id}>Surface {s.surface_index} {s.name ? `· ${s.name}` : ""}</option>)}</select></div>
        </div>
      </div>

      <div className="card">
        <h2>2 · Draw ROIs</h2>
        <div className="row">
          <button className="btn secondary" onClick={snapshot}>Capture snapshot</button>
          <button className={`btn secondary${tool === "polygon" ? " ok" : ""}`} onClick={() => { setTool("polygon"); setDraftPts([]); }}>Polygon</button>
          <button className={`btn secondary${tool === "rect" ? " ok" : ""}`} onClick={() => { setTool("rect"); setDraftPts([]); }}>Rectangle</button>
          <span className="muted">
            {tool === "polygon"
              ? "Click points around the part; double-click or click first point to close."
              : "Drag to draw a rectangle."}
          </span>
          <span style={{ flex: 1 }} />
          <button className="btn secondary" onClick={() => { setRois([]); setDraftPts([]); }}>Clear</button>
          <button className="btn" onClick={saveRois}>Save ROIs</button>
        </div>
        <div className="grid cols-2" style={{ marginTop: 12 }}>
          <Stage width={imgSize.w} height={imgSize.h}
            onMouseDown={onDown} onMouseMove={onMove} onMouseUp={onUp} onDblClick={onDblClick}
            onTouchStart={onDown} onTouchMove={onMove} onTouchEnd={onUp}
            style={{ border: "1px solid var(--line)", borderRadius: 8 }}>
            <Layer>
              {img && <KImage image={img} width={imgSize.w} height={imgSize.h} />}
              {rois.map((r, i) => (
                <Line key={`l${i}`}
                  points={flatPts(r.geometry.points)}
                  closed={true}
                  stroke={selected === i ? "#22d3ee" : "#3b82f6"}
                  strokeWidth={2}
                  onClick={() => setSelected(i)}
                />
              ))}
              {rois.map((r, i) => {
                const p = r.geometry.points[0];
                return (
                  <Text key={`t${i}`} x={p[0] * scale + 3} y={p[1] * scale + 3}
                    text={r.name || `ROI${i + 1}`} fontSize={13} fill="#3b82f6"
                    onClick={() => setSelected(i)} />
                );
              })}
              {selected != null && rois[selected]?.geometry.points.map((p, vi) => (
                <Circle key={`v${selected}-${vi}`}
                  x={p[0] * scale} y={p[1] * scale} radius={VERT_R}
                  fill="#22d3ee" stroke="#fff" strokeWidth={1} draggable
                  onDragMove={(e) => moveVertex(selected, vi, e.target.x(), e.target.y())}
                  onDragEnd={(e) => moveVertex(selected, vi, e.target.x(), e.target.y())}
                />
              ))}
              {draftPts.length > 0 && (
                <Line points={flatPts(draftPts)} stroke="#22d3ee" strokeWidth={2} dash={[6, 4]} />
              )}
              {draftPts.map((p, i) => (
                <Circle key={`d${i}`} x={p[0] * scale} y={p[1] * scale} radius={VERT_R}
                  fill={i === 0 ? "#22d3ee" : "#3b82f6"} />
              ))}
              {draftRect && <Rect x={draftRect.x} y={draftRect.y} width={draftRect.w} height={draftRect.h}
                stroke="#22d3ee" strokeWidth={2} dash={[4, 4]} />}
            </Layer>
          </Stage>
          <div>
            <label>ROIs</label>
            {rois.map((r, i) => (
              <div className="row" key={i} style={{ marginBottom: 6 }}>
                <span className="muted" style={{ width: 22 }}>{i + 1}</span>
                <input value={r.name} placeholder="name (e.g. Screw)"
                  onFocus={() => setSelected(i)}
                  onChange={(e) => { const c = [...rois]; c[i] = { ...c[i], name: e.target.value }; setRois(c); }} />
                <button className="btn secondary" onClick={() => { setRois(rois.filter((_, j) => j !== i)); if (selected === i) setSelected(null); }}>x</button>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="card">
        <h2>3 · Teach EMPTY / FILLED</h2>
        <div className="row">
          <button className="btn nok" onClick={() => teach("EMPTY")}>Capture EMPTY (~20)</button>
          <button className="btn ok" onClick={() => teach("FILLED")}>Capture FILLED (~20)</button>
          <span style={{ flex: 1 }} /><span className="muted">{progress}</span>
        </div>
        {status && <div className="muted" style={{ marginTop: 10 }}>Samples — EMPTY: {status.EMPTY} · FILLED: {status.FILLED}</div>}
        <div className="muted" style={{ marginTop: 8 }}>Then export SSD-3 to the training server, train, and import the bundle in Models.</div>
      </div>
    </>
  );
}
