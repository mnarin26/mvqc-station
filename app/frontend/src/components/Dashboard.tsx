import { useEffect, useState } from "react";
import { api } from "../api";

export function Dashboard() {
  const [data, setData] = useState<any>(null);
  useEffect(() => { api.dashboard().then(setData).catch(() => {}); }, []);
  if (!data) return <p className="muted">Loading…</p>;
  const s = data.stats;
  const sh = data.storage;
  return (
    <>
      <div className="grid cols-3">
        <div className="card"><div className="muted">Total inspections</div><div style={{ fontSize: 30, fontWeight: 700 }}>{s.total}</div></div>
        <div className="card"><div className="muted">Pass rate</div><div style={{ fontSize: 30, fontWeight: 700 }}>{(s.pass_rate * 100).toFixed(1)}%</div></div>
        <div className="card"><div className="muted">Failures</div><div style={{ fontSize: 30, fontWeight: 700, color: "var(--nok)" }}>{s.fail}</div></div>
      </div>
      <div className="card">
        <h2>Storage health</h2>
        <table>
          <thead><tr><th>Location</th><th>Mounted</th><th>Writable</th><th>Free (MB)</th><th>OK</th></tr></thead>
          <tbody>
            <tr>
              <td><code>{sh.mount ?? "-"}</code></td>
              <td>{String(sh.mounted)}</td>
              <td>{String(sh.writable)}</td>
              <td>{sh.free_mb ?? "-"}</td>
              <td><span className={"dot " + (sh.ok ? "ok" : "nok")} /></td>
            </tr>
          </tbody>
        </table>
        <div className="muted" style={{ marginTop: 8 }}>Policy: {sh.policy} · buffered files: {sh.buffered_files}</div>
      </div>
      <div className="card">
        <h2>Recent inspections</h2>
        <table>
          <thead><tr><th>ID</th><th>Surface</th><th>Result</th><th>Conf</th><th>Saved</th><th>Time</th></tr></thead>
          <tbody>{data.recent.map((r: any) => (
            <tr key={r.id}><td>{r.id}</td><td>{r.surface_index}</td>
              <td style={{ color: r.result === "PASS" ? "var(--ok)" : "var(--nok)" }}>{r.result}</td>
              <td>{(r.overall_confidence ?? 0).toFixed(2)}</td><td>{r.saved ? r.saved_reason : "-"}</td>
              <td className="muted">{r.timestamp}</td></tr>
          ))}</tbody>
        </table>
      </div>
    </>
  );
}
