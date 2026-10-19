import { describe, expect, it } from 'vitest';
import {
  FRAMES, SLOTS, SLOT_FRAMES, SNAP_VEL,
  angleForSlot, cameraForAngle, frameForAngle, nearestSlotDelta, pinOcclusion,
  pixelsPerFrame, readAheadWindow, settle, slotForAngle,
} from './helixMath';

describe('frameForAngle', () => {
  it('maps degrees onto the 120-frame turn, wrapping both ways', () => {
    expect(frameForAngle(0)).toBe(0);
    expect(frameForAngle(2.9)).toBe(0);
    expect(frameForAngle(3)).toBe(1);
    expect(frameForAngle(72)).toBe(SLOT_FRAMES);
    expect(frameForAngle(359.9)).toBe(119);
    expect(frameForAngle(360)).toBe(0);
    expect(frameForAngle(-1)).toBe(119);
    expect(frameForAngle(-720 - 1)).toBe(119);
    expect(frameForAngle(3600 + 93)).toBe(31);
  });
});

describe('nearestSlotDelta', () => {
  it('takes the shortest signed way to a module, never the long one', () => {
    expect(nearestSlotDelta(60)).toBe(12);
    expect(nearestSlotDelta(80)).toBe(-8);
    expect(nearestSlotDelta(359)).toBe(1); // 1° on to 360, not 71° back to 288
    expect(nearestSlotDelta(-73)).toBe(1);
    expect(nearestSlotDelta(-71)).toBe(-1);
    expect(Object.is(nearestSlotDelta(144), 0)).toBe(true);
    expect(Object.is(nearestSlotDelta(-288), 0)).toBe(true);
  });

  it('breaks an exact 36° tie toward the current spin, forward when still', () => {
    expect(nearestSlotDelta(36)).toBe(36);
    expect(nearestSlotDelta(36, 1)).toBe(36);
    expect(nearestSlotDelta(36, -1)).toBe(-36);
    expect(nearestSlotDelta(-36)).toBe(36);
    expect(nearestSlotDelta(-36, -3)).toBe(-36);
    expect(nearestSlotDelta(108, -1)).toBe(-36);
  });
});

describe('slots', () => {
  it('places the five modules a fifth of a turn apart', () => {
    expect(SLOTS * SLOT_FRAMES).toBe(FRAMES);
    expect([0, 1, 2, 3, 4, 5, -1].map(angleForSlot)).toEqual([0, 72, 144, 216, 288, 0, 288]);
  });

  it('reads the module nearest to any angle', () => {
    expect(slotForAngle(0)).toBe(0);
    expect(slotForAngle(80)).toBe(1);
    expect(slotForAngle(-60)).toBe(4);
    expect(slotForAngle(725)).toBe(0);
    expect(slotForAngle(108, -1)).toBe(1);
    expect(slotForAngle(108, 1)).toBe(2);
  });
});

describe('cameraForAngle', () => {
  const cams = [
    { x: 0, y: 0, w: 1 },
    { x: 0.5, y: 0, w: 0.5 },
    { x: 0.3, y: 0.2, w: 0.5 },
    { x: 0.2, y: 0.4, w: 0.5 },
    { x: 0.1, y: 0.5, w: 0.5 },
  ];
  const near = (c, e) => ['x', 'y', 'w'].forEach((k) => expect(c[k]).toBeCloseTo(e[k], 6));

  it('frames each module with its own shot, on any turn', () => {
    near(cameraForAngle(0, cams), cams[0]);
    near(cameraForAngle(72, cams), cams[1]);
    near(cameraForAngle(144 + 360, cams), cams[2]);
    near(cameraForAngle(-72, cams), cams[4]);
  });

  it('glides between shots with the dial, halfway between modules', () => {
    near(cameraForAngle(36, cams), { x: 0.25, y: 0, w: 0.75 });
    near(cameraForAngle(324, cams), { x: 0.05, y: 0.25, w: 0.75 }); // Riesgo monogénico back to Ancestría
    expect(cameraForAngle(8, cams).w).toBeGreaterThan(0.95); // eased: barely moves leaving a module
  });
});

describe('pinOcclusion', () => {
  it('is 1 facing front, fades with the turn, 0 across the back', () => {
    expect(pinOcclusion(72, 72)).toBeCloseTo(1);
    expect(pinOcclusion(72, 72 + 360)).toBeCloseTo(1);
    expect(pinOcclusion(0, 60)).toBeCloseTo(0.5);
    expect(pinOcclusion(0, 90)).toBeCloseTo(0);
    expect(pinOcclusion(0, 180)).toBe(0);
    expect(pinOcclusion(270, 0)).toBeCloseTo(0);
  });
});

describe('pixelsPerFrame', () => {
  it('drags the glass surface: π·W spread over one turn', () => {
    expect(pixelsPerFrame(400)).toBeCloseTo(10.47, 2);
    expect(pixelsPerFrame(400) * SLOT_FRAMES).toBeCloseTo(251, 0); // one module of drag
  });
});

describe('readAheadWindow', () => {
  it("lists the next module's frames in the spin direction, wrapping", () => {
    const fwd = readAheadWindow(110, 1);
    expect(fwd).toHaveLength(SLOT_FRAMES);
    expect(fwd.slice(0, 3)).toEqual([111, 112, 113]);
    expect(fwd.at(-1)).toBe(14);
    const back = readAheadWindow(5, -1);
    expect(back.slice(0, 3)).toEqual([4, 3, 2]);
    expect(back.at(-1)).toBe(101);
  });

  it('splits the window both ways when still', () => {
    const still = readAheadWindow(0, 0);
    expect(still).toHaveLength(SLOT_FRAMES);
    expect(still.slice(0, 4)).toEqual([1, 119, 2, 118]);
  });
});

describe('settle', () => {
  const run = (pos, vel, ms = 2000) => {
    let s = { pos, vel, done: false };
    for (let t = 0; t < ms && !s.done; t += 16) s = settle(s.pos, s.vel, 0.016);
    return s;
  };

  it('magnets onto the module when close and slow, without overshoot', () => {
    let s = { pos: 60, vel: 0 };
    let max = 0;
    for (let i = 0; i < 200; i++) { s = settle(s.pos, s.vel, 0.016); max = Math.max(max, s.pos); }
    expect(s.pos).toBe(72);
    expect(s.done).toBe(true);
    expect(max).toBeLessThanOrEqual(72);
    expect(run(-17, 0).pos).toBe(0);
    expect(run(365, 0).pos).toBe(360);
  });

  it('lands on the nearest module from anywhere in its half', () => {
    expect(run(72 + 30, 0).pos).toBe(72);
    expect(run(72 + 35, 0).pos).toBe(72);
    expect(run(72 + 37, 0).pos).toBe(144);
  });

  it('brakes a fast release instead of letting it coast into the next module', () => {
    expect(run(0, SNAP_VEL * 4).pos).toBe(0); // a hard flick from Ancestría
    // the real touchpad log: let go 28° past Farmacogenética, moving away at ~2080°/s
    expect(run(100, 2083).pos).toBe(72);
    expect(run(-100, -2083).pos).toBe(-72);
  });

  it('is at rest immediately on a module', () => {
    expect(settle(216, 0, 0.016)).toEqual({ pos: 216, vel: 0, done: true });
  });
});
