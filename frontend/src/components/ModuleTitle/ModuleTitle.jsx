import React from 'react';
import { RESULT_MODULES } from '../../config/resultNav';
import './ModuleTitle.css';

// Each module's title borrows one piece of its own page: the ancestry shares paint the letters,
// a capsule stands in for an O, a hand-drawn ring marks "tú", the population curve sits behind,
// and the monogenic title reads one cell per letter like a sequence.

const Ring = () => (
  <svg className="mt__ring" viewBox="0 0 170 130" aria-hidden="true">
    <path pathLength="1" d="M150 40C140 6 30 0 12 48c-14 42 68 80 128 56 36-16 26-58-20-80" />
  </svg>
);

const Curve = () => (
  <svg className="mt__curve" viewBox="0 0 300 60" preserveAspectRatio="none" aria-hidden="true">
    <path className="mt__curve-area" d="M0 58C80 58 105 4 150 4s70 54 150 54Z" />
    <path pathLength="1" d="M0 58C80 58 105 4 150 4s70 54 150 54" />
    <line pathLength="1" x1="150" y1="4" x2="150" y2="58" />
  </svg>
);

// Shares (largest first) become hard colour stops across the word, ink to rung to pale.
const shareFill = (shares) => {
  const total = shares.reduce((sum, s) => sum + s, 0);
  if (shares.length < 2 || !total) return undefined;
  const tones = ['var(--mt-ink)', 'color-mix(in srgb, var(--mt-rung) 80%, var(--mt-ink))', 'var(--mt-rung)', 'color-mix(in srgb, var(--mt-rung) 45%, white)'];
  let at = 0;
  const stops = shares.map((s, i) => {
    const from = at;
    at += (s / total) * 100;
    return `${tones[Math.min(i, tones.length - 1)]} ${from.toFixed(2)}% ${at.toFixed(2)}%`;
  });
  return { backgroundImage: `linear-gradient(90deg, ${stops.join(', ')})` };
};

const body = (key, title, shares) => {
  switch (key) {
    case 'global_ancestry': {
      const fill = shareFill(shares ?? []);
      return fill ? <span className="mt__fill" style={fill}>{title}</span> : title;
    }
    case 'pharmacogenetics': {
      const o = title.toLowerCase().lastIndexOf('o');
      if (o < 0) return title;
      return <>{title.slice(0, o)}<span className="mt__pill">{title[o]}</span>{title.slice(o + 1)}</>;
    }
    case 'traits': {
      const cut = title.lastIndexOf(' ') + 1;
      return <>{title.slice(0, cut)}<span className="mt__marked">{title.slice(cut)}<Ring /></span></>;
    }
    case 'polygenic_risk': {
      // the curve sits under the last word ("promedio") alone, so it fits that word at any width
      const cut = title.lastIndexOf(' ') + 1;
      return <>{title.slice(0, cut)}<span className="mt__avg">{title.slice(cut)}<Curve /></span></>;
    }
    case 'monogenic_risk':
      // words stay whole when the line wraps; the middle letter of the middle word is the one being read
      return title.split(' ').map((word, w) => (
        <React.Fragment key={w}>
          {w > 0 && ' '}
          <span className="mt__word">
            {[...word].map((ch, i) => (
              <span key={i} className={w === 1 && i === Math.floor(word.length / 2) ? 'mt__cell mt__cell--on' : 'mt__cell'}>{ch}</span>
            ))}
          </span>
        </React.Fragment>
      ));
    default:
      return title;
  }
};

const ModuleTitle = ({ moduleKey, title, shares, className = '', ...rest }) => {
  const module = RESULT_MODULES.find((m) => m.key === moduleKey);
  const text = title ?? module?.title ?? '';
  const style = module ? { '--mt-ink': module.ink, '--mt-rung': module.rung, '--mt-tint': module.tint } : undefined;
  return (
    <h1 className={`mt mt--${moduleKey} ${className}`.trim()} style={style} {...rest}>
      {body(moduleKey, text, shares)}
    </h1>
  );
};

export default ModuleTitle;
