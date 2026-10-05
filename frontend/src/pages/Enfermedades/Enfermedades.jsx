import React, { useEffect, useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { Menu, X } from 'lucide-react';
import { API_ENDPOINTS, apiRequest, clearToken } from '../../config/api';
import { useLatestGenomicsResults } from '../../hooks/useLatestGenomicsResults';
import Sidebar from '../../components/Sidebar/Sidebar';
import '../../styles/cards.css';
import './Enfermedades.css';

const ENFERMEDADES_SUBTITLE =
  'Consulta los valores de los módulos poligénico y monogénico.';

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

const riskModules = [
  { module: 'polygenic_risk', kind: 'demo_index', title: 'Módulo poligénico' },
  { module: 'monogenic_risk', kind: 'demo_entries', title: 'Módulo monogénico' },
];
const knownModules = new Set([
  'global_ancestry', 'local_ancestry', 'polygenic_risk', 'monogenic_risk', 'traits', 'pharmacogenetics',
]);
const displayProvenance = {
  clinically_reviewed: false, display_only: true, numeric_semantics: 'arbitrary_demo_only_not_evaluated',
};
const isObject = (value) => value !== null && typeof value === 'object' && !Array.isArray(value);
const isText = (value) => typeof value === 'string' && value.trim().length > 0;
const isDemoLabel = (value) => typeof value === 'string' && /^Demo index [A-Z]+$/.test(value);
const hasDemoDisclosure = (value) => isObject(value)
  && value.synthetic === true && value.non_clinical === true && isText(value.disclaimer);

// Only raw, explicitly non-evaluated demo displays are renderable. A malformed
// bundle invalidates both targets; a missing target stays unavailable without fallback.
const readRiskDisplays = (data) => {
  const displays = { polygenic_risk: null, monogenic_risk: null, invalid: false };
  const invalid = () => ({ ...displays, polygenic_risk: null, monogenic_risk: null, invalid: true });
  if (!hasDemoDisclosure(data) || !Array.isArray(data.results)
    || !Object.entries(displayProvenance).every(([key, value]) => (
      data[key] === value
    ))) return invalid();
  const seen = new Set();
  for (const result of data.results) {
    if (!isObject(result) || !knownModules.has(result.module) || seen.has(result.module)) return invalid();
    seen.add(result.module);
    const definition = riskModules.find(({ module }) => module === result.module);
    if (!definition) continue;
    const payload = result.payload;
    if (result.result_type !== 'synthetic_placeholder' || result.value_code !== 'SYNTHETIC_NOT_EVALUATED'
      || !hasDemoDisclosure(payload) || payload.module !== result.module || payload.state !== 'not_evaluated'
      || !isDemoLabel(payload.label)
      || !Object.entries(displayProvenance).every(([key, value]) => payload[key] === value)
      || !isObject(payload.display) || payload.display.kind !== definition.kind
      || !Array.isArray(payload.display.items) || !payload.display.items.length) return invalid();
    const labels = new Set();
    for (const item of payload.display.items) {
      if (!isObject(item) || !isDemoLabel(item.label) || labels.has(item.label)
        || typeof item.display_value !== 'number' || !Number.isFinite(item.display_value)) return invalid();
      labels.add(item.label);
    }
    displays[result.module] = payload.display;
  }
  return displays;
};

// Localize display text only; validation and React keys keep the raw labels.
const formatRiskLabel = (label) => label.replace(/^Demo index ([A-Z]+)$/, 'Índice $1');

const resultMessages = {
  loading: 'Cargando datos…',
  noService: 'No hay un servicio disponible para mostrar resultados.',
  empty: 'El servicio seleccionado no tiene resultados.',
  missing: 'Faltan módulos en los resultados disponibles.',
  invalid: 'Los módulos no están disponibles: los datos no son válidos.',
  permission: 'No tienes permiso para consultar estos resultados.',
  error: 'No fue posible cargar los datos. Puedes reintentar.',
  ready: 'Datos disponibles.',
};

const getRiskResultStatus = (results, displays) => {
  if (results.loading) return 'loading';
  if (['ready', 'empty'].includes(results.status) && !results.service) return 'noService';
  if (displays?.invalid) return 'invalid';
  if (displays && !results.data.results.length) return 'empty';
  if (displays && riskModules.some(({ module }) => !displays[module])) return 'missing';
  return Object.hasOwn(resultMessages, results.status) ? results.status : 'error';
};

function DemoModuleCard({ definition, display }) {
  return (
    <section className="card-pro card-large-pro" aria-labelledby={`${definition.module}-title`}>
      <div className="card-pro__header">
        <h2 className="priority-section__title" id={`${definition.module}-title`}>{definition.title}</h2>
      </div>
      {display ? (
        <dl className="legend-pro">
          {display.items.map((item) => (
            <div className="legend-pro__item" key={item.label}>
              <dt className="legend-pro__label">{formatRiskLabel(item.label)}</dt>
              <dd className="legend-pro__value">{item.display_value}</dd>
            </div>
          ))}
        </dl>
      ) : <p>Módulo no disponible.</p>}
    </section>
  );
}

const Enfermedades = () => {
  const [user, setUser] = useState(null);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [isMobile, setIsMobile] = useState(false);
  const navigate = useNavigate();
  const results = useLatestGenomicsResults();
  const displays = results.status === 'ready' && results.service ? readRiskDisplays(results.data) : null;
  const resultStatus = getRiskResultStatus(results, displays);
  const failed = ['permission', 'error', 'invalid'].includes(resultStatus);

  useEffect(() => {
    fetchUser();
  }, []);

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

  const fetchUser = async () => {
    const response = await apiRequest(API_ENDPOINTS.ME, { method: 'GET' });
    if (response.ok && response.data)
      setUser(response.data.user || response.data);
  };

  const handleLogout = async () => {
    try {
      await apiRequest(API_ENDPOINTS.LOGOUT, { method: 'POST' });
    } catch {
          // Logout is best effort; clear the local session below.
        }
    clearToken();
    navigate('/');
  };

  const sidebarItems = useMemo(
    () => [
      { label: 'Ancestría', href: '/dashboard/ancestria' },
      { label: 'Rasgos', href: '/dashboard/rasgos' },
      { label: 'Farmacogenética', href: '/dashboard/farmacogenetica' },
      { label: 'Enfermedades', href: '/dashboard/enfermedades' }
    ],
    []
  );

  return (
    <div className="enfermedades-layout">
      {isMobile && (
        <button
          type="button"
          className="enfermedades-layout__burger"
          onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
          aria-label={isMobileMenuOpen ? 'Cerrar menú' : 'Abrir menú'}
          aria-expanded={isMobileMenuOpen}
        >
          {isMobileMenuOpen ? (
            <X size={24} strokeWidth={2.5} aria-hidden="true" />
          ) : (
            <Menu size={24} strokeWidth={2.5} aria-hidden="true" />
          )}
        </button>
      )}

      <aside className="enfermedades-layout__sidebar">
        <Sidebar
          items={sidebarItems}
          onLogout={handleLogout}
          user={user}
          isMobileMenuOpen={isMobileMenuOpen}
          setIsMobileMenuOpen={setIsMobileMenuOpen}
        />
      </aside>

      <main className="enfermedades-layout__main">
        <div className="enfermedades-page">
          <EnfermedadesPageHeader />
          <div className="enfermedades-page__content">
            <div className={failed ? 'enfermedades-page__error' : 'enfermedades-results-status'}>
              <p
                role={failed ? 'alert' : 'status'}
                aria-label="Estado de los resultados"
                aria-busy={resultStatus === 'loading'}
              >
                {resultMessages[resultStatus]}
              </p>
              {resultStatus !== 'loading' && (
                <button type="button" aria-label="Reintentar carga de resultados" onClick={results.retry}>
                  Reintentar
                </button>
              )}
            </div>
            {displays && !displays.invalid && ['ready', 'missing'].includes(resultStatus) && (
              <div className="dashboard-pro-3col">
                <DemoModuleCard definition={riskModules[0]} display={displays.polygenic_risk} />
                <DemoModuleCard definition={riskModules[1]} display={displays.monogenic_risk} />
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
};

export default Enfermedades;
