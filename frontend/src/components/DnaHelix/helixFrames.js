// Frame names of the dashboard helix, rendered by blender/render_dashboard.sh:
// rest_{m}, seq_{a}-{b}_000..024 (every pair a < b) and dive_{m}_000..024. Pure functions: no React, no DOM.

const STEPS = 24;
const EDGE = 0.14; // top/bottom share of a rest frame where the neighbouring stretches peek in

const pad = (k) => String(k).padStart(3, '0');
export const frames = (name) => Array.from({ length: STEPS + 1 }, (_, k) => `${name}_${pad(k)}.webp`);
const seq = (a, b) => (a < b ? frames(`seq_${a}-${b}`) : frames(`seq_${b}-${a}`).reverse());

/** Frames from module `from` to `to`: every pair has its own rendered trip (the short way round), forward or backward. */
export const spinPath = (from, to) => (from === to ? [] : seq(from, to));

/** The module a click picks, from its height in the rest frame (0 top, 1 bottom): neighbours peek in at the edges. */
export const slotAt = (y, shown, count) =>
  Math.max(0, Math.min(count - 1, shown + (y < EDGE ? -1 : y > 1 - EDGE ? 1 : 0)));
