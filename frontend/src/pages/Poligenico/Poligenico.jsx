import React, { useEffect, useId, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { ChevronDown } from 'lucide-react';
import { clearToken } from '../../config/api';
import { moduleRows, useLatestGenomicsResults } from '../../hooks/useLatestGenomicsResults';
import { useSession } from '../../hooks/useSession';
import ModuleTitle from '../../components/ModuleTitle/ModuleTitle';
import ResultsBar from '../../components/ResultsBar/ResultsBar';
import { CATEGORY_PLAIN, alsoFor, below, zOf } from './polygenic';
import './Poligenico.css';

const resultMessages = {
  loading: 'Cargando datos…',
  empty: 'Aún no tienes resultados disponibles.',
  missing: 'Tu último servicio no tiene resultados de riesgo.',
  permission: 'No tienes permiso para consultar estos resultados.',
  error: 'No fue posible cargar los datos. Puedes reintentar.',
  ready: 'Datos disponibles.',
};

// The population bell with the reader's place; the people below them are filled in.
const BELL = Array.from({ length: 61 }, (_, k) => {
  const z = -3 + k / 10;
  return `${k ? 'L' : 'M'}${(150 + z * 46).toFixed(1)} ${(84 - Math.exp(-z * z / 2) * 70).toFixed(1)}`;
}).join('');

const Bell = ({ percentile }) => {
  const clip = useId();
  const z = zOf(percentile);
  const x = 150 + z * 46;
  const y = 84 - Math.exp(-z * z / 2) * 70;
  return (
    <svg className="pgs-bell" viewBox="0 0 300 104" aria-hidden="true">
      <clipPath id={clip}><rect x="0" y="0" width={x} height="104" /></clipPath>
      <path className="pgs-bell__all" d={`${BELL}Z`} />
      <path className="pgs-bell__below" d={`${BELL}Z`} clipPath={`url(#${clip})`} />
      <line className="pgs-bell__mean" x1="150" y1="14" x2="150" y2="84" />
      <text className="pgs-bell__label" x="150" y="100">promedio</text>
      <line className="pgs-bell__stem" x1={x} y1={y} x2={x} y2="84" />
      <circle className="pgs-bell__you" cx={x} cy={y} r="6.5" />
    </svg>
  );
};

const Row = ({ risk, open, onToggle, detailId }) => {
  const name = risk.label || risk.condition;
  const lower = name.toLowerCase();
  return (
    <div className={`pgs-row${open ? ' is-open' : ''}`}>
      <button type="button" className="pgs-row__head" aria-expanded={open} aria-controls={open ? detailId : undefined}
        onClick={onToggle}>
        <span className="pgs-row__name">{name}</span>
        <span className="pgs-row__place">
          <b>{Math.round(risk.percentile)}</b> de cada 100
          <span className="pgs-row__cat">{CATEGORY_PLAIN[risk.category] ?? risk.category}</span>
        </span>
        <ChevronDown size={20} className="pgs-chev" aria-hidden="true" />
      </button>
      {open && (
        <div className="pgs-halves" id={detailId}>
          <section className="pgs-half" aria-label="Tu genética">
            <h3>Tu genética</h3>
            <p className="pgs-big"><b>{below(risk.percentile)}</b> de cada 100 personas quedan por debajo de ti</p>
            <Bell percentile={risk.percentile} />
            <p>Se sumaron <b>{risk.risk_loci} variantes</b> comunes; cada una mueve muy poco y ninguna decide sola.</p>
          </section>
          <section className="pgs-half pgs-half--not" aria-label="Lo que este número no mide">
            <h3>Lo que este número no mide</h3>
            <p className="pgs-not__lead">Esto no se suma ni se resta a tu puntaje.</p>
            <dl className="pgs-not">
              <div>
                <dt>No es tu probabilidad</dt>
                <dd>Dice tu lugar entre 100 personas, no si vas a tener {lower}.</dd>
              </div>
              <div>
                <dt>No conoce tu vida</dt>
                <dd>No sabe tu edad, tu familia ni tus hábitos.</dd>
              </div>
              <div>
                <dt>Pesa igual o más</dt>
                <dd>{alsoFor(risk.condition)}</dd>
              </div>
            </dl>
          </section>
        </div>
      )}
    </div>
  );
};

const PgsLoading = () => (
  <section className="pgs-loading" role="status" aria-live="polite" aria-busy="true">
    <span className="pgs-sr">{resultMessages.loading}</span>
    <div className="pgs-sheet" aria-hidden="true">
      {[0, 1, 2, 3, 4].map((key) => <div className="pgs-skel-row" key={key}><span /><b /></div>)}
    </div>
  </section>
);

const Poligenico = () => {
  const { user } = useSession();
  const navigate = useNavigate();
  const { hash } = useLocation();
  const results = useLatestGenomicsResults();
  const risks = moduleRows(results, 'polygenic_risk');
  const status = results.status === 'ready' && !risks.length ? 'missing' : results.status;
  const failed = ['permission', 'error'].includes(status);
  const [open, setOpen] = useState(0);
  const uid = useId();

  // The dashboard's risk card links here with #polygenic_risk.
  useEffect(() => {
    if (status !== 'ready' || !hash) return;
    const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    document.getElementById(decodeURIComponent(hash.slice(1)))
      ?.scrollIntoView?.({ block: 'start', behavior: reduce ? 'auto' : 'smooth' });
  }, [hash, status]);

  const handleLogout = async () => {
    await clearToken();
    navigate('/');
  };

  return (
    <div className="pgs">
      <main className="pgs-main-content">
        <ResultsBar user={user} onLogout={handleLogout} />
        <div className="pgx">
          <header className="pgs-hero">
            <ModuleTitle className="pgs-title" moduleKey="polygenic_risk" />
            {status === 'ready' && (
              <p className="pgs-lede">Para cada condición sumamos muchas variantes pequeñas y vemos <b>dónde queda tu
                puntaje entre 100 personas</b>. Es tu lugar en la fila, no tu probabilidad de enfermar.</p>
            )}
          </header>

          {status === 'loading' && <PgsLoading />}

          {status === 'ready' && (
            <>
              <p className="pgs-sr" role="status" aria-label="Estado de los resultados" aria-busy={false}>
                {resultMessages.ready}
              </p>
              <section className="pgs-sheet" id="polygenic_risk" aria-labelledby="polygenic_risk-title">
                <h2 className="pgs-sr" id="polygenic_risk-title">Tus condiciones</h2>
                {risks.map((risk, index) => (
                  <Row key={risk.condition} risk={risk} open={open === index} detailId={`${uid}-${index}`}
                    onToggle={() => setOpen(open === index ? null : index)} />
                ))}
              </section>
              <footer className="pgs-foot"><p>Esto no es un diagnóstico.</p></footer>
            </>
          )}

          {status !== 'ready' && status !== 'loading' && (
            <div className="pgs-status">
              <p role={failed ? 'alert' : 'status'} aria-label="Estado de los resultados" aria-busy={false}>
                {resultMessages[status]}
              </p>
              <button type="button" className="pgs-retry" aria-label="Reintentar carga de resultados"
                onClick={results.retry}>
                Reintentar
              </button>
            </div>
          )}
        </div>
      </main>
    </div>
  );
};

export default Poligenico;
