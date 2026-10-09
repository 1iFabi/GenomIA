import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Menu, X, Zap } from 'lucide-react';
import { clearToken } from '../../config/api';
import { RESULT_NAV_ITEMS } from '../../config/resultNav';
import { moduleRows, useLatestGenomicsResults } from '../../hooks/useLatestGenomicsResults';
import { useSession } from '../../hooks/useSession';
import Sidebar from '../../components/Sidebar/Sidebar';
import { animatedSidebarIcons } from '../../components/Sidebar/animatedSidebarIcons';
import SectionHeader from '../../components/SectionHeader/SectionHeader';
import { DashboardPageSkeleton, SkeletonBlock } from '../../components/DashboardSkeleton/DashboardSkeleton';
import './Farmacogenetica.css';

const resultMessages = {
  loading: 'Cargando datos…',
  empty: 'Aún no tienes resultados disponibles.',
  missing: 'Tu último servicio no tiene resultados de farmacogenética.',
  permission: 'No tienes permiso para consultar estos resultados.',
  error: 'No fue posible cargar los datos. Puedes reintentar.',
  ready: 'Datos disponibles.',
};

const Farmacogenetica = () => {
  const { user } = useSession();
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [isMobile, setIsMobile] = useState(false);
  const navigate = useNavigate();
  const results = useLatestGenomicsResults();
  const genes = moduleRows(results, 'pharmacogenetics');
  const status = results.status === 'ready' && !genes.length ? 'missing' : results.status;
  const failed = ['permission', 'error'].includes(status);

  useEffect(() => {
    const checkMobile = () => {
      const mobile = window.innerWidth <= 1024;
      setIsMobile(mobile);
      if (!mobile) setIsMobileMenuOpen(false);
    };
    checkMobile();
    window.addEventListener('resize', checkMobile);
    return () => window.removeEventListener('resize', checkMobile);
  }, []);

  const handleLogout = async () => {
    await clearToken();
    navigate('/');
  };


  return (
    <div className="farmacogenetica-layout-new">
      {isMobile && (
        <button
          type="button"
          className="farmaco-burger"
          onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
          aria-label={isMobileMenuOpen ? 'Cerrar menú de navegación' : 'Abrir menú de navegación'}
          aria-expanded={isMobileMenuOpen}
          aria-controls="farmaco-navigation"
        >
          {isMobileMenuOpen ? <X size={24} color="white" aria-hidden="true" /> : <Menu size={24} color="white" aria-hidden="true" />}
        </button>
      )}
      <aside className="farmaco-sidebar-area" id="farmaco-navigation">
        <Sidebar
          iconOverrides={animatedSidebarIcons}
          items={RESULT_NAV_ITEMS}
          onLogout={handleLogout}
          user={user}
          isMobileMenuOpen={isMobileMenuOpen}
          setIsMobileMenuOpen={setIsMobileMenuOpen}
        />
      </aside>
      <main className="farmaco-main-content">
        <div className="farmaco-page-container">
          <SectionHeader title="Farmacogenética" subtitle="Consulta los valores del módulo de farmacogenética." icon={Zap} />
          <div className="farmaco-grid-wrapper">
            <div className="farmaco-list-section farmaco-demo-content">
              {status === 'loading' ? (
                <DashboardPageSkeleton className="farmaco-loading" label={resultMessages.loading}>
                  <section className="system-card-new farmaco-demo-panel">
                    <h2>Respuesta a medicamentos</h2>
                    <div className="farmaco-demo-values">
                      {[0, 1, 2, 3].map((index) => (
                        <div className="farmaco-loading__row" key={index}>
                          <span className="farmaco-loading__identity">
                            <SkeletonBlock className="farmaco-loading__gene" />
                            <SkeletonBlock className="farmaco-loading__diplotype" />
                          </span>
                          <span className="farmaco-loading__response">
                            <SkeletonBlock className="farmaco-loading__phenotype" />
                            <SkeletonBlock className="farmaco-loading__drugs" />
                          </span>
                        </div>
                      ))}
                    </div>
                  </section>
                </DashboardPageSkeleton>
              ) : (
                <div className="no-results-message">
                  <p role={failed ? 'alert' : 'status'} aria-label="Estado de los resultados" aria-busy={false}>
                    {resultMessages[status]}
                  </p>
                  <button type="button" className="filter-reset-btn" aria-label="Reintentar carga de resultados" onClick={results.retry}>
                    Reintentar
                  </button>
                </div>
              )}
              {results.data?.disclaimer && <p className="farmaco-disclaimer">{results.data.disclaimer}</p>}
              {status === 'ready' && (
                <section className="system-card-new farmaco-demo-panel" aria-labelledby="pharmacogenetics-title">
                  <h2 id="pharmacogenetics-title">Respuesta a medicamentos</h2>
                  <dl className="farmaco-demo-values">
                    {genes.map((gene) => (
                      <div key={gene.gene}>
                        <dt>{gene.gene} <span>{gene.diplotype}</span></dt>
                        <dd>
                          {gene.phenotype}
                          {gene.drugs?.length > 0 && <small> · {gene.drugs.join(', ')}</small>}
                        </dd>
                      </div>
                    ))}
                  </dl>
                </section>
              )}
            </div>
          </div>
        </div>
      </main>
    </div>
  );
};

export default Farmacogenetica;
