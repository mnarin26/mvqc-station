import { useCallback, useEffect, useState } from "react";
import { api } from "../api";

type Field = {
  key: string;
  label: string;
  type: string;
  options?: string[];
  min?: number;
  max?: number;
  step?: number;
  value: unknown;
  default: unknown;
};

type Section = { id: string; title: string; fields: Field[] };

type Devices = {
  video: { path: string; label: string }[];
  input: { path: string; label: string }[];
  serial: { path: string; label: string }[];
  mounts?: {
    path: string;
    display?: string;
    display_name?: string;
    select_value?: string;
    mount_path?: string | null;
    fstype?: string;
    mounted?: boolean;
    writable?: boolean;
    free_mb?: number;
    recommended?: boolean;
    selectable?: boolean;
    status?: string;
  }[];
  storage_devices?: {
    id: string;
    device: string;
    name: string;
    display_name: string;
    size?: string;
    fstype?: string;
    transport?: string;
    mounted?: boolean;
    mount_path?: string | null;
    select_value?: string;
    selectable?: boolean;
    recommended?: boolean;
    status?: string;
  }[];
};

export function Settings() {
  const [sections, setSections] = useState<Section[]>([]);
  const [values, setValues] = useState<Record<string, unknown>>({});
  const [devices, setDevices] = useState<Devices>({ video: [], input: [], serial: [] });
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const [data, dev] = await Promise.all([
      api.settingsFull(),
      api.settingsDevices().catch(() => ({ video: [], input: [], serial: [], mounts: [], storage_devices: [] })),
    ]);
    setSections(data.sections || []);
    setValues(data.values || {});
    setDevices(dev);
  }, []);

  useEffect(() => { load(); }, [load]);

  const setVal = (key: string, v: unknown) => setValues((prev) => ({ ...prev, [key]: v }));

  const save = async () => {
    setBusy(true);
    setMsg("");
    try {
      const res = await api.updateSettings({ ...values, reload_hardware: true });
      setValues(res.values || values);
      setSections(res.sections || sections);
      const hw = res.hardware;
      setMsg(hw
        ? `Applied — camera: ${hw.camera} (${hw.camera_open ? "open" : "closed"})`
        : res.storage?.device
          ? `Storage: ${res.storage.ok ? "OK" : "select volume"} · ${res.storage.device}`
          : "Saved");
    } catch (e) {
      setMsg((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const reloadHw = async () => {
    setBusy(true);
    try {
      const res = await api.reloadHardware();
      setMsg(`Reloaded: ${res.hardware?.camera}`);
    } catch (e) {
      setMsg((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  if (!sections.length) return <p className="muted">Loading…</p>;

  const renderField = (f: Field) => {
    const val = values[f.key] ?? f.value;
    if (f.type === "select") {
      return (
        <select value={String(val)} onChange={(e) => setVal(f.key, e.target.value)}>
          {(f.options || []).map((o) => <option key={o} value={o}>{o}</option>)}
        </select>
      );
    }
    if (f.type === "boolean") {
      return (
        <select value={String(val)} onChange={(e) => setVal(f.key, e.target.value === "true")}>
          <option value="true">true</option>
          <option value="false">false</option>
        </select>
      );
    }
    if (f.type === "device_video") {
      return (
        <>
          <select value={String(val)} onChange={(e) => setVal(f.key, e.target.value)}>
            {devices.video.map((d) => <option key={d.path} value={d.path}>{d.label}</option>)}
          </select>
          <input style={{ marginTop: 6 }} value={String(val)} placeholder="/dev/video0"
            onChange={(e) => setVal(f.key, e.target.value)} />
        </>
      );
    }
    if (f.type === "device_input") {
      return (
        <>
          <select value={String(val)} onChange={(e) => setVal(f.key, e.target.value)}>
            {devices.input.map((d) => <option key={d.path} value={d.path}>{d.label}</option>)}
          </select>
          <input style={{ marginTop: 6 }} value={String(val)} placeholder="/dev/input/event0"
            onChange={(e) => setVal(f.key, e.target.value)} />
        </>
      );
    }
    if (f.type === "device_serial") {
      return (
        <>
          <select value={String(val)} onChange={(e) => setVal(f.key, e.target.value)}>
            {devices.serial.map((d) => <option key={d.path} value={d.path}>{d.label}</option>)}
          </select>
          <input style={{ marginTop: 6 }} value={String(val)} placeholder="/dev/ttyUSB0"
            onChange={(e) => setVal(f.key, e.target.value)} />
        </>
      );
    }
    if (f.type === "storage_device") {
      const devs = devices.storage_devices || [];
      const curDev = String(values[f.key] ?? f.value ?? "");
      const curSelect = curDev.startsWith("device:") ? curDev : (curDev.startsWith("/dev/") ? `device:${curDev}` : curDev);
      const curMount = String(values["storage.mount"] ?? "");
      const match = (item: { select_value?: string; device?: string }) =>
        curSelect === item.select_value || curDev === item.device;
      return (
        <>
          <select value={curSelect} onChange={(e) => setVal(f.key, e.target.value)}>
            {devs.filter((d) => d.selectable !== false).map((d) => {
              const lbl = d.display_name || d.device;
              const tag = d.recommended ? " ★" : d.status === "needs_mount" ? " (mount on save)" : "";
              return <option key={d.select_value} value={d.select_value}>{lbl}{tag}</option>;
            })}
            {!devs.some(match) && curDev && <option value={curSelect}>{curDev} (saved)</option>}
          </select>
          <div className="muted" style={{ fontSize: 11, marginTop: 4 }}>
            Mount path: <code>{curMount || "(not mounted)"}</code>
          </div>
        </>
      );
    }
    return (
      <input type="number" value={Number(val)} step={f.step} min={f.min} max={f.max}
        onChange={(e) => setVal(f.key, e.target.value.includes(".") ? parseFloat(e.target.value) : parseInt(e.target.value, 10))} />
    );
  };

  return (
    <>
      {sections.map((sec) => (
        <div className="card" key={sec.id}>
          <h2>{sec.title}</h2>
          <div className="grid cols-2">
            {sec.fields.map((f) => (
              <div key={f.key}>
                <label>{f.label}</label>
                {renderField(f)}
                <div className="muted" style={{ fontSize: 11, marginTop: 2 }}>default: {String(f.default)}</div>
              </div>
            ))}
          </div>
        </div>
      ))}
      <div className="card">
        <div className="row">
          <button className="btn" disabled={busy} onClick={save}>Save &amp; apply</button>
          <button className="btn secondary" disabled={busy} onClick={reloadHw}>Reload hardware only</button>
          <span className="muted">{msg}</span>
        </div>
        <div className="muted" style={{ marginTop: 8 }}>Camera, barcode, lighting and storage mount paths apply immediately after save.</div>
      </div>
    </>
  );
}
