import { useEffect, useRef, useState } from "react";
import { api } from "../api";

export function Models() {
  const [models, setModels] = useState<any[]>([]);
  const [products, setProducts] = useState<any[]>([]);
  const [cov, setCov] = useState<any>(null);
  const [msg, setMsg] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  const load = () => { api.models().then(setModels); api.products().then(setProducts); };
  useEffect(() => { load(); }, []);

  const importBundle = async () => {
    const f = fileRef.current?.files?.[0];
    if (!f) { setMsg("Choose a bundle .zip"); return; }
    try { const r = await api.importBundle(f); setMsg(`Activated ${r.count} models for ${r.product}`); load(); }
    catch (e) { setMsg((e as Error).message); }
  };

  return (
    <>
      <div className="card">
        <h2>Import model bundle (USB)</h2>
        <div className="row"><input type="file" accept=".zip" ref={fileRef} /><button className="btn" onClick={importBundle}>Import &amp; activate</button><span className="muted">{msg}</span></div>
        <div className="muted" style={{ marginTop: 8 }}>Bundle = manifest.json + one ONNX per ROI, produced by the training server.</div>
      </div>
      <div className="card">
        <h2>Deployed models</h2>
        <table>
          <thead><tr><th>Product</th><th>Surface</th><th>ROI</th><th>Version</th><th>Source</th><th>Loaded</th><th /></tr></thead>
          <tbody>{models.map((m) => (
            <tr key={m.roi_id}><td>{m.product || "-"}</td><td>{m.surface_index ?? "-"}</td><td>{m.roi_name || m.roi_id}</td>
              <td>{m.version}</td><td><span className="pill">{m.source}</span></td><td><span className={"dot " + (m.loaded ? "ok" : "nok")} /></td>
              <td>{m.has_rollback && <button className="btn secondary" onClick={async () => { await api.rollback(m.roi_id); load(); }}>Rollback</button>}</td></tr>
          ))}</tbody>
        </table>
      </div>
      <div className="card">
        <h2>Coverage</h2>
        <select onChange={(e) => e.target.value && api.coverage(+e.target.value).then(setCov)} style={{ maxWidth: 280 }}>
          <option value="">--</option>{products.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
        {cov && <div className="muted" style={{ marginTop: 8 }}>Ready: <b style={{ color: cov.ready ? "var(--ok)" : "var(--nok)" }}>{String(cov.ready)}</b> — {cov.covered}/{cov.total} ROIs covered</div>}
      </div>
    </>
  );
}
