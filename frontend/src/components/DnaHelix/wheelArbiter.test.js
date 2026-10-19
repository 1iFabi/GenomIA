import { describe, expect, it } from 'vitest';
import { arbitrate, createArbiter } from './wheelArbiter';

// Sequences lifted from a real Windows touchpad log (Chrome 155, events every ~5.5 ms).
// `0` is the {0, 0} event the touchpad sends when the fingers lift.
const H = (xs) => xs.map((x) => [x, 0]);
const V = (ys) => ys.map((y) => [0, y]);
const LIFT = [[0, 0]];

function feed(steps, { s = createArbiter(), t0 = 0, dt = 5.5, gapBefore = 0 } = {}) {
  let t = t0 + gapBefore;
  return steps.map(([deltaX, deltaY, deltaMode = 0]) => {
    t += dt;
    return arbitrate(s, { deltaX, deltaY, deltaMode, timeStamp: t });
  });
}
const actions = (rs) => rs.map((r) => r.action);
const spun = (rs) => rs.reduce((a, r) => a + r.px, 0);

describe('mouse wheel', () => {
  it('always scrolls, never turns the helix', () => {
    const rs = feed(V([100, 100, -100, -100]), { dt: 40 });
    expect(actions(rs)).toEqual(['scroll', 'scroll', 'scroll', 'scroll']);
    expect(feed([[0, 3, 1]]).map((r) => r.action)).toEqual(['scroll']); // line-mode wheel
  });
});

describe('touchpad', () => {
  const swipe = [4, 25, 33, 38, 40, 42, 43, 43, 41, 38, 34, 29, 12, 8, 6, 4, 6, 2];
  const tail = [7, 5, 6, 4, 5, 3, 4, 3, 4, 2, 3, 3, 2, 2, 3, 2, 1, 2, 2, 2, 1];

  it('turns with the fingers, all the way down their slow-down, and releases on lift', () => {
    const s = createArbiter();
    feed([...H([10, 20]), ...LIFT], { s }); // an earlier gesture showed this touchpad sends the marker
    const rs = feed([...H(swipe), ...LIFT, ...H(tail)], { s, t0: 1000 });
    expect(actions(rs).slice(0, swipe.length).every((a) => a === 'spin')).toBe(true);
    expect(spun(rs)).toBe(swipe.reduce((a, b) => a + b));
    expect(rs[swipe.length].release).toBe(true);
    expect(actions(rs).slice(swipe.length)).toEqual(Array(tail.length + 1).fill('hold'));
    expect(rs.slice(1).some((r) => r.fresh)).toBe(false);
  });

  it('on the very first swipe (no marker seen yet) still holds the tail after the lift', () => {
    const rs = feed([...H(swipe), ...LIFT, ...H(tail)]);
    expect(rs.slice(1).some((r) => r.fresh)).toBe(false);
    expect(actions(rs).slice(swipe.length)).toEqual(Array(tail.length + 1).fill('hold'));
  });

  it('catches a second swipe that starts while the first one is still coasting', () => {
    const second = [72, 85, 107, 135, 144, 148, 150];
    const rs = feed([...H([17, 21, 26, 32, 34, 33]), ...LIFT, ...H([3, 3, 2, 1, 1]), ...H(second)]);
    const start = rs.length - second.length;
    expect(rs[start].fresh).toBe(true);
    expect(actions(rs).slice(start)).toEqual(Array(second.length).fill('spin'));
  });

  it('hands a vertical swipe to the page even right after a horizontal one coasts', () => {
    const rs = feed([...H([-10, -14, -18, -21, -28]), ...LIFT, ...H([-17, -15, -3, -2]),
      ...V([-2, -12, -14, -15, -16, -18])]);
    const tailV = actions(rs).slice(-5);
    expect(tailV).toEqual(['scroll', 'scroll', 'scroll', 'scroll', 'scroll']);
    expect(rs.at(-5).fresh).toBe(true);
  });

  it('lets a vertical swipe scroll and coast, ignoring 1 px of sideways tail noise', () => {
    const rs = feed([...V([-1, -11, -12, -13, -16, -17]), ...LIFT, [1, 0], ...V([-1, -1, -1])]);
    expect(actions(rs).every((a) => a === 'scroll')).toBe(true);
    expect(spun(rs)).toBe(0);
  });

  it('starts over after a pause', () => {
    const s = createArbiter();
    feed(H([20, 30, 30]), { s });
    const rs = feed(V([10, 10]), { s, t0: 1000 });
    expect(rs[0].fresh).toBe(true);
    expect(actions(rs)).toEqual(['scroll', 'scroll']);
  });
});

describe('diagonals', () => {
  it('never scrolls and turns in one gesture: stray vertical events are held', () => {
    const rs = feed([[20, 3], [22, 4], [3, 9], [24, 2], [25, 3]]);
    expect(actions(rs)).toEqual(['spin', 'spin', 'hold', 'spin', 'spin']);
  });

  it('a mostly vertical start keeps the whole gesture on the page', () => {
    const rs = feed([[1, 6], [8, 6], [9, 2]]);
    expect(actions(rs)).toEqual(['scroll', 'scroll', 'scroll']);
    expect(spun(rs)).toBe(0);
  });

  it('a horizontal gesture that turns firmly vertical goes back to the page', () => {
    const rs = feed([...H([20, 25]), ...V([15, 18, 20, 22])]);
    expect(actions(rs)).toEqual(['spin', 'spin', 'hold', 'hold', 'scroll', 'scroll']);
    expect(rs[4].release).toBe(true);
  });
});

describe('without the lift marker (other platforms)', () => {
  it('calls a long, deep decay the lift', () => {
    const decay = [40, 36, 32, 28, 22, 15, 9, 6, 4, 3];
    const rs = feed(H(decay));
    const at = rs.findIndex((r) => r.release);
    expect(at).toBe(7); // 6 px: seven drops in a row, under 20% of the 40 px peak
    expect(actions(rs).slice(at)).toEqual(Array(decay.length - at).fill('hold'));
  });

  it('trusts the marker alone once the platform has sent one', () => {
    const s = createArbiter();
    feed([...H([10, 20]), ...LIFT], { s });
    const rs = feed(H([40, 36, 32, 28, 22, 15, 9, 6, 4, 3]), { s, t0: 1000 });
    expect(rs.every((r) => r.action === 'spin')).toBe(true);
  });
});
