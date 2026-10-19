import { useEffect, useRef } from 'react';
import { FRAMES, frameForAngle } from '../../components/DnaHelix/helixMath';

const src = (i) => `/dna/${String(i).padStart(3, '0')}.webp`;
const SPEED = 360 / 6; // degrees per second: one turn every 6 s

/**
 * The rendered glass helix, turning on its own; decorative, it takes no input.
 * Frames load only near the viewport and the loop sleeps off screen.
 * Reduced motion: it holds still on its first frame.
 */
export default function DnaTurntable() {
  const wrap = useRef(null);
  const canvas = useRef(null);

  useEffect(() => {
    const el = wrap.current;
    const cv = canvas.current;
    const ctx = cv.getContext?.('2d');
    if (!ctx) return undefined; // no canvas (tests, very old browsers): the poster stays
    if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) return undefined;

    const imgs = [];
    let angle = 0;
    let visible = false;
    let raf = 0;
    let last = 0;
    let shown = -1;

    const fit = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      cv.width = Math.min(800, Math.round(cv.clientWidth * dpr));
      cv.height = Math.round(cv.width * 1.25);
      shown = -1;
    };

    const draw = () => {
      const i = frameForAngle(angle);
      const img = imgs[i]?.complete ? imgs[i] : imgs.find((m) => m?.complete); // a frame still loading: show one that is ready
      if (!img || i === shown) return;
      ctx.clearRect(0, 0, cv.width, cv.height);
      ctx.drawImage(img, 0, 0, cv.width, cv.height);
      shown = i;
      el.dataset.ready = '';
    };

    const tick = (t) => {
      angle = (angle + Math.min((t - (last || t)) / 1000, 0.05) * SPEED) % 360;
      last = t;
      draw();
      raf = visible ? requestAnimationFrame(tick) : 0;
    };

    const near = new IntersectionObserver(([e]) => {
      if (!e.isIntersecting) return;
      near.disconnect();
      for (let i = 0; i < FRAMES; i++) {
        const img = new Image();
        img.decoding = 'async';
        img.src = src(i);
        imgs.push(img);
      }
    }, { rootMargin: '800px 0px' });
    const onScreen = new IntersectionObserver(([e]) => {
      visible = e.isIntersecting;
      if (visible && !raf) { last = 0; raf = requestAnimationFrame(tick); }
    });
    near.observe(el);
    onScreen.observe(el);
    const ro = new ResizeObserver(() => { fit(); draw(); });
    ro.observe(cv);

    return () => {
      cancelAnimationFrame(raf);
      near.disconnect();
      onScreen.disconnect();
      ro.disconnect();
    };
  }, []);

  return (
    <div ref={wrap} className="gp-dna">
      <img className="gp-dna__poster" src={src(0)} alt="" width="800" height="1000" decoding="async" />
      <canvas ref={canvas} className="gp-dna__canvas" />
    </div>
  );
}
