import { useEffect, useState } from 'react';
import { cn } from '@/lib/utils';

// Text Decoder, from 21st.dev (@shadcnspace/animated-text-09). Changes for GenomIA: one pass instead of a
// loop, its length set by `duration` (decode 30%, hold 46%, re-encrypt 16%, then it rests encrypted), `encrypt`
// false to decode and stay readable, and it wraps like normal text instead of `whitespace-pre`.

const DEFAULT_GLYPHS = '▓▒░#%&*@$€£¥☰01QKR';

function usePrefersReducedMotion() {
  const [reduced, setReduced] = useState(false);

  useEffect(() => {
    const query = window.matchMedia?.('(prefers-reduced-motion: reduce)');
    if (!query) return undefined;
    setReduced(query.matches);
    const onChange = () => setReduced(query.matches);
    query.addEventListener('change', onChange);
    return () => query.removeEventListener('change', onChange);
  }, []);

  return reduced;
}

export function TextDecoder({
  text = 'SHADCNSPACE',
  glyphs = DEFAULT_GLYPHS,
  className,
  inkColor,
  accentColor,
  scrambleColor,
  duration = 4000,
  encrypt = true,
}) {
  const reducedMotion = usePrefersReducedMotion();
  const [output, setOutput] = useState(text);
  const [settled, setSettled] = useState(false);

  useEffect(() => {
    const chars = Array.from(text);

    if (reducedMotion || chars.length === 0) {
      setOutput(text);
      setSettled(true);
      return undefined;
    }

    const decodeMs = duration * 0.3;
    const holdMs = duration * 0.46;
    const encryptMs = duration * 0.16;
    const tick = 55;

    let elapsed = 0;
    const glyph = () => glyphs[Math.floor(Math.random() * glyphs.length)] ?? '#';

    const id = window.setInterval(() => {
      elapsed += tick;
      let frame = '';
      let isSettled = false;

      if (elapsed < decodeMs) {
        const progress = elapsed / decodeMs;
        for (let i = 0; i < chars.length; i++) {
          frame += chars[i] === ' ' ? ' ' : i / chars.length < progress ? chars[i] : glyph();
        }
      } else if (!encrypt || elapsed < decodeMs + holdMs) {
        isSettled = true;
        frame = text;
        if (!encrypt) window.clearInterval(id);
      } else {
        const progress = Math.min(1, (elapsed - decodeMs - holdMs) / encryptMs);
        for (let i = 0; i < chars.length; i++) {
          frame += chars[i] === ' ' ? ' ' : i / chars.length >= progress ? chars[i] : glyph();
        }
        if (progress >= 1) window.clearInterval(id);
      }

      setOutput(frame);
      setSettled(isSettled);
    }, tick);

    return () => window.clearInterval(id);
  }, [text, glyphs, duration, encrypt, reducedMotion]);

  const scramble = scrambleColor ?? 'var(--primary)';
  const accent = accentColor ?? 'var(--primary)';
  const ink = inkColor ?? 'currentColor';

  const style = {
    color: settled ? ink : scramble,
    textShadow: `0 0 ${settled ? '0.35em' : '0.4em'} color-mix(in oklch, ${settled ? accent : scramble} ${settled ? 30 : 45}%, transparent)`,
  };

  return (
    <span
      role="img"
      aria-label={text}
      data-settled={settled}
      className={cn(
        'font-medium inline-block',
        'transition-[color,text-shadow] duration-200 ease-out motion-reduce:transition-none',
        className,
      )}
      style={style}
    >
      {output}
    </span>
  );
}

export default TextDecoder;
