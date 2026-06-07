import { useEffect, useState } from "react";
import { api } from "../api";
import type { InspectResult } from "../types";

export function Inspect({ lastScan }: { lastScan: string | null }) {
  const [products, setProducts] = useState<any[]>([]);
  const [barcode, setBarcode] = useState("");
  const [productId, setProductId] = useState<number | "">("");
  const [result, setResult] = useState<InspectResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => { api.products().then(setProducts); }, []);

  // Auto-run when a hardware scan arrives.
  useEffect(() => {
    if (lastScan) { setBarcode(lastScan); run(lastScan); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lastScan]);

  const run = async (bc?: string) => {
    const body: any = {};
    const code = bc ?? barcode;
    if (code.trim()) body.barcode = code.trim();
    else if (productId) body.product_id = productId;
    else { setErr("Scan a barcode or pick a product"); return; }
    setBusy(true); setErr(null);
    try { setResult(await api.inspect(body)); }
    catch (e) { setErr((e as Error).message); setResult(null); }
    finally { setBusy(false); }
  };

  return (
    <>
      <div className="card">
        <h2>Inspect</h2>
        <div className="row">
          <div style={{ flex: 1 }}><label>Barcode (scan to auto-run)</label>
            <input value={barcode} onChange={(e) => setBarcode(e.target.value)} onKeyDown={(e) => e.key === "Enter" && run()} placeholder="scan or type barcode" /></div>
          <div style={{ width: 240 }}><label>or Product</label>
            <select value={productId} onChange={(e) => setProductId(e.target.value ? +e.target.value : "")}>
              <option value="">--</option>{products.map((p) => <option key={p.id} value={p.id}>{p.name} ({p.status})</option>)}</select></div>
          <div style={{ alignSelf: "flex-end" }}><button className="btn" disabled={busy} onClick={() => run()}>Run inspection</button></div>
        </div>
        {err && <div style={{ color: "var(--nok)", marginTop: 8 }}>{err}</div>}
      </div>

      <div className="card"><h2>Live preview</h2><img className="preview" src="/stream/preview" alt="preview" /></div>

      {result && (
        <>
          <div className={"banner " + (result.result === "PASS" ? "pass" : "fail")}>{result.result}</div>
          {result.surfaces.map((s) => (
            <div className="card" key={s.inspection_id}>
              <h2>Surface {s.surface_index} — {s.result} ({(s.overall_confidence * 100).toFixed(0)}%)</h2>
              <div className="grid cols-2">
                <img className="preview" src={s.annotated_image} alt="annotated" />
                <div>
                  <table>
                    <thead><tr><th>ROI</th><th>Label</th><th>Conf</th><th>Decision</th></tr></thead>
                    <tbody>{s.roi_results.map((rr) => (
                      <tr key={rr.roi_id}><td>{rr.name || `ROI${rr.roi_index}`}</td><td>{rr.label}</td><td>{(rr.confidence * 100).toFixed(0)}%</td>
                        <td style={{ color: rr.decision === "OK" ? "var(--ok)" : "var(--nok)" }}>{rr.decision}</td></tr>
                    ))}</tbody>
                  </table>
                  <div className="muted" style={{ marginTop: 8 }}>{s.saved ? `Archived: ${s.saved_reason}` : "Not archived"}</div>
                </div>
              </div>
            </div>
          ))}
        </>
      )}
    </>
  );
}
