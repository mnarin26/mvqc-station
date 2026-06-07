import { useEffect, useState } from "react";
import { api } from "./api";
import { useEvents } from "./useEvents";
import type { StationEvent } from "./types";
import { Dashboard } from "./components/Dashboard";
import { Products } from "./components/Products";
import { Teaching } from "./components/Teaching";
import { Inspect } from "./components/Inspect";
import { Models } from "./components/Models";
import { Settings } from "./components/Settings";

const TABS = [
  ["dashboard", "Dashboard"],
  ["products", "Products"],
  ["teaching", "Teaching"],
  ["inspect", "Inspect"],
  ["models", "Models"],
  ["settings", "Settings"],
] as const;

type Tab = (typeof TABS)[number][0];

export function App() {
  const [tab, setTab] = useState<Tab>("dashboard");
  const [health, setHealth] = useState<any>(null);
  const [lastScan, setLastScan] = useState<string | null>(null);

  const connected = useEvents((e: StationEvent) => {
    if (e.type === "barcode_scan") setLastScan(String(e.payload.barcode));
  });

  useEffect(() => {
    const poll = () => api.health().then(setHealth).catch(() => {});
    poll();
    const t = setInterval(poll, 8000);
    return () => clearInterval(t);
  }, []);

  return (
    <>
      <header>
        <h1 style={{ fontSize: 16, margin: 0 }}>MVQC <span className="muted">Station</span></h1>
        <span className="muted">{health?.station_id ?? "-"}</span>
        <span style={{ flex: 1 }} />
        <span className={"pill " + (health?.camera?.open ? "ok" : "bad")}>cam:{health?.camera?.backend}</span>
        <span className={"pill " + (health?.storage?.ok ? "ok" : "bad")}>ssd</span>
        <span className={"pill " + (connected ? "ok" : "bad")}>{connected ? "live" : "offline"}</span>
      </header>
      <nav>
        {TABS.map(([id, label]) => (
          <button key={id} className={tab === id ? "active" : ""} onClick={() => setTab(id as Tab)}>
            {label}
          </button>
        ))}
      </nav>
      <main>
        {tab === "dashboard" && <Dashboard />}
        {tab === "products" && <Products />}
        {tab === "teaching" && <Teaching />}
        {tab === "inspect" && <Inspect lastScan={lastScan} />}
        {tab === "models" && <Models />}
        {tab === "settings" && <Settings />}
      </main>
    </>
  );
}
