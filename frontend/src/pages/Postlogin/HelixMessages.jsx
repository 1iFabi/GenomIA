import { useEffect, useRef, useState } from 'react';
import TextDecoder from '@/components/ui/text-decoder';
import GenominMascot from '@/components/Genomin/GenominMascot';
import './HelixMessages.css';

// Timing (taste-skill motion rules): a recurring, ambient element, so small and quiet; ease-out in, a shorter fade out.
// It never talks over the page: the first line waits until the title has been read, each reading is said once,
// and a module says one line per arrival.
const ARRIVE = 4000; // ms after the page opens before Genomin's first line: the title and figure are read first
const AFTER_PICK = 2200; // ms after a module change: the turn ends and its new title is read first
const TYPE = 3500; // ms Genomin "types" (three dots) before the line appears
const DECODE = 3000; // Text Decoder's pass length; it decodes in its first 30% (~0.9 s)
const READ_PER_WORD = 280; // ms; with READ_BASE, a line stays as long as reading it takes (2.6–5 s)
const READ_BASE = 1200;
const ENTER = 450; // ms the slip takes to arrive (ease-out)
const EXIT = 320; // ms it takes to go, ~70% of the arrival: it simply fades
const GAP = 1500; // ms before trying again when a row finds no glass
const ROWS = [0.42, 0.58, 0.34, 0.66]; // heights of the stretch on show (share of the stage) a message leaves from, in turn
const PHONE_ROWS = [0.3, 0.38];
const TRAVEL = 20; // px: a short drift off the glass, not a flight
// Genomin's pose once the line is out: every clean pose but the two that belong elsewhere (laptop is the typing
// one, durmiendo the widget's idle sleep); presentando, bailando, mostrando_adn and sorprendido still carry their
// sticker border, so they wait until they are cleaned.
const POSES = [
  'apuntando', 'asomandose', 'celebrando', 'corazon', 'corriendo', 'guino_saludo', 'laboratorio', 'leyendo',
  'megafono', 'pensando', 'riendo', 'saltando', 'saludando', 'saludando_ambas_manos', 'selfie', 'tierno',
  'timido', 'trofeo',
];
const shuffled = () => {
  const a = [...POSES];
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
};
const easeOut = (x) => 1 - (1 - Math.min(1, Math.max(0, x))) ** 4;
const readMs = (text) => Math.min(5000, Math.max(2600, text.split(/\s+/).length * READ_PER_WORD + READ_BASE));
const reduced = () => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
const isPhone = () => window.matchMedia?.('(max-width: 860px)').matches;

/** Where the glass crosses the screen row `y`: its left edge and middle (screen px), or null on empty ground. */
function strandAt(img, y) {
  if (!img?.naturalWidth) return null;
  const r = img.getBoundingClientRect();
  const [px, py] = getComputedStyle(img).objectPosition.split(' ').map((v) => parseFloat(v) / 100);
  const s = Math.max(r.width / img.naturalWidth, r.height / img.naturalHeight);
  const ox = r.left + (r.width - img.naturalWidth * s) * px;
  const ny = Math.round((y - r.top - (r.height - img.naturalHeight * s) * py) / s);
  if (ny < 0 || ny >= img.naturalHeight) return null;
  try {
    const c = Object.assign(document.createElement('canvas'), { width: img.naturalWidth, height: 1 });
    const ctx = c.getContext('2d', { willReadFrequently: true });
    ctx.drawImage(img, 0, ny, img.naturalWidth, 1, 0, 0, img.naturalWidth, 1);
    const a = ctx.getImageData(0, 0, img.naturalWidth, 1).data;
    let first = -1, last = -1;
    for (let x = 0; x < img.naturalWidth; x++) if (a[x * 4 + 3] > 90) { if (first < 0) first = x; last = x; }
    if (first < 0) return null;
    const left = Math.max(ox + first * s, r.left), right = Math.min(ox + last * s, r.right);
    return right > left ? { left, mid: (left + right) / 2 } : null;
  } catch {
    return null;
  }
}

/**
 * Genomin's lines leaving the stretch of the helix on show: one at a time, tied to the glass by a thread,
 * each a different reading of the module's real figure. Genomin sits on the slip: at his laptop while he types
 * (three dots), then in a new pose for every line once it is out. The line decodes out of
 * A, C, G and T (21st.dev's Text Decoder), stays as long as it takes to read, and the slip fades. Each reading is
 * said once per visit, one line each time a module comes up: a module that has said all of its lines goes quiet.
 * Decorative: the page's own line already says the figure, so this stays out of the accessibility tree.
 */
export default function HelixMessages({ root, moduleKey, readings, rung, onLine }) {
  const cap = useRef(null);
  const sizer = useRef(null);
  const wire = useRef(null);
  const turn = useRef({}); // readings already said, per module: coming back continues, never repeats
  const born = useRef(performance.now()); // the first line of the visit waits ARRIVE from here; a later pick, AFTER_PICK
  const [msg, setMsg] = useState(null); // { id, text, typing, pose }
  const deck = useRef({ order: [], at: 0 }); // poses dealt in a shuffled order: every one shows before any repeats

  useEffect(() => {
    const el = cap.current, line = wire.current;
    if (!readings?.length || !el || !line) return undefined;
    const still = readings.length === 1;
    let timer = 0, typed = 0, raf = 0, row = 0;

    const hide = () => { el.style.opacity = 0; line.style.opacity = 0; };

    const say = () => {
      const box = root.current, img = box?.querySelector('.dna-helix__frame');
      // only from a helix at rest on its stretch: never mid-turn, mid-dive or in a hidden tab
      if (!box || !img || document.hidden || !/rest_\d+\.webp$/.test(img.src) || box.querySelector('.dna-helix[data-diving]')) {
        timer = setTimeout(say, 300);
        return;
      }
      const phone = isPhone(), calm = reduced();
      const b = box.getBoundingClientRect();
      const rows = phone ? PHONE_ROWS : ROWS;
      const y = b.top + b.height * rows[row++ % rows.length];
      const strand = strandAt(img, y);
      if (!strand) { timer = setTimeout(say, GAP); return; }

      const copy = phone ? null : box.querySelector('.hx__copy')?.getBoundingClientRect();
      const floor = copy ? copy.right + 24 - b.left : 16; // never over the words
      let room = phone ? Math.min(b.width * 0.62, 272) : Math.min(304, strand.left - b.left - 26 - TRAVEL - floor);
      const over = !phone && room < 220; // a close-up framing: the glass reaches the words, so the slip rests on the glass
      if (over) room = 280;

      const k = turn.current[moduleKey] || 0;
      if (k >= readings.length) return; // all of this module's lines said: quiet until another module
      turn.current[moduleKey] = k + 1;
      const text = readings[k];
      sizer.current.textContent = text; // the hidden copy sizes the slip now; the decoder renders over it
      el.style.width = '';
      el.style.maxWidth = `${room}px`;
      const w = el.offsetWidth, h = el.offsetHeight;
      el.style.width = `${w}px`; // the letters change while it lives; the box must not
      const ax = (phone || over ? strand.mid : strand.left) - b.left, ay = y - b.top;
      const typing = calm ? 0 : TYPE;
      const life = typing + DECODE * 0.3 + readMs(text);
      // Genomin types first (three dots), then the line decodes out of the bases
      const d = deck.current;
      if (d.at >= d.order.length) {
        const last = d.order[d.order.length - 1];
        d.order = shuffled();
        if (d.order[0] === last) d.order.push(d.order.shift()); // no pose twice in a row across decks
        d.at = 0;
      }
      setMsg({ id: `${moduleKey}-${k}`, text, typing: typing > 0, pose: d.order[d.at++] });
      onLine?.('start');
      typed = setTimeout(() => setMsg((m) => (m && { ...m, typing: false })), typing);
      const t0 = performance.now();

      const frame = (now) => {
        const t = now - t0;
        if (t >= life) { hide(); onLine?.('end'); return; } // one line per arrival: the next waits for the next module
        const alpha = Math.min(easeOut(t / (ENTER * 0.7)), (life - t) / EXIT);
        const go = still || calm ? 0 : TRAVEL * easeOut(t / ENTER);
        let left, top, ex, ey;
        if (phone) {
          left = b.width - w - 16; top = Math.max(8, ay - h - 22 - go * 0.4);
          ex = left + w / 2; ey = top + h;
        } else {
          left = over ? floor + TRAVEL - go : ax - 26 - go - w;
          top = Math.min(Math.max(8, ay - h / 2), b.height - h - 8);
          ex = left + w; ey = top + h / 2;
        }
        el.style.opacity = alpha;
        el.style.transform = `translate3d(${left}px, ${top}px, 0)`;
        line.setAttribute('x1', ax); line.setAttribute('y1', ay);
        line.setAttribute('x2', ex); line.setAttribute('y2', ey);
        line.style.opacity = alpha * 0.75 * easeOut((t - ENTER * 0.6) / ENTER); // the thread follows once the slip lands
        raf = requestAnimationFrame(frame);
      };
      raf = requestAnimationFrame(frame);
    };

    timer = setTimeout(say, Math.max(AFTER_PICK, ARRIVE - (performance.now() - born.current)));
    return () => { clearTimeout(timer); clearTimeout(typed); cancelAnimationFrame(raf); hide(); setMsg(null); };
  }, [root, moduleKey, readings, onLine]);

  return (
    <div className="hxm" aria-hidden="true" style={{ '--hxm-rung': rung }}>
      <svg className="hxm__wire"><line ref={wire} /></svg>
      <p className="hxm__cap" ref={cap}>
        {msg && <GenominMascot pose={msg.typing ? 'laptop' : msg.pose} size={92} />}
        <span className="hxm__text">
          <span className="hxm__sizer" ref={sizer} />
          {msg?.typing && <span className="hxm__typing"><i /><i /><i /></span>}
          {msg && !msg.typing && (
            <TextDecoder
              key={msg.id}
              text={msg.text}
              glyphs="ACGT"
              duration={DECODE}
              encrypt={false}
              className="hxm__decoded font-semibold"
              inkColor="var(--ink)"
              accentColor="var(--hxm-rung)"
              scrambleColor="var(--hxm-rung)"
            />
          )}
        </span>
      </p>
    </div>
  );
}
