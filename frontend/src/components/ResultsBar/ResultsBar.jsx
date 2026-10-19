import React, { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { motion as Motion, useReducedMotion, useSpring } from 'motion/react';
import { ArrowLeft } from 'lucide-react';
import AccountMenu from '../AccountMenu/AccountMenu';
import { RESULT_MODULES, SLOT_KEY } from '../../config/resultNav';
import './ResultsBar.css';

const GUIDE_COLOURS = { ink: '#0f2341', tint: '#e3ecfa', rung: '#4f8fd6' };
// Critically damped (damping = 2·√stiffness): a tap carries no momentum, so the pill never overshoots.
const PILL = { stiffness: 380, damping: 39 };
// How long the pill keeps following its module while the names open and close (the CSS takes 0.45s).
const FOLLOW_MS = 600;

// Every result page mounts its own bar, so the module last on show is kept here: the new bar opens
// on it and travels to the new one, instead of appearing already there.
let lastShown = null;

// Riesgo poligénico and monogénico share one page; the hash picks which (poligénico when none).
const activeIndex = (pathname, hash) => RESULT_MODULES.findIndex((m) => {
  const [path, anchor] = m.href.split('#');
  if (path !== pathname) return false;
  return !anchor || hash === `#${anchor}` || (!hash && anchor === 'polygenic_risk');
});

/**
 * The bar on top of every result page: back to the helix, the five modules as the helix's
 * coloured dots (the one on show named), and the account menu.
 * Moving between modules is one continuous motion: the old name closes while the new one opens,
 * the pill glides under them and the colours crossfade. Other names show as a label under the
 * pointer, so hovering never moves the dots.
 */
const ResultsBar = ({ user, onLogout }) => {
  const { pathname, hash } = useLocation();
  const active = activeIndex(pathname, hash);
  const reduce = useReducedMotion();
  const [shown, setShown] = useState(() => (lastShown !== null && active >= 0 ? lastShown : active));
  const colours = RESULT_MODULES[shown] || GUIDE_COLOURS;
  const links = useRef([]);
  const placed = useRef(false);
  const x = useSpring(0, PILL);
  const width = useSpring(0, PILL);

  // Back on the dashboard, the helix waits on the module the client last read.
  useEffect(() => {
    if (active < 0) return;
    try { sessionStorage.setItem(SLOT_KEY, String(active)); } catch { /* private mode */ }
  }, [active]);

  // One frame on the old module, then over to the new one, so the change is seen happening.
  useEffect(() => {
    if (active >= 0) lastShown = active;
    if (shown === active) return undefined;
    const frame = requestAnimationFrame(() => setShown(active));
    return () => cancelAnimationFrame(frame);
  }, [active, shown]);

  // The pill chases its module's live box while the names resize, so it glides and grows with them.
  useLayoutEffect(() => {
    const link = links.current[shown];
    if (!link) return undefined;
    const place = (now) => {
      if (now || reduce) {
        x.jump(link.offsetLeft);
        width.jump(link.offsetWidth);
      } else {
        x.set(link.offsetLeft);
        width.set(link.offsetWidth);
      }
    };
    place(!placed.current);
    placed.current = true;
    const start = performance.now();
    let frame = requestAnimationFrame(function follow(t) {
      place(false);
      if (t - start < FOLLOW_MS) frame = requestAnimationFrame(follow);
    });
    const resize = () => place(true);
    window.addEventListener('resize', resize);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener('resize', resize);
    };
  }, [shown, reduce, x, width]);

  return (
    <>
    <div className="rbar-space" aria-hidden="true" />
    <header className="rbar" style={{ '--ink': colours.ink, '--tint': colours.tint, '--rung': colours.rung }}>
      <Link to="/dashboard" className="rbar__back" aria-label="Volver a tu ADN">
        <ArrowLeft size={22} strokeWidth={2.25} aria-hidden="true" />
      </Link>

      <nav className="rbar__strand" aria-label="Módulos">
        {shown >= 0 && <Motion.span className="rbar__pill" aria-hidden="true" style={{ x, width }} />}
        {RESULT_MODULES.map((m, i) => (
          <Link
            key={m.key}
            ref={(node) => { links.current[i] = node; }}
            to={m.href}
            className="rbar__mod"
            style={{ '--dot': m.rung }}
            data-name={m.name}
            data-shown={i === shown ? '' : undefined}
            aria-current={i === active ? 'page' : undefined}
          >
            <span className="rbar__name">
              <span className="rbar__label">
                <span className="rbar__full">{m.name}</span>
                {m.short && <span className="rbar__short" aria-hidden="true">{m.short}</span>}
              </span>
            </span>
          </Link>
        ))}
      </nav>

      <AccountMenu user={user} onLogout={onLogout} />
    </header>
    </>
  );
};

export default ResultsBar;
