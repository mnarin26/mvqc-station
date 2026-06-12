export type { Geometry } from "./geometry";

export interface Roi {
  id?: number;
  name?: string | null;
  roi_index: number;
  inspector_type: string;
  geometry: import("./geometry").Geometry;
  threshold: number;
}

export interface Surface {
  id: number;
  surface_index: number;
  name?: string | null;
  rois: Roi[];
}

export interface Recipe {
  id: number;
  product_id: number;
  product_name?: string;
  version: number;
  is_active: boolean;
  pass_rule: string;
  surfaces: Surface[];
}

export interface Product {
  id: number;
  name: string;
  barcode?: string | null;
  surface_count: number;
  status: string;
  active_recipe_id?: number | null;
  created_at: string;
}

export interface RoiResult {
  roi_id: number;
  roi_index: number;
  name?: string | null;
  label: string;
  confidence: number;
  decision: string;
  geometry: import("./geometry").Geometry;
}

export interface SurfaceResult {
  inspection_id: number;
  surface_index: number;
  result: string;
  overall_confidence: number;
  roi_results: RoiResult[];
  saved: boolean;
  saved_reason?: string | null;
  annotated_image: string;
}

export interface InspectResult {
  cycle_id: number;
  product: string;
  barcode?: string | null;
  result: string;
  surfaces: SurfaceResult[];
}

export interface StationEvent { type: string; ts: number; payload: Record<string, unknown>; }
