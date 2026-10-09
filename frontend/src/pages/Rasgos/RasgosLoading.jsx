import React from 'react';
import { Menu } from 'lucide-react';
import { DashboardPageSkeleton, SkeletonBlock } from '../../components/DashboardSkeleton/DashboardSkeleton';
import './Rasgos.css';

const categoryRows = [0, 1, 2, 3, 4];
const navigationRows = [0, 1, 2, 3];

export const RasgosHeader = () => (
  <header className="rasgos-header">
    <span className="rasgos-header__kicker">Resultados</span>
    <h1 className="rasgos-header__title">
      Rasgos <span className="rasgos-header__accent">genéticos</span>
    </h1>
    <p className="rasgos-header__subtitle">Consulta los valores del módulo de rasgos.</p>
  </header>
);

export const RasgosLoadingContent = () => (
  <DashboardPageSkeleton className="rasgos-loading" label="Cargando datos…">
    <div className="rasgos-overview">
      <div className="rasgos-overview__intro">
        <SkeletonBlock className="rasgos-loading__eyebrow" />
        <SkeletonBlock className="rasgos-loading__hint" />
      </div>
      <div className="rasgos-overview__body">
        <div className="rasgos-overview__chart">
          <span className="rasgos-loading__donut">
            <SkeletonBlock className="rasgos-loading__donut-center" />
          </span>
        </div>
        <div className="rasgos-overview__legend">
          {categoryRows.map((index) => (
            <div className="rasgos-loading__legend-item" key={index}>
              <SkeletonBlock className="rasgos-loading__marker" />
              <span className="rasgos-loading__legend-copy">
                <SkeletonBlock className="rasgos-loading__legend-name" />
                <SkeletonBlock className="rasgos-loading__legend-count" />
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  </DashboardPageSkeleton>
);

const RasgosLoading = () => (
  <div className="rasgos-layout rasgos-layout--loading">
    <span className="rasgos-layout__burger rasgos-loading__menu" aria-hidden="true">
      <Menu size={24} />
    </span>
    <aside className="rasgos-layout__sidebar" aria-hidden="true">
      <div className="rasgos-loading__sidebar">
        <span className="rasgos-loading__sidebar-brand" />
        <div className="rasgos-loading__sidebar-nav">
          {navigationRows.map((index) => <span key={index} />)}
        </div>
      </div>
    </aside>
    <main className="rasgos-layout__main">
      <div className="rasgos-page">
        <RasgosHeader />
        <RasgosLoadingContent />
      </div>
    </main>
  </div>
);

export default RasgosLoading;
