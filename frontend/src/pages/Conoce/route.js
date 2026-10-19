/**
 * A road through the station centres: one cubic per leg, bulging to alternate sides so it reads
 * as a winding path. Works for a row (desktop) and a column (mobile) of stations.
 */
export function roadThrough(pts) {
  let d = `M ${pts[0].x} ${pts[0].y}`;
  for (let i = 1; i < pts.length; i++) {
    const p = pts[i - 1];
    const q = pts[i];
    const dx = q.x - p.x;
    const dy = q.y - p.y;
    const row = Math.abs(dx) >= Math.abs(dy);
    const bulge = Math.min(row ? 56 : 22, Math.hypot(dx, dy) * 0.3) * (i % 2 ? -1 : 1);
    const c1 = row ? [p.x + dx * 0.35, p.y + bulge] : [p.x + bulge, p.y + dy * 0.35];
    const c2 = row ? [q.x - dx * 0.35, q.y + bulge] : [q.x + bulge, q.y - dy * 0.35];
    d += ` C ${c1.join(" ")} ${c2.join(" ")} ${q.x} ${q.y}`;
  }
  return d;
}

/** Length along the road for a position in station units (0 = first station, 3 = last). */
export function lengthAt(stops, t) {
  const i = Math.max(0, Math.min(stops.length - 2, Math.floor(t)));
  return stops[i] + (t - i) * (stops[i + 1] - stops[i]);
}
