import { useEffect, useRef, useState } from "react";
import { Stage, Layer, Image as KImage, Rect, Text } from "react-konva";
import { api } from "../api";
import type { Geometry, Recipe } from "../types";

interface EditRoi { name: string; geometry: Geometry; }

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
  const draft = useRef<{ x: number; y: number } | null>(null);
  const [draftRect, setDraftRect] = useState<Geometry | null>(null);

  useEffect(() => { api.products().then(setProducts); }, []);

  const selectProduct = async (id: number) => {
    setRecipe(null); setSurfaceId(""); setRois([]);
    try { setRecipe(await api.activeRecipe(id)); }
    catch {
      const recs = await api.recipes(id);
      if (recs.length) setRecipe(await api.recipe(recs[0].id));
    }
  };

  const selectSurface = (sid: number) => {
    setSurfaceId(sid);
    const s = recipe?.surfaces.find((x) => x.id === sid);
    setRois((s?.rois ?? []).map((r) => ({ name: r.name ?? "", geometry: { ...r.geometry } })));
    api.teachStatus(sid).then(setStatus);
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

  const onDown = (e: { target: { getStage: () => unknown }; evt?: MouseEvent | TouchEvent }) => {
    const p = getPointer(e as Parameters<typeof getPointer>[0]);
    if (p) draft.current = p;
  };
  const onMove = (e: { target: { getStage: () => unknown }; evt?: MouseEvent | TouchEvent }) => {
    if (!draft.current) return;
    const p = getPointer(e as Parameters<typeof getPointer>[0]);
    if (!p) return;
    setDraftRect({
      x: Math.min(draft.current.x, p.x), y: Math.min(draft.current.y, p.y),
      w: Math.abs(p.x - draft.current.x), h: Math.abs(p.y - draft.current.y),
    });
  };
  const onUp = () => {
    if (draftRect && draftRect.w > 8 && draftRect.h > 8) {
      setRois([...rois, { name: "", geometry: {
        x: Math.round(draftRect.x / scale), y: Math.round(draftRect.y / scale),
        w: Math.round(draftRect.w / scale), h: Math.round(draftRect.h / scale) } }]);
    }
    draft.current = null; setDraftRect(null);
  };

  const saveRois = async () => {
    if (!surfaceId) return;
    await api.setRois(surfaceId, rois.map((r, i) => ({ name: r.name || null, roi_index: i + 1, geometry: r.geometry })));
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
          <span className="muted">Drag on the image to add a ROI.</span>
          <span style={{ flex: 1 }} />
          <button className="btn secondary" onClick={() => setRois([])}>Clear</button>
          <button className="btn" onClick={saveRois}>Save ROIs</button>
        </div>
        <div className="grid cols-2" style={{ marginTop: 12 }}>
          <Stage width={imgSize.w} height={imgSize.h} onMouseDown={onDown} onMouseMove={onMove} onMouseUp={onUp}
            onTouchStart={onDown} onTouchMove={onMove} onTouchEnd={onUp} style={{ border: "1px solid var(--line)", borderRadius: 8 }}>
            <Layer>
              {img && <KImage image={img} width={imgSize.w} height={imgSize.h} />}
              {rois.map((r, i) => (
                <>
                  <Rect key={`r${i}`} x={r.geometry.x * scale} y={r.geometry.y * scale} width={r.geometry.w * scale} height={r.geometry.h * scale} stroke="#3b82f6" strokeWidth={2} />
                  <Text key={`t${i}`} x={r.geometry.x * scale + 3} y={r.geometry.y * scale + 3} text={r.name || `ROI${i + 1}`} fontSize={13} fill="#3b82f6" />
                </>
              ))}
              {draftRect && <Rect x={draftRect.x} y={draftRect.y} width={draftRect.w} height={draftRect.h} stroke="#22d3ee" strokeWidth={2} dash={[4, 4]} />}
            </Layer>
          </Stage>
          <div>
            <label>ROIs</label>
            {rois.map((r, i) => (
              <div className="row" key={i} style={{ marginBottom: 6 }}>
                <span className="muted" style={{ width: 22 }}>{i + 1}</span>
                <input value={r.name} placeholder="name (e.g. Screw)" onChange={(e) => { const c = [...rois]; c[i] = { ...c[i], name: e.target.value }; setRois(c); }} />
                <button className="btn secondary" onClick={() => setRois(rois.filter((_, j) => j !== i))}>x</button>
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
