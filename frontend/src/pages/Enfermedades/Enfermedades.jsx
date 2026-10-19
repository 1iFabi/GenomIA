import React, { useEffect } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { clearToken } from '../../config/api';
import { moduleRows, useLatestGenomicsResults } from '../../hooks/useLatestGenomicsResults';
import { useSession } from '../../hooks/useSession';
import ResultsBar from '../../components/ResultsBar/ResultsBar';
import { DashboardPageSkeleton, SkeletonBlock } from '../../components/DashboardSkeleton/DashboardSkeleton';
import '../../styles/cards.css';
import './Enfermedades.css';

const ENFERMEDADES_SUBTITLE =
  'Tu riesgo poligénico y las variantes patogénicas encontradas en ClinVar.';

function EnfermedadesPageHeader() {
  return (
    <header className="enfermedades-page-header">
      <span className="enfermedades-page-header__kicker">RESULTADOS</span>
      <h1 className="enfermedades-page-header__title">
        <span className="enfermedades-page-header__title-accent">ENFER</span>
        <span className="enfermedades-page-header__title-neutral">MEDADES</span>
      </h1>
      <p className="enfermedades-page-header__subtitle">{ENFERMEDADES_SUBTITLE}</p>
    </header>
  );
}

const resultMessages = {
  loading: 'Cargando datos…',
  empty: 'Aún no tienes resultados disponibles.',
  missing: 'Tu último servicio no tiene resultados de riesgo.',
  permission: 'No tienes permiso para consultar estos resultados.',
  error: 'No fue posible cargar los datos. Puedes reintentar.',
  ready: 'Datos disponibles.',
};

const formatSignificance = (value) => value?.replaceAll('_', ' ').replace('/', ' / ') ?? '';

function RiskCard({ id, title, empty, children }) {
  return (
    <section className="card-pro card-large-pro" id={id} aria-labelledby={`${id}-title`}>
      <div className="card-pro__header">
        <h2 className="priority-section__title" id={`${id}-title`}>{title}</h2>
      </div>
      {children || <p>{empty}</p>}
    </section>
  );
}

const Enfermedades = () => {
  const { user } = useSession();
  const navigate = useNavigate();
  const { hash } = useLocation();
  const results = useLatestGenomicsResults();
  const polygenic = moduleRows(results, 'polygenic_risk');
  const monogenic = moduleRows(results, 'monogenic_risk');
  const resultStatus = results.status === 'ready' && !polygenic.length && !monogenic.length
    ? 'missing' : results.status;
  const failed = ['permission', 'error'].includes(resultStatus);

  // The dashboard's two risk cards link here with #polygenic_risk or #monogenic_risk.
  useEffect(() => {
    if (resultStatus !== 'ready' || !hash) return;
    const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    document.getElementById(decodeURIComponent(hash.slice(1)))
      ?.scrollIntoView?.({ block: 'start', behavior: reduce ? 'auto' : 'smooth' });
  }, [hash, resultStatus]);

  const handleLogout = async () => {
    await clearToken();
    navigate('/');
  };


  return (
    <div className="enfermedades-layout">


      <main className="enfermedades-layout__main">
        <ResultsBar user={user} onLogout={handleLogout} />
        <div className="enfermedades-page">
          <EnfermedadesPageHeader />
          <div className="enfermedades-page__content">
            {resultStatus === 'loading' ? (
              <DashboardPageSkeleton className="enfermedades-loading" label={resultMessages.loading}>
                <div className="dashboard-pro-3col">
                  {['Riesgo poligénico', 'Variantes patogénicas (ClinVar)'].map((title) => (
                    <section className="card-pro card-large-pro" key={title}>
                      <div className="card-pro__header">
                        <h2 className="priority-section__title">{title}</h2>
                      </div>
                      <div className="legend-pro">
                        {[0, 1, 2].map((index) => (
                          <div className="legend-pro__item enfermedades-loading__row" key={index}>
                            <SkeletonBlock className="enfermedades-loading__label" />
                            <SkeletonBlock className="enfermedades-loading__value" />
                          </div>
                        ))}
                      </div>
                    </section>
                  ))}
                </div>
              </DashboardPageSkeleton>
            ) : (
              <div className={failed ? 'enfermedades-page__error' : 'enfermedades-results-status'}>
                <p role={failed ? 'alert' : 'status'} aria-label="Estado de los resultados" aria-busy={false}>
                  {resultMessages[resultStatus]}
                </p>
                <button type="button" aria-label="Reintentar carga de resultados" onClick={results.retry}>
                  Reintentar
                </button>
              </div>
            )}
            {results.data?.disclaimer && <p className="enfermedades-disclaimer">{results.data.disclaimer}</p>}
            {resultStatus === 'ready' && (
              <div className="dashboard-pro-3col">
                <RiskCard id="polygenic_risk" title="Riesgo poligénico" empty="Sin resultados poligénicos.">
                  {polygenic.length > 0 && (
                    <dl className="legend-pro">
                      {polygenic.map((risk) => (
                        <div className="legend-pro__item" key={risk.condition}>
                          <dt className="legend-pro__label">{risk.label}</dt>
                          <dd className="legend-pro__value">
                            {risk.category} · percentil {Math.round(risk.percentile)}
                          </dd>
                        </div>
                      ))}
                    </dl>
                  )}
                </RiskCard>
                <RiskCard id="monogenic_risk" title="Variantes patogénicas (ClinVar)" empty="No se encontraron variantes patogénicas.">
                  {monogenic.length > 0 && (
                    <dl className="legend-pro">
                      {monogenic.map((variant) => (
                        <div className="legend-pro__item" key={variant.variant_id}>
                          <dt className="legend-pro__label">
                            {variant.gene || 'Gen no informado'} · {formatSignificance(variant.clinical_significance)}
                          </dt>
                          <dd className="legend-pro__value">
                            {variant.conditions?.length ? variant.conditions.join(', ') : 'Condición no informada'} · {variant.zygosity}
                          </dd>
                        </div>
                      ))}
                    </dl>
                  )}
                </RiskCard>
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
};

export default Enfermedades;
