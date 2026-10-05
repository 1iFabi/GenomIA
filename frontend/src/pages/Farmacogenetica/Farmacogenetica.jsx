import React, { useEffect, useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { Menu, X, Zap } from 'lucide-react';
import { API_ENDPOINTS, apiRequest, clearToken } from '../../config/api';
import { useLatestGenomicsResults } from '../../hooks/useLatestGenomicsResults';
import { useSession } from '../../hooks/useSession';
import Sidebar from '../../components/Sidebar/Sidebar';
import SectionHeader from '../../components/SectionHeader/SectionHeader';
import './Farmacogenetica.css';

const knownModules = new Set([
  'global_ancestry', 'local_ancestry', 'polygenic_risk', 'monogenic_risk', 'traits', 'pharmacogenetics',
]);
const demoProvenance = {
  synthetic: true, non_clinical: true, clinically_reviewed: false, display_only: true,
  numeric_semantics: 'arbitrary_demo_only_not_evaluated',
};
const isObject = (value) => value !== null && typeof value === 'object' && !Array.isArray(value);
const isText = (value) => typeof value === 'string' && value.trim().length > 0;

// Read only the explicit demo display. Invalid bundles and v1 placeholders
// stay unavailable; legacy fields and other modules never supply a value.
const readPharmacogeneticsDisplay = (data) => {
  const invalid = { status: 'invalid', display: null };
  if (!isObject(data) || !Array.isArray(data.results)
    || !Object.entries(demoProvenance).every(([key, expected]) => data[key] === expected)) return invalid;
  const seen = new Set();
  let pharmacogenetics = null;
  for (const result of data.results) {
    if (!isObject(result) || !knownModules.has(result.module) || seen.has(result.module)) return invalid;
    seen.add(result.module);
    if (result.module === 'pharmacogenetics') pharmacogenetics = result;
  }
  if (!data.results.length) return { status: 'empty', display: null };
  if (!pharmacogenetics) return { status: 'missing', display: null };

  const payload = pharmacogenetics.payload;
  if (!isObject(payload) || payload.state !== 'not_evaluated' || !isObject(payload.display)
    || payload.display.kind !== 'demo_interactions' || !Array.isArray(payload.display.items)
    || !payload.display.items.length) return invalid;
  const labels = new Set();
  for (const item of payload.display.items) {
    if (!isObject(item) || !isText(item.label) || labels.has(item.label)
      || typeof item.display_value !== 'number' || !Number.isFinite(item.display_value)) return invalid;
    labels.add(item.label);
  }
  return { status: 'ready', display: payload.display };
};

// Localize known categories and neutralize other display prefixes without mutating data.
const formatInteractionLabel = (label) => label
  .replace(/^(\s*)Demo interaction ([A-Z]+)(\s*)$/, '$1Interacción $2$3')
  .replace(/^(\s*)Demo\s+/i, '$1');

const resultMessages = {
  loading: 'Cargando datos…',
  noService: 'No hay un servicio disponible para mostrar resultados.',
  empty: 'El servicio seleccionado no tiene resultados.',
  missing: 'El módulo de farmacogenética no está disponible en los resultados del servicio seleccionado.',
  invalid: 'El módulo de farmacogenética no está disponible: los datos no son válidos.',
  permission: 'No tienes permiso para consultar estos resultados.',
  error: 'No fue posible cargar los datos. Puedes reintentar.',
  ready: 'Datos disponibles.',
};
const getPharmacogeneticsResult = (results) => {
  if (results.loading || results.status === 'loading') return { status: 'loading', display: null };
  if (results.status === 'permission') return { status: 'permission', display: null };
  if (!['ready', 'empty'].includes(results.status)) return { status: 'error', display: null };
  if (!results.service) return { status: 'noService', display: null };
  if (results.status === 'empty') return { status: 'empty', display: null };
  return readPharmacogeneticsDisplay(results.data);
};

const Farmacogenetica = () => {
  const { user } = useSession();
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [isMobile, setIsMobile] = useState(false);
  const navigate = useNavigate();
  const results = useLatestGenomicsResults();
  const { status, display } = getPharmacogeneticsResult(results);
  const failed = ['permission', 'error', 'invalid'].includes(status);

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
    try {
      await apiRequest(API_ENDPOINTS.LOGOUT, { method: 'POST' });
    } catch {
      // Logout is best effort; clear the local session below.
    }
    clearToken();
    navigate('/');
  };

  const sidebarItems = useMemo(() => [
    { label: 'Ancestría', href: '/dashboard/ancestria' },
    { label: 'Rasgos', href: '/dashboard/rasgos' },
    { label: 'Farmacogenética', href: '/dashboard/farmacogenetica' },
    { label: 'Enfermedades', href: '/dashboard/enfermedades' },
  ], []);

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
          items={sidebarItems}
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
              <div className="no-results-message">
                <p
                  role={failed ? 'alert' : 'status'}
                  aria-label="Estado de los resultados"
                  aria-busy={status === 'loading'}
                >
                  {resultMessages[status]}
                </p>
                {status !== 'loading' && (
                  <button type="button" className="filter-reset-btn" aria-label="Reintentar carga de resultados" onClick={results.retry}>
                    Reintentar
                  </button>
                )}
              </div>
              {display && (
                <section className="system-card-new farmaco-demo-panel" aria-labelledby="pharmacogenetics-demo-title">
                  <h2 id="pharmacogenetics-demo-title">Módulo de farmacogenética</h2>
                  <dl className="farmaco-demo-values">
                    {display.items.map((item) => (
                      <div key={item.label}>
                        <dt>{formatInteractionLabel(item.label)}</dt>
                        <dd>{item.display_value}</dd>
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
