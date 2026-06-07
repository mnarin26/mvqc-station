const API = "/api";

async function request<T>(path: string, opts: RequestInit = {}): Promise<T> {
  const res = await fetch(API + path, opts);
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail ?? detail; } catch { /* ignore */ }
    throw new Error(detail);
  }
  return (res.status === 204 ? undefined : await res.json()) as T;
}

const json = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const api = {
  health: () => request<any>("/health"),
  dashboard: () => request<any>("/dashboard"),
  settings: () => request<any>("/settings"),
  settingsFull: () => request<any>("/settings"),
  settingsDevices: () => request<any>("/settings/devices"),
  updateSettings: (body: Record<string, unknown>) =>
    request<any>("/settings", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  reloadHardware: () => request<any>("/settings/reload-hardware", json({})),

  products: () => request<any[]>("/products"),
  createProduct: (b: unknown) => request<any>("/products", json(b)),
  product: (id: number) => request<any>(`/products/${id}`),
  recipes: (id: number) => request<any[]>(`/products/${id}/recipes`),
  recipe: (id: number) => request<any>(`/recipes/${id}`),
  activeRecipe: (id: number) => request<any>(`/products/${id}/active-recipe`),
  activateRecipe: (id: number) => request<any>(`/recipes/${id}/activate`, json({})),

  setRois: (surfaceId: number, rois: unknown) =>
    request<any>(`/surfaces/${surfaceId}/rois`, { ...json({ rois }), method: "PUT" }),

  snapshot: () => request<{ image: string; width: number; height: number }>("/teaching/snapshot"),
  teach: (surfaceId: number, label: string) =>
    request<any>("/teaching/capture", json({ surface_id: surfaceId, label })),
  teachStatus: (surfaceId: number) => request<any>(`/teaching/status/${surfaceId}`),

  inspect: (b: unknown) => request<any>("/inspect", json(b)),

  models: () => request<any[]>("/models"),
  coverage: (id: number) => request<any>(`/models/coverage/${id}`),
  rollback: (roiId: number) => request<any>(`/models/rollback/${roiId}`, json({})),
  importBundle: (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return request<any>("/models/import", { method: "POST", body: fd });
  },
};
