import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from 'react';
import { frames, slotAt, spinPath } from './helixFrames';
import { arbitrate, createArbiter } from './wheelArbiter';
import './DnaHelix.css';

const FRAME_MS = 33; // ~30 fps: one module is 0.8 s of spin
const FADE_MS = 220;
const HURRY = 3; // frames per tick when a new module is picked mid-trip
const SWIPE_PX = 40; // drag or touchpad travel that turns one module
const PHONE = '(max-width: 860px)'; // keep in step with Dashboard.css and DnaHelix.css
const reduced = () => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

const usePhone = () => {
  const [phone, setPhone] = useState(() => Boolean(window.matchMedia?.(PHONE).matches));
  useEffect(() => {
    const mq = window.matchMedia?.(PHONE);
    if (!mq) return undefined;
    const on = () => setPhone(mq.matches);
    mq.addEventListener('change', on);
    return () => mq.removeEventListener('change', on);
  }, []);
  return phone;
};

/**
 * The glass helix as a sequence player. `slot` is the chosen module; when it changes the
 * rendered trip from the module on show straight to it plays (a fade instead while a frame
 * is still missing, or with reduced motion). Picking again mid-trip never cuts: the running
 * trip hurries to its end and the helix travels on from there.
 * Dragging, a sideways touchpad swipe or the arrow keys ask for a neighbour via `onPick(i)`;
 * a click on a stretch picks it. The helix never enters a module: that is the page's link.
 * The ref exposes dive() → Promise: the plunge into the chosen stretch, then a fade out.
 */
const DnaHelix = forwardRef(function DnaHelix({ slot, count, label, onPick }, ref) {
  const phone = usePhone();
  const base = `/dna-dashboard/${phone ? 'mobile' : 'desktop'}/`;
  const img = useRef(null);
  const cache = useRef(new Map());
  const shown = useRef(slot);
  const token = useRef(0);
  const busy = useRef(false);
  const hurry = useRef(false);
  const drag = useRef(null);
  const cb = useRef({});
  cb.current = { onPick, slot, count, base };
  const [diving, setDiving] = useState(false);
  const [first] = useState(slot); // after mount the player owns src: a re-render must not jump to the destination

  // Frames load as they become needed, not all 380 up front: every rest frame, then from the module on
  // show the trips to its neighbours (the tour's next stop wraps round) and its dive. A farther pick fades
  // instead of spinning. Newest needs go first, six requests at a time.
  const queue = useRef([]);
  const loading = useRef(0);
  const pump = () => {
    while (loading.current < 6 && queue.current.length) {
      const url = queue.current.shift();
      if (cache.current.has(url)) continue;
      const im = new Image();
      im.decoding = 'async';
      loading.current += 1;
      im.onload = im.onerror = () => { loading.current -= 1; pump(); };
      im.src = url;
      cache.current.set(url, im);
    }
  };
  const want = (names) => {
    queue.current = [...names.map((name) => cb.current.base + name), ...queue.current];
    pump();
  };
  const warm = (m) => {
    const n = cb.current.count;
    want([...spinPath(m, (m + 1) % n), ...spinPath(m, (m - 1 + n) % n), ...frames(`dive_${m}`)]);
  };

  useEffect(() => {
    warm(shown.current);
    want(Array.from({ length: count }, (_, m) => `rest_${m}.webp`)); // ahead of the warm-up
    return () => { queue.current = []; };
  }, [base, count]); // eslint-disable-line react-hooks/exhaustive-deps

  const ready = (name) => {
    const im = cache.current.get(cb.current.base + name);
    return Boolean(im?.complete && im.naturalWidth);
  };
  const show = (name) => { if (img.current) img.current.src = cb.current.base + name; };

  const fadeTo = (name, t) => new Promise((resolve) => {
    const el = img.current;
    if (!el) { resolve(); return; }
    el.dataset.fading = '';
    setTimeout(() => {
      if (name && t === token.current) show(name);
      if (name) delete el.dataset.fading; // a newer move took over: never leave the glass hidden
      resolve();
    }, FADE_MS);
  });

  const play = (names, t) => new Promise((resolve) => {
    let k = 0;
    let last = -Infinity;
    const tick = (now) => {
      if (t !== token.current) { resolve(); return; }
      if (now - last >= FRAME_MS) {
        k = Math.min(names.length, k + (hurry.current ? HURRY : 1));
        show(names[k - 1]);
        last = now;
      }
      if (k < names.length) requestAnimationFrame(tick);
      else resolve();
    };
    requestAnimationFrame(tick);
  });

  // Go from the module on show straight to `to`; when the trip ends, follow any newer pick.
  const travel = (to) => {
    const from = shown.current;
    const rest = `rest_${to}.webp`;
    if (from === to) { show(rest); return; }
    shown.current = to;
    warm(to);
    busy.current = true;
    const t = ++token.current;
    const path = spinPath(from, to);
    const moving = reduced() || !path.every(ready) ? fadeTo(rest, t) : play(path, t);
    moving.then(() => {
      busy.current = false;
      hurry.current = false;
      if (t !== token.current) return; // a dive took over
      show(rest);
      if (cb.current.slot !== to) travel(cb.current.slot);
    });
  };

  // The chosen module changed: travel there, or hurry the trip under way and continue from its end.
  useEffect(() => {
    if (busy.current) { hurry.current = true; return; }
    travel(slot);
  }, [slot, base]); // eslint-disable-line react-hooks/exhaustive-deps

  useImperativeHandle(ref, () => ({
    dive: async () => {
      const t = ++token.current;
      setDiving(true);
      const path = frames(`dive_${shown.current}`);
      if (!reduced() && path.every(ready)) await play(path, t);
      await fadeTo(null, t); // the module's page takes over from the glass
    },
  }), []); // eslint-disable-line react-hooks/exhaustive-deps

  const step = (dir) => {
    const { slot: s, count: n, onPick: pick } = cb.current;
    const to = Math.max(0, Math.min(n - 1, s + dir));
    if (to !== s) pick?.(to);
  };

  // Drag sideways: one module per gesture. A still click picks the stretch under it.
  const down = (e) => {
    if (e.button > 0) return;
    drag.current = { x: e.clientX, y: e.clientY, used: false };
  };
  const move = (e) => {
    const d = drag.current;
    if (!d || d.used) return;
    const dx = e.clientX - d.x;
    if (Math.abs(dx) > SWIPE_PX && Math.abs(dx) > Math.abs(e.clientY - d.y)) {
      d.used = true;
      step(dx < 0 ? 1 : -1);
    }
  };
  const up = (e) => {
    const d = drag.current;
    drag.current = null;
    if (!d || d.used || Math.hypot(e.clientX - d.x, e.clientY - d.y) > 6) return;
    const hit = hitTest(img.current, e.clientX, e.clientY);
    if (!hit) return;
    const { slot: s, count: n } = cb.current;
    const to = slotAt(hit.y, s, n);
    if (to !== s) cb.current.onPick?.(to);
  };

  // Touchpad: a sideways swipe turns one module; vertical scrolls the page.
  useEffect(() => {
    const el = img.current;
    const arb = createArbiter();
    let travel = 0;
    let spent = false;
    let quiet = 0;
    const wheel = (e) => {
      const r = arbitrate(arb, e);
      if (r.action !== 'scroll') e.preventDefault();
      if (r.fresh) { travel = 0; spent = false; }
      if (r.action === 'spin' && !spent) {
        travel += r.px;
        if (Math.abs(travel) > SWIPE_PX) { spent = true; step(travel > 0 ? 1 : -1); }
      }
      clearTimeout(quiet);
      quiet = setTimeout(() => { travel = 0; spent = false; }, 160);
    };
    el.addEventListener('wheel', wheel, { passive: false });
    return () => { clearTimeout(quiet); el.removeEventListener('wheel', wheel); };
  }, []);

  const key = (e) => {
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') step(1);
    else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') step(-1);
    else return;
    e.preventDefault();
  };

  return (
    <div
      className="dna-helix"
      data-diving={diving ? '' : undefined}
      tabIndex={0}
      role="group"
      aria-roledescription="hélice"
      aria-label={`${label}. Flechas para cambiar de módulo.`}
      onKeyDown={key}
    >
      <img
        ref={img}
        className="dna-helix__frame"
        src={`${base}rest_${first}.webp`}
        alt=""
        draggable="false"
        onPointerDown={down}
        onPointerMove={move}
        onPointerUp={up}
        onPointerCancel={() => { drag.current = null; }}
      />
    </div>
  );
});

/** Where a click falls on the frame (object-fit: cover), or null on clear glass or empty ground. */
function hitTest(el, cx, cy) {
  if (!el?.naturalWidth) return null;
  const r = el.getBoundingClientRect();
  const [px, py] = getComputedStyle(el).objectPosition.split(' ').map((v) => parseFloat(v) / 100);
  const s = Math.max(r.width / el.naturalWidth, r.height / el.naturalHeight);
  const x = (cx - r.left - (r.width - el.naturalWidth * s) * px) / s;
  const y = (cy - r.top - (r.height - el.naturalHeight * s) * py) / s;
  if (x < 0 || y < 0 || x >= el.naturalWidth || y >= el.naturalHeight) return null;
  try {
    const ctx = Object.assign(document.createElement('canvas'), { width: 1, height: 1 }).getContext('2d');
    ctx.drawImage(el, x, y, 1, 1, 0, 0, 1, 1);
    if (ctx.getImageData(0, 0, 1, 1).data[3] < 40) return null;
  } catch { /* no canvas: count the click */ }
  return { y: y / el.naturalHeight };
}

export default DnaHelix;
