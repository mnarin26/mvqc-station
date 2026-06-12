export interface Geometry {
  points: [number, number][];
}

/** Migrate legacy {x,y,w,h} rect to 4-point polygon. */
export function normalizeGeometry(g: {
  points?: [number, number][];
  x?: number;
  y?: number;
  w?: number;
  h?: number;
}): Geometry {
  if (g.points && g.points.length >= 3) {
    return { points: g.points.map((p) => [p[0], p[1]] as [number, number]) };
  }
  if (g.x != null && g.y != null && g.w != null && g.h != null) {
    const { x, y, w, h } = g;
    return {
      points: [
        [x, y],
        [x + w, y],
        [x + w, y + h],
        [x, y + h],
      ],
    };
  }
  return { points: [] };
}

export function rectFromDrag(
  x0: number,
  y0: number,
  x1: number,
  y1: number,
  scale: number,
): Geometry {
  const x = Math.round(Math.min(x0, x1) / scale);
  const y = Math.round(Math.min(y0, y1) / scale);
  const w = Math.round(Math.abs(x1 - x0) / scale);
  const h = Math.round(Math.abs(y1 - y0) / scale);
  return normalizeGeometry({ x, y, w, h });
}

export function dist(a: [number, number], b: [number, number]): number {
  return Math.hypot(a[0] - b[0], a[1] - b[1]);
}
