// The pre-rendered glass helix as a dial. Angles are continuous degrees (they
// never wrap, so a spin can be followed past 360°); frames are what gets drawn.
// Pure functions: no React, no DOM.

export const FRAMES = 120; // one turn rendered: frame 119 meets frame 0 again
export const FRAME_DEG = 360 / FRAMES; // 3°
export const SLOTS = 5; // Ancestría, Farmacogenética, Rasgos, Riesgo poligénico, Riesgo monogénico
export const SLOT_DEG = 360 / SLOTS; // 72°, one module per fifth of a turn
export const SLOT_FRAMES = FRAMES / SLOTS; // 24 frames
export const SNAP_VEL = 90; // °/s; faster than this, away from the module, is still a throw
export const THROW_VEL = 2 * SNAP_VEL; // a release never counts faster than this

const OMEGA = 18; // spring stiffness, rad/s: lands in ~0.4 s, no overshoot from rest
const BRAKE = 0.06; // s; a throw loses ~63% of its speed every 60 ms
const HALF = SLOT_DEG / 2 - 0.1; // stop short of the exact tie with the next module

const mod = (a, n) => ((a % n) + n) % n;

/** Degrees → frame 0..119; -1° is frame 119. */
export const frameForAngle = (deg) => mod(Math.floor(deg / FRAME_DEG), FRAMES);

/**
 * Signed degrees to the nearest module, within ±36° (the short way round).
 * An exact 36° tie follows the spin `dir`; still, it goes forward.
 */
export function nearestSlotDelta(deg, dir = 0) {
  const r = mod(deg, SLOT_DEG);
  const tie = SLOT_DEG / 2;
  if (r === tie) return dir < 0 ? -tie : tie;
  if (r < tie) return r ? -r : 0;
  return SLOT_DEG - r;
}

/** Module index → its angle: 0/72/144/216/288. */
export const angleForSlot = (i) => mod(i, SLOTS) * SLOT_DEG;

/** The module (0..4) an angle is closest to. */
export const slotForAngle = (deg, dir = 0) =>
  mod(Math.round((deg + nearestSlotDelta(deg, dir)) / SLOT_DEG), SLOTS);

/**
 * The shot for an angle. `cams` holds one framing per module, { x, y, w } as fractions
 * of the frame (the crop keeps the frame's aspect, so its height is w too). Between
 * modules the camera eases from one shot to the next, so turning the dial moves it.
 */
export function cameraForAngle(deg, cams) {
  const p = mod(deg, 360) / SLOT_DEG;
  const i = Math.floor(p);
  const t = p - i;
  const e = t * t * (3 - 2 * t); // smoothstep: still at each module, fastest halfway
  const a = cams[i];
  const b = cams[(i + 1) % SLOTS];
  return { x: a.x + (b.x - a.x) * e, y: a.y + (b.y - a.y) * e, w: a.w + (b.w - a.w) * e };
}

/** A pin fixed at `pinAngle` on the glass: 1 facing front, 0 anywhere on the back half. */
export const pinOcclusion = (pinAngle, angle) =>
  Math.max(0, Math.cos(((pinAngle - angle) * Math.PI) / 180));

/** Drag that moves one frame when you grab the glass surface: π·W over a turn. */
export const pixelsPerFrame = (width) => (Math.PI * width) / FRAMES;

/** The next module's worth of frames to decode, ahead in the spin direction; split both ways when still. */
export function readAheadWindow(frame, dir) {
  const out = [];
  for (let i = 1; out.length < SLOT_FRAMES; i++) {
    if (dir) out.push(mod(frame + Math.sign(dir) * i, FRAMES));
    else out.push(mod(frame + Math.ceil(i / 2) * (i % 2 ? 1 : -1), FRAMES));
  }
  return out;
}

/**
 * One step (`dt` seconds) of the release after a spin. It always lands on the
 * module whose half it was let go in: slow (or already heading in), a critically
 * damped spring pulls it there; a throw away from it is braked and never carried
 * past the halfway line, so momentum alone cannot change the module.
 */
export function settle(pos, vel, dt) {
  const v = Math.max(-THROW_VEL, Math.min(THROW_VEL, vel)); // trackpads release at ~2000°/s
  const delta = nearestSlotDelta(pos, Math.sign(v));
  const target = Math.round((pos + delta) / SLOT_DEG) * SLOT_DEG + 0; // + 0: never -0
  if (Math.abs(v) < SNAP_VEL || Math.sign(v) === Math.sign(delta)) {
    const x0 = -delta;
    const k = Math.exp(-OMEGA * dt);
    const x = (x0 + (v + OMEGA * x0) * dt) * k;
    const nv = (v - OMEGA * (v + OMEGA * x0) * dt) * k;
    if (Math.abs(x) < 0.01 && Math.abs(nv) < 1) return { pos: target, vel: 0, done: true };
    return { pos: target + x, vel: nv, done: false };
  }
  const k = Math.exp(-dt / BRAKE);
  const next = pos + v * BRAKE * (1 - k);
  const edge = target + Math.sign(v) * HALF; // the halfway line toward the next module
  if (Math.abs(next - target) >= HALF) return { pos: edge, vel: 0, done: false };
  return { pos: next, vel: v * k, done: false };
}
