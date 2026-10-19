import React, { useCallback, useMemo, useState, useEffect, useRef } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ArrowRight } from 'lucide-react';
import AccountMenu from '../../components/AccountMenu/AccountMenu';
import Buttondownload from '../../components/Buttondownload';
import DnaHelix from '../../components/DnaHelix/DnaHelix';
import { useLatestGenomicsResults } from '../../hooks/useLatestGenomicsResults';
import { ancestryGroups, helixReadings, helixTeasers } from './helixTeasers';
import ModuleTitle from '../../components/ModuleTitle/ModuleTitle';
import HelixMessages from './HelixMessages';
import { RESULT_MODULES as MODULES, SLOT_KEY } from '../../config/resultNav';
import './Dashboard.css';


// Coming back from a module page lands on the same stretch of the helix.
const savedSlot = () => {
  try {
    const n = Number(sessionStorage.getItem(SLOT_KEY));
    return Number.isInteger(n) && n >= 0 && n < MODULES.length ? n : 0;
  } catch {
    return 0;
  }
};

const isPhone = () => window.matchMedia?.('(max-width: 860px)').matches ?? false;
const reducedMotion = () => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false;
const IDLE_MS = 10000; // untouched this long, the helix starts touring
// The tour follows Genomin, not a clock: a module turns away only once its line has been read, plus a beat.
const TOUR_MIN_MS = 15000; // every module stays at least this long, said or quiet
const TOUR_REST_MS = 1800; // after a long line fades, before the helix turns on

const Dashboard = ({ user, onLogout }) => {
  const [active, setActive] = useState(savedSlot);
  const helix = useRef(null);
  const entering = useRef(false);
  const navigate = useNavigate();
  const results = useLatestGenomicsResults();

  useEffect(() => {
    try { sessionStorage.setItem(SLOT_KEY, String(active)); } catch { /* private mode: start on Ancestría */ }
  }, [active]);

  const firstName = useMemo(() => {
    const name = [user?.first_name, user?.firstName, user?.name, user?.username].find(Boolean);
    return name ? String(name).split(' ')[0] : null;
  }, [user]);

  const teasers = useMemo(() => helixTeasers(results.data), [results.data]);
  const shares = useMemo(() => ancestryGroups(results.data).map(([, p]) => p), [results.data]);
  const readings = useMemo(() => helixReadings(results.data), [results.data]);
  const stage = useRef(null);

  // Standby: left alone, the helix tours the modules on its own; any move hands it back, where it stands.
  const [touring, setTouring] = useState(false);
  const tourLine = useRef(null); // while touring: hears when Genomin starts and ends a line
  const onLine = useCallback((phase) => tourLine.current?.(phase), []);
  useEffect(() => {
    if (reducedMotion()) return undefined;
    let idle = 0, step = 0, since = 0;
    const wait = (ms) => { clearTimeout(step); step = setTimeout(next, ms); };
    function next() {
      if (!document.hidden && !entering.current) setActive((a) => (a + 1) % MODULES.length);
      since = Date.now();
      wait(TOUR_MIN_MS);
    }
    const start = () => {
      setTouring(true);
      tourLine.current = (phase) => (phase === 'start'
        ? clearTimeout(step)
        : wait(Math.max(TOUR_REST_MS, TOUR_MIN_MS - (Date.now() - since))));
      next();
    };
    const wake = () => {
      clearTimeout(idle); clearTimeout(step);
      tourLine.current = null;
      setTouring(false);
      idle = setTimeout(start, IDLE_MS);
    };
    // no 'scroll': the tour itself glides the phone's list; a reader's scroll starts as wheel or touch
    const events = ['pointerdown', 'pointermove', 'keydown', 'wheel', 'touchstart'];
    events.forEach((e) => window.addEventListener(e, wake, { passive: true, capture: true }));
    wake();
    return () => {
      clearTimeout(idle); clearTimeout(step);
      tourLine.current = null;
      events.forEach((e) => window.removeEventListener(e, wake, { capture: true }));
    };
  }, []);

  const module = MODULES[active];
  const teaser = teasers[module.key];

  const enter = async (e) => {
    if (e && (e.button > 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey)) return; // new tab: let the link work
    e?.preventDefault();
    if (entering.current) return;
    entering.current = true;
    await helix.current?.dive();
    navigate(module.href, { viewTransition: true });
  };

  // The phone's list: its scroll picks the module nearest the middle. A pick made elsewhere (a tap, the
  // helix) steers the list there, and the scroll events of that glide do not pick on the way.
  const list = useRef(null);
  const steering = useRef(null);
  const steered = useRef(false); // the first placement (back from a module) jumps, later ones glide
  const rowHeight = () => list.current?.querySelector('li')?.offsetHeight || 0;
  const onListScroll = () => {
    const el = list.current, h = rowHeight();
    if (!el || !h) return;
    if (steering.current) {
      clearTimeout(steering.current);
      steering.current = setTimeout(() => { steering.current = null; }, 140);
      return;
    }
    const i = Math.max(0, Math.min(MODULES.length - 1, Math.round(el.scrollTop / h)));
    if (i !== active) setActive(i);
  };
  useEffect(() => {
    const el = list.current, h = rowHeight();
    if (!el || !h || el.scrollHeight <= el.clientHeight) return; // desktop: a still legend
    const top = active * h;
    if (Math.abs(el.scrollTop - top) <= h / 2) return;
    clearTimeout(steering.current);
    steering.current = setTimeout(() => { steering.current = null; }, 600);
    el.scrollTo({ top, behavior: steered.current && !reducedMotion() ? 'smooth' : 'auto' });
    steered.current = true;
  }, [active]);

  let line;
  if (results.status === 'loading') {
    line = <span className="hx__line-loading">Cargando tu resumen…</span>;
  } else if (results.status === 'ready' && teaser) {
    line = null; // the title speaks alone once the results are in
  } else if (results.status === 'error') {
    line = (
      <>
        No pudimos cargar tu resumen.{' '}
        <button type="button" className="hx__retry" onClick={results.retry}>Reintentar</button>
      </>
    );
  } else if (results.status === 'ready') {
    line = 'Este módulo no trae datos en tu informe.';
  } else {
    line = 'Tus resultados aparecerán aquí cuando estén publicados.';
  }

  return (
    <div className="dashboard">
      <main
        className="dashboard__main dashboard__main--stage"
        style={{ '--tint': module.tint, '--ink': module.ink, '--rung': module.rung }}
      >
        <section className="hx" aria-labelledby="hx-title" ref={stage}>
          <header className="hx__bar">
            <p className="hx__hello">{firstName ? `Hola, ${firstName}` : 'Hola'}</p>
            <AccountMenu user={user} onLogout={onLogout} />
          </header>

          <div className="hx__stage">
            <DnaHelix
              ref={helix}
              slot={active}
              count={MODULES.length}
              label={`Tu ADN, tramo de ${module.name}`}
              onPick={setActive}
            />
          </div>

          {results.status === 'ready' && (
            <HelixMessages root={stage} moduleKey={module.key} readings={readings[module.key]} rung={module.rung} onLine={onLine} />
          )}

          <div className="hx__copy">
            <ModuleTitle id="hx-title" className="hx__title" key={module.key} moduleKey={module.key} shares={shares} />
            {/* the figure and the way in; on the phone the list carries both, so these step aside */}
            <div className="hx__way">
              {line && <p className="hx__line" key={`${module.key}-${results.status}`} aria-busy={results.status === 'loading'}>{line}</p>}
              <Link to={module.href} className="hx__enter" onClick={enter} key={`${module.key}-cta`}>
                <span className="hx__enter-text">{module.cta}</span>
                <ArrowRight className="hx__enter-arrow" size={22} strokeWidth={2.25} aria-hidden="true" />
              </Link>
            </div>

            {/* The legend of the helix: same order top to bottom, each dot the colour of its stretch.
                On the phone it is the list over the helix: scrolling it turns the helix, the centred one enters. */}
            <nav className="hx__mods" aria-label="Módulos" ref={list} onScroll={onListScroll}>
              <ul>
                {MODULES.map((m, i) => (
                  <li key={m.key}>
                    <button
                      type="button"
                      style={{ '--dot': m.rung }}
                      aria-current={i === active ? 'true' : undefined}
                      onPointerDown={(e) => { if (e.button === 0 && !isPhone()) setActive(i); }}
                      onClick={(e) => (isPhone() && i === active ? enter(e) : setActive(i))}
                    >
                      <span className="hx__mod-full">{m.name}</span>
                      {m.short && <span className="hx__mod-short" aria-hidden="true">{m.short}</span>}
                      <span className="hx__mod-title" aria-hidden="true">{m.title}</span>
                      <span className="hx__mod-go" aria-hidden="true">{m.cta}</span>
                    </button>
                  </li>
                ))}
              </ul>
            </nav>

            <div className="hx__notice"><Buttondownload /></div>
          </div>

          {/* the standby tour turns on its own: announce only the reader's own picks */}
          <p className="hx__live" aria-live="polite">{touring ? '' : `${module.name}: ${module.title}`}</p>
        </section>
      </main>
    </div>
  );
};

export default Dashboard;
