import { useEffect, useState } from "react";
import { api } from "../api";

export function Products() {
  const [products, setProducts] = useState<any[]>([]);
  const [name, setName] = useState("");
  const [barcode, setBarcode] = useState("");
  const [surfaces, setSurfaces] = useState(1);
  const [rule, setRule] = useState("all_filled");
  const [err, setErr] = useState<string | null>(null);

  const load = () => api.products().then(setProducts).catch(() => {});
  useEffect(() => { load(); }, []);

  const create = async () => {
    setErr(null);
    try {
      await api.createProduct({ name: name.trim(), barcode: barcode.trim() || null, surface_count: surfaces, pass_rule: rule });
      setName(""); setBarcode(""); setSurfaces(1); load();
    } catch (e) { setErr((e as Error).message); }
  };

  return (
    <>
      <div className="card">
        <h2>Create product</h2>
        <div className="grid cols-2">
          <div><label>Name</label><input value={name} onChange={(e) => setName(e.target.value)} placeholder="Product_A" /></div>
          <div><label>Barcode</label><input value={barcode} onChange={(e) => setBarcode(e.target.value)} placeholder="8691234567890" /></div>
          <div><label>Surface count</label><input type="number" min={1} value={surfaces} onChange={(e) => setSurfaces(+e.target.value)} /></div>
          <div><label>Pass rule</label><select value={rule} onChange={(e) => setRule(e.target.value)}><option value="all_filled">all_filled</option><option value="any_filled">any_filled</option></select></div>
        </div>
        <div className="row" style={{ marginTop: 12 }}><button className="btn" onClick={create}>Create product</button>{err && <span style={{ color: "var(--nok)" }}>{err}</span>}</div>
      </div>
      <div className="card">
        <h2>Products</h2>
        <table>
          <thead><tr><th>ID</th><th>Name</th><th>Barcode</th><th>Surfaces</th><th>Status</th></tr></thead>
          <tbody>{products.map((p) => (
            <tr key={p.id}><td>{p.id}</td><td>{p.name}</td><td>{p.barcode || "-"}</td><td>{p.surface_count}</td><td><span className="pill">{p.status}</span></td></tr>
          ))}</tbody>
        </table>
      </div>
    </>
  );
}
