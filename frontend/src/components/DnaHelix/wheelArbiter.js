// Decides, wheel event by wheel event, whether the page scrolls or the helix turns.
// Tuned on a real Windows precision-touchpad log (Chrome 155): each event rides one
// axis, a {0, 0} event marks the fingers lifting, and the OS inertia that follows can
// run straight into the next swipe with no pause between them.
// Pure logic: no DOM. The caller calls preventDefault() unless the action is 'scroll'.

const GAP_MS = 160; // silence that ends any gesture
const LOCK_PX = 4; // travel before an axis is chosen; vertical wins ties
const CONTACT_PX = 6; // during inertia, a jump this big (and 3× the tail) is new fingers
const SWITCH = 3; // vertical events in a row that hand a horizontal gesture back to scroll

export const createArbiter = () => ({ sawLift: false, t: -Infinity, ...fresh() });

const fresh = () => ({ lock: null, phase: 'fingers', adx: 0, ady: 0, last: 0, peak: 0, drops: 0, against: 0 });

/**
 * Feeds one wheel event (`deltaX`, `deltaY`, `deltaMode`, `timeStamp`) into the arbiter
 * `s`, which it updates. Returns { action: 'scroll' | 'spin' | 'hold', px, release, fresh }:
 * 'spin' turns the helix by `px` of horizontal travel, 'hold' swallows the event,
 * `release` means the fingers just lifted (start settling), `fresh` a new gesture began.
 */
export function arbitrate(s, { deltaX, deltaY, deltaMode = 0, timeStamp }) {
  const unit = deltaMode === 1 ? 16 : deltaMode === 2 ? 800 : 1; // lines/pages → px
  const ax = Math.abs(deltaX * unit);
  const ay = Math.abs(deltaY * unit);
  const mag = Math.max(ax, ay);
  const axis = ax > ay ? 'H' : 'V';

  const isNew = timeStamp - s.t > GAP_MS
    || (s.phase === 'momentum' && mag >= CONTACT_PX && (axis !== s.lock || mag >= 3 * s.last));
  if (isNew) Object.assign(s, fresh());
  s.t = timeStamp;
  const out = (action, px = 0, release = false) => ({ action, px, release, fresh: isNew });
  const idle = () => (s.lock === 'H' ? 'hold' : 'scroll');

  if (!mag) { // the fingers lifted; what follows is the OS's inertia
    s.sawLift = true;
    s.last = s.peak; // the tail starts small against the swipe, so it never reads as new fingers
    if (s.phase === 'momentum') return out(idle()); // the decay guess already released it
    s.phase = 'momentum';
    return out(idle(), 0, s.lock === 'H');
  }

  if (s.phase === 'momentum') { // inertia: scroll keeps it, the helix ignores it
    s.last = mag;
    return out(idle());
  }

  if (!s.lock) {
    s.adx += ax;
    s.ady += ay;
    if (deltaMode) s.lock = 'V'; // a notched wheel reporting lines or pages
    else if (s.adx + s.ady >= LOCK_PX) s.lock = s.adx > s.ady ? 'H' : 'V';
    if (!s.lock) return out(axis === 'H' ? 'hold' : 'scroll');
  }
  s.peak = Math.max(s.peak, mag);
  if (s.lock === 'V') return out('scroll');

  if (axis === 'V') { // a stray vertical event, or the user really went vertical
    if (++s.against < SWITCH) return out('hold');
    Object.assign(s, fresh(), { lock: 'V' });
    return out('scroll', 0, true);
  }
  s.against = 0;

  // Platforms that never send the {0, 0} marker: call a long, deep decay the lift.
  if (!s.sawLift) {
    s.drops = ax < s.last ? s.drops + 1 : 0;
    if (s.drops >= 6 && ax < 0.2 * s.peak) {
      s.phase = 'momentum';
      s.last = ax;
      return out('hold', 0, true);
    }
  }
  s.last = ax;
  return out('spin', deltaX * unit);
}
