import React from 'react';
import { ChevronRight } from 'lucide-react';
import ModuleTitle from '../../components/ModuleTitle/ModuleTitle';
import ResultsBar from '../../components/ResultsBar/ResultsBar';
import './Rasgos.css';

// Placeholder widths follow the real category names, so the legend keeps its rhythm.
const NAME_WIDTHS = ['42%', '78%', '36%', '58%', '52%'];

export const RasgosHeader = () => (
  <header className="rasgos-header">
    <ModuleTitle className="rasgos-header__title" moduleKey="traits" title="Lo que te hace tú" />
    <p className="rasgos-header__subtitle">Lo que tus genes dicen de rasgos de tu día a día, ordenados por categoría.</p>
  </header>
);

const Bar = ({ width }) => <span className="rasgos-loading__bar" style={width ? { '--w': width } : undefined} />;

/**
 * The overview while the results load, built from the overview's own classes: the fixed words are
 * real text, only the data (the donut, the category names and counts) waits as shapes. So it sits
 * exactly where the content lands, and the content fades in over it without moving.
 */
export const RasgosLoadingContent = () => (
  <section className="rasgos-loading" role="status" aria-live="polite" aria-busy="true">
    <span className="rasgos-visually-hidden">Cargando tus rasgos…</span>
    <div className="rasgos-overview" aria-hidden="true">
      <div className="rasgos-overview__intro">
        <span className="rasgos-report__eyebrow">Explorar resultados</span>
        <span className="rasgos-report__hint">Selecciona una categoría</span>
      </div>
      <div className="rasgos-overview__body">
        <div className="rasgos-overview__chart">
          <span className="rasgos-overview__pie rasgos-loading__donut">
            <Bar width="3.25rem" />
          </span>
        </div>
        <div className="rasgos-overview__legend">
          {NAME_WIDTHS.map((width) => (
            <div className="rasgos-overview__legend-item rasgos-loading__row" key={width}>
              <span className="rasgos-overview__legend-marker rasgos-loading__shape" />
              <span className="rasgos-overview__legend-copy">
                <span className="rasgos-overview__legend-name"><Bar width={width} /></span>
                <span className="rasgos-overview__legend-count"><Bar width="3.5rem" /></span>
              </span>
              <ChevronRight size={16} />
            </div>
          ))}
        </div>
      </div>
    </div>
  </section>
);

/** The whole page while the session or the page itself loads: the real bar, header and overview shape. */
export const RasgosPageSkeleton = () => (
  <div className="rasgos-layout">
    <main className="rasgos-layout__main">
      <ResultsBar />
      <div className="rasgos-page">
        <RasgosHeader />
        <RasgosLoadingContent />
      </div>
    </main>
  </div>
);
