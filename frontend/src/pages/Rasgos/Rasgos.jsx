import React, { useEffect, useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { Menu, X } from 'lucide-react';
import { API_ENDPOINTS, apiRequest, clearToken } from '../../config/api';
import { useLatestGenomicsResults } from '../../hooks/useLatestGenomicsResults';
import { useSession } from '../../hooks/useSession';
import Sidebar from '../../components/Sidebar/Sidebar';
import '../../styles/cards.css';
import './Rasgos.css';

const knownModules = new Set([
  'global_ancestry', 'local_ancestry', 'polygenic_risk', 'monogenic_risk', 'traits', 'pharmacogenetics',
]);
const demoProvenance = {
  synthetic: true, non_clinical: true, clinically_reviewed: false, display_only: true,
  numeric_semantics: 'arbitrary_demo_only_not_evaluated',
};
const isObject = (value) => value !== null && typeof value === 'object' && !Array.isArray(value);
const isText = (value) => typeof value === 'string' && value.trim().length > 0;
const hasDemoProvenance = (value) => isObject(value) && isText(value.disclaimer)
  && Object.entries(demoProvenance).every(([key, expected]) => value[key] === expected);

// Never derive trait values from legacy fields or another module. Invalid bundles
// and v1 placeholders remain unavailable, rather than implying an absent trait.
const readTraitsDisplay = (data) => {
  const invalid = { status: 'invalid', display: null };
  if (!hasDemoProvenance(data) || !Array.isArray(data.results)) return invalid;
  const seen = new Set();
  let traits = null;
  for (const result of data.results) {
    if (!isObject(result) || !knownModules.has(result.module) || seen.has(result.module)) return invalid;
    seen.add(result.module);
    if (result.module === 'traits') traits = result;
  }
  if (!data.results.length) return { status: 'empty', display: null };
  if (!traits) return { status: 'missing', display: null };

  const payload = traits.payload;
  if (traits.result_type !== 'synthetic_placeholder' || traits.value_code !== 'SYNTHETIC_NOT_EVALUATED'
    || !hasDemoProvenance(payload) || payload.module !== 'traits' || payload.state !== 'not_evaluated'
    || !isText(payload.label) || !isObject(payload.display) || payload.display.kind !== 'demo_traits'
    || !Array.isArray(payload.display.items) || !payload.display.items.length) return invalid;
  const labels = new Set();
  for (const item of payload.display.items) {
    if (!isObject(item) || !isText(item.label) || labels.has(item.label)
      || typeof item.display_value !== 'number' || !Number.isFinite(item.display_value)) return invalid;
    labels.add(item.label);
  }
  return { status: 'ready', display: payload.display };
};

// Localize known categories and neutralize other display prefixes without mutating data.
const formatTraitLabel = (label) => label
  .replace(/^(\s*)Demo trait ([A-Z]+)(\s*)$/, '$1Rasgo $2$3')
  .replace(/^(\s*)Demo\s+/i, '$1');

const resultMessages = {
  loading: 'Cargando datos…',
  noService: 'No hay un servicio disponible para mostrar resultados.',
  empty: 'El servicio seleccionado no tiene resultados.',
  missing: 'El módulo de rasgos no está disponible en los resultados del servicio seleccionado.',
  invalid: 'El módulo de rasgos no está disponible: los datos no son válidos.',
  permission: 'No tienes permiso para consultar estos resultados.',
  error: 'No fue posible cargar los datos. Puedes reintentar.',
  ready: 'Datos disponibles.',
};
const getTraitsResult = (results) => {
  if (results.loading || results.status === 'loading') return { status: 'loading', display: null };
  if (results.status === 'permission') return { status: 'permission', display: null };
  if (!['ready', 'empty'].includes(results.status)) return { status: 'error', display: null };
  if (!results.service) return { status: 'noService', display: null };
  if (results.status === 'empty') return { status: 'empty', display: null };
  return readTraitsDisplay(results.data);
};

const Rasgos = () => {
  const { user } = useSession();
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [isMobile, setIsMobile] = useState(typeof window !== 'undefined' ? window.innerWidth <= 1024 : false);
  const navigate = useNavigate();
  const results = useLatestGenomicsResults();
  const { status, display } = getTraitsResult(results);
  const failed = ['permission', 'error', 'invalid'].includes(status);

  useEffect(() => {
    const checkMobile = () => {
      const mobile = window.innerWidth <= 1024;
      setIsMobile(mobile);
      if (mobile) setIsMobileMenuOpen(false);
    };
    checkMobile();
    window.addEventListener('resize', checkMobile);
    return () => window.removeEventListener('resize', checkMobile);
  }, []);

  const handleLogout = async () => {
    try {
      await apiRequest(API_ENDPOINTS.LOGOUT, { method: 'POST' });
    } catch {
      /* logout best-effort; local token cleared below */
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
    <div className="rasgos-layout">
      {isMobile && (
        <button
          type="button"
          className="rasgos-layout__burger"
          onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
          aria-label={isMobileMenuOpen ? 'Cerrar menú de navegación' : 'Abrir menú de navegación'}
          aria-expanded={isMobileMenuOpen}
        >
          {isMobileMenuOpen ? <X size={24} aria-hidden="true" /> : <Menu size={24} aria-hidden="true" />}
        </button>
      )}
      <aside className="rasgos-layout__sidebar">
        <Sidebar
          items={sidebarItems}
          onLogout={handleLogout}
          user={user}
          isMobileMenuOpen={isMobileMenuOpen}
          setIsMobileMenuOpen={setIsMobileMenuOpen}
        />
      </aside>
      <main className="rasgos-layout__main">
        <div className="rasgos-page">
          <header className="rasgos-header">
            <span className="rasgos-header__kicker">Resultados</span>
            <h1 className="rasgos-header__title">Rasgos</h1>
            <p className="rasgos-header__subtitle">
              Consulta los valores del módulo de rasgos.
            </p>
          </header>
          <div className={failed ? 'rasgos-page__error' : status === 'loading' ? 'rasgos-page__loading' : 'rasgos-report__intro'}>
            <p
              role={failed ? 'alert' : 'status'}
              aria-label="Estado de los resultados"
              aria-busy={status === 'loading'}
            >
              {resultMessages[status]}
            </p>
            {status !== 'loading' && (
              <button type="button" className="rasgos-back" aria-label="Reintentar carga de resultados" onClick={results.retry}>
                Reintentar
              </button>
            )}
          </div>
          {display && (
            <section className="rasgos-trait-detail" aria-labelledby="traits-title">
              <header className="rasgos-trait-detail__header">
                <h2 className="rasgos-trait-detail__title" id="traits-title">Módulo de rasgos</h2>
              </header>
              <dl className="rasgos-field-grid">
                {display.items.map((item) => (
                  <div className="rasgos-field" key={item.label}>
                    <dt className="rasgos-trait-row__title">{formatTraitLabel(item.label)}</dt>
                    <dd className="rasgos-field__value">{item.display_value}</dd>
                  </div>
                ))}
              </dl>
            </section>
          )}
        </div>
      </main>
    </div>
  );
};

export default Rasgos;
