import React from 'react';
import { Search } from 'lucide-react';
import ModuleTitle from '../../components/ModuleTitle/ModuleTitle';
import ResultsBar from '../../components/ResultsBar/ResultsBar';
import './Farmacogenetica.css';

export const PGX_TITLE = 'Tus remedios';

const Bar = ({ className = '', width }) => (
  <span className={`pgx-skel ${className}`.trim()} style={width ? { '--w': width } : undefined} />
);

// Placeholder widths follow real medication names and their uses, so the grid keeps its rhythm.
const CARDS = [['38%', '30%'], ['44%', '18%'], ['40%', '36%'], ['34%', '28%'], ['42%', '34%'], ['46%', '24%']];

const GhostCard = ({ name, use }) => (
  <li>
    <span className="pgx-card pgx-card--ghost">
      <span className="pgx-card__head">
        <Bar className="pgx-skel--name" width={name} />
        <Bar className="pgx-skel--use" width={use} />
      </span>
      <span className="pgx-card__say"><Bar width="100%" /><Bar width="100%" /><Bar width="62%" /></span>
      <span className="pgx-rule">
        <span className="pgx-rule__caps" />
        <span className="pgx-rule__track" style={{ '--n': 5 }}>{[0, 1, 2, 3, 4].map((k) => <span key={k} />)}</span>
        <span className="pgx-rule__labels"><Bar width="2.5rem" /><Bar width="4rem" /></span>
      </span>
    </span>
  </li>
);

/**
 * The page while its results load, built from the page's own classes: the fixed words are real
 * text, only the data (the counts, the group, the medication cards) waits as shapes. It sits
 * exactly where the content lands, so nothing moves when the results arrive.
 */
export const PgxLoadingContent = ({ label = 'Cargando datos…' }) => (
  <section className="pgx-loading" role="status" aria-live="polite" aria-busy="true">
    <span className="pgx-sr">{label}</span>
    <div aria-hidden="true">
      <p className="pgx-hero__lede"><Bar width="100%" /><Bar width="100%" /><Bar width="40%" /></p>
      <div className="pgx-kit">
        <span className="pgx-kit__label">¿Cuáles tomas o te recetaron?</span>
        <span className="pgx-search"><Search size={20} /><span className="pgx-search__ghost">Busca un medicamento</span></span>
        <p className="pgx-kit__hint">Tu lista no se guarda ni se envía: vive solo en esta pantalla.</p>
      </div>
      <span className="pgx-lens">
        <span className="pgx-lens__item is-on">Por medicamento</span>
        <span className="pgx-lens__item">Por gen</span>
      </span>
      <div className="pgx-group">
        <Bar className="pgx-skel--h2" width="17rem" />
        <p><Bar width="100%" /><Bar width="100%" /><Bar className="pgx-skel--narrow" width="40%" /></p>
        <ul className="pgx-cards">{CARDS.map(([name, use]) => <GhostCard key={name + use} name={name} use={use} />)}</ul>
      </div>
    </div>
  </section>
);

/** The whole page while the session or the page itself loads: the real bar, title and page shape. */
export const FarmacoPageSkeleton = () => (
  <div className="farmacogenetica-layout-new">
    <main className="farmaco-main-content">
      <ResultsBar />
      <div className="pgx">
        <header className="pgx-hero"><ModuleTitle className="pgx-title" moduleKey="pharmacogenetics" title={PGX_TITLE} /></header>
        <PgxLoadingContent />
      </div>
    </main>
  </div>
);
