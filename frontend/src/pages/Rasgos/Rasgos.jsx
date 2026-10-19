import React, { useEffect, useMemo, useRef, useState } from 'react';
import { AnimatePresence, motion as Motion, useReducedMotion } from 'motion/react';
import { useNavigate } from 'react-router-dom';
import { ChevronRight } from 'lucide-react';
import { PieChart } from '../../components/charts/pie-chart';
import { PieSlice } from '../../components/charts/pie-slice';
import { PieCenter } from '../../components/charts/pie-center';
import { clearToken } from '../../config/api';
import { moduleRows, useLatestGenomicsResults } from '../../hooks/useLatestGenomicsResults';
import { useSession } from '../../hooks/useSession';
import ResultsBar from '../../components/ResultsBar/ResultsBar';
import RasgosDetail from './RasgosDetail';
import { RasgosHeader, RasgosLoadingContent } from './RasgosLoading';
import '../../styles/cards.css';
import './Rasgos.css';

const resultMessages = {
  empty: 'Aún no tienes resultados disponibles.',
  missing: 'Tu último servicio no tiene resultados de rasgos.',
  permission: 'No tienes permiso para consultar estos resultados.',
  error: 'No fue posible cargar los datos. Puedes reintentar.',
};

const CATEGORY_ORDER = [
  'Metabolismo', 'Rendimiento Físico y Sensorial', 'Cognición', 'Bienestar y Salud', 'Apariencia Física',
];
// Rasgos' sky (config/resultNav.js): one cool family, kept apart by value and by each slice's pattern.
const CATEGORY_COLORS = {
  Metabolismo: '#1e3a5f',
  'Rendimiento Físico y Sensorial': '#2f7fd0',
  Cognición: '#d9922e',
  'Bienestar y Salud': '#23967f',
  'Apariencia Física': '#cf5f5a',
};
const CATEGORY_DESCRIPTIONS = {
  Metabolismo: 'Rasgos asociados a cómo tu cuerpo transforma alimentos y sustancias.',
  'Rendimiento Físico y Sensorial': 'Rasgos vinculados al desempeño físico y a cómo percibes los estímulos.',
  Cognición: 'Rasgos ligados a procesos mentales como la atención, la memoria y el manejo del estrés.',
  'Bienestar y Salud': 'Rasgos relacionados con tu equilibrio físico y tus ritmos diarios.',
  'Apariencia Física': 'Rasgos asociados a características externas como el cabello o los ojos.',
};
const PATTERN_WHITE = { fill: 'none', stroke: '#ffffff', strokeWidth: 1.5 };
const CATEGORY_PATTERNS = {
  Metabolismo: { id: 'rasgos-pattern-dots', size: 16, shape: (
    <><circle cx="4" cy="4" r="1.8" fill="#ffffff" fillOpacity="0.25" /><circle cx="12" cy="12" r="1.8" fill="#ffffff" fillOpacity="0.25" /></>
  ) },
  'Rendimiento Físico y Sensorial': { id: 'rasgos-pattern-rings', size: 18, shape: (
    <><circle cx="9" cy="9" r="4" {...PATTERN_WHITE} strokeOpacity="0.27" /><circle cx="0" cy="0" r="4" {...PATTERN_WHITE} strokeOpacity="0.2" /></>
  ) },
  Cognición: { id: 'rasgos-pattern-cross', size: 16, shape: <path d="M8 2v12M2 8h12" {...PATTERN_WHITE} strokeOpacity="0.24" /> },
  'Bienestar y Salud': { id: 'rasgos-pattern-diagonal', size: 14, shape: (
    <path d="M-3 3 3-3M0 14 14 0M11 17 17 11" {...PATTERN_WHITE} strokeOpacity="0.2" strokeWidth="2" />
  ) },
  'Apariencia Física': { id: 'rasgos-pattern-diamond', size: 18, shape: (
    <path d="m9 3 6 6-6 6-6-6 6-6Z" {...PATTERN_WHITE} strokeOpacity="0.22" />
  ) },
};
const OTHER_COLOR = '#94a9c0';

// PieChart moves children whose name contains "Pattern" into its <defs>.
function CategoryPattern({ id, size, color, children }) {
  return (
    <pattern id={id} width={size} height={size} patternUnits="userSpaceOnUse">
      <rect width={size} height={size} fill={color} />
      {children}
    </pattern>
  );
}
CategoryPattern.displayName = 'CategoryPattern';

// Opening a category goes one level in: the overview steps back (a touch smaller, fading) while the
// category rises into the same place, both at once; going back retraces the same path. No gap,
// no bounce, and a tap mid-way just retargets from where things are.
const LEVEL = {
  overview: { scale: 0.97, y: -8 },
  detail: { y: 20 },
};
const levelMotion = (level, reduce) => ({
  initial: { opacity: 0, ...(reduce ? {} : LEVEL[level]) },
  animate: { opacity: 1, y: 0, scale: 1, transition: { type: 'spring', bounce: 0, duration: 0.45 } },
  exit: {
    opacity: 0,
    ...(reduce ? {} : LEVEL[level]),
    pointerEvents: 'none',
    // the old words clear quickly so the two never read on top of each other
    transition: { default: { type: 'spring', bounce: 0, duration: 0.3 }, opacity: { duration: 0.12, ease: 'easeOut' } },
  },
});

const OTHER_CATEGORY = 'Otros rasgos';
const traitCount = (count) => `${count} ${count === 1 ? 'rasgo' : 'rasgos'}`;

const groupByCategory = (traits) => {
  const groups = new Map();
  for (const trait of traits) {
    const name = trait.category || OTHER_CATEGORY;
    groups.set(name, [...(groups.get(name) || []), trait]);
  }
  const rank = (name) => (CATEGORY_ORDER.includes(name) ? CATEGORY_ORDER.indexOf(name) : CATEGORY_ORDER.length);
  return [...groups].map(([name, items]) => ({ name, traits: items })).sort((a, b) => rank(a.name) - rank(b.name));
};

const Rasgos = () => {
  const { user } = useSession();
  const navigate = useNavigate();
  const results = useLatestGenomicsResults();
  const traits = moduleRows(results, 'traits');
  const status = results.status === 'ready' && !traits.length ? 'missing' : results.status;
  const failed = ['permission', 'error'].includes(status);
  const groups = useMemo(() => groupByCategory(traits), [traits]);
  const [categoryName, setCategoryName] = useState(null);
  const category = groups.find((group) => group.name === categoryName);
  const reduce = useReducedMotion();
  // The first overview after loading only fades in over the skeleton, which already holds its place.
  const fromLoading = useRef(status === 'loading');
  useEffect(() => {
    if (status === 'loading') fromLoading.current = true;
    else if (status === 'ready') fromLoading.current = false;
  }, [status]);

  // A new category starts at its top: if the reader had scrolled down, bring the page back up to it.
  useEffect(() => {
    if (window.scrollY > 0) window.scrollTo({ top: 0, behavior: reduce ? 'auto' : 'smooth' });
  }, [categoryName, reduce]);

  const handleLogout = async () => {
    await clearToken();
    navigate('/');
  };


  return (
    <div className="rasgos-layout">
      <main className="rasgos-layout__main">
        <ResultsBar user={user} onLogout={handleLogout} />
        <div className="rasgos-page">
          <RasgosHeader />
          {!['loading', 'ready'].includes(status) && (
            <div className={failed ? 'rasgos-page__error' : 'rasgos-report__intro'}>
              <p role={failed ? 'alert' : 'status'} aria-label="Estado de los resultados" aria-busy={false}>
                {resultMessages[status]}
              </p>
              <button type="button" className="rasgos-back" aria-label="Reintentar carga de resultados" onClick={results.retry}>
                Reintentar
              </button>
            </div>
          )}
          <div className="rasgos-stage">
          <AnimatePresence initial={false}>
          {status === 'loading' && (
            <Motion.div key="loading" exit={{ opacity: 0, transition: { duration: 0.35, ease: 'easeOut' } }}>
              <RasgosLoadingContent />
            </Motion.div>
          )}
          {status === 'ready' && !category && (
            <Motion.section
              key="overview"
              {...levelMotion('overview', reduce)}
              {...(fromLoading.current && { initial: { opacity: 0 } })}
              style={{ transformOrigin: '50% 0' }} className="rasgos-overview" aria-labelledby="rasgos-overview-title">
              <div className="rasgos-overview__intro">
                <span id="rasgos-overview-title" className="rasgos-report__eyebrow">Explorar resultados</span>
                <span className="rasgos-report__hint">Selecciona una categoría</span>
              </div>
              <div className="rasgos-overview__body">
              <div
                className="rasgos-overview__chart"
                role="group"
                aria-label={`Distribución de rasgos por categoría. Total: ${traitCount(traits.length)}.`}
              >
                <PieChart
                  data={groups.map((group) => ({
                    label: group.name,
                    value: group.traits.length,
                    color: CATEGORY_COLORS[group.name] || OTHER_COLOR,
                    fill: CATEGORY_PATTERNS[group.name] ? `url(#${CATEGORY_PATTERNS[group.name].id})` : undefined,
                  }))}
                  innerRadius={78}
                  padAngle={0.025}
                  cornerRadius={3}
                  hoverOffset={8}
                  className="rasgos-overview__pie"
                >
                  {groups.filter((group) => CATEGORY_PATTERNS[group.name]).map((group) => {
                    const pattern = CATEGORY_PATTERNS[group.name];
                    return (
                      <CategoryPattern key={pattern.id} id={pattern.id} size={pattern.size} color={CATEGORY_COLORS[group.name]}>
                        {pattern.shape}
                      </CategoryPattern>
                    );
                  })}
                  {groups.map((group, index) => (
                    <PieSlice
                      key={group.name}
                      index={index}
                      ariaLabel={`Abrir categoría ${group.name}, ${traitCount(group.traits.length)}`}
                      onClick={() => setCategoryName(group.name)}
                    />
                  ))}
                  <PieCenter defaultLabel="rasgos" valueClassName="rasgos-overview__center-value" labelClassName="rasgos-overview__center-label">
                    {({ value, label, isHovered }) => (
                      <span className="rasgos-overview__center-content">
                        <strong>{value}</strong>
                        <span>{isHovered ? label : 'rasgos'}</span>
                      </span>
                    )}
                  </PieCenter>
                </PieChart>
              </div>
              <div className="rasgos-overview__legend" aria-label="Categorías de rasgos">
                {groups.map((group) => (
                  <button
                    key={group.name}
                    type="button"
                    className="rasgos-overview__legend-item"
                    onClick={() => setCategoryName(group.name)}
                    aria-label={`Abrir categoría ${group.name}, ${traitCount(group.traits.length)}`}
                  >
                    <span className="rasgos-overview__legend-marker" style={{ backgroundColor: CATEGORY_COLORS[group.name] || OTHER_COLOR }} aria-hidden="true" />
                    <span className="rasgos-overview__legend-copy">
                      <span className="rasgos-overview__legend-name">{group.name}</span>
                      <span className="rasgos-overview__legend-count">{traitCount(group.traits.length)}</span>
                    </span>
                    <ChevronRight size={16} aria-hidden="true" />
                  </button>
                ))}
              </div>
              </div>
            </Motion.section>
          )}
          {status === 'ready' && category && (
            <Motion.div key="detail" {...levelMotion('detail', reduce)}>
            <RasgosDetail
              groups={groups}
              category={category}
              colors={(name) => CATEGORY_COLORS[name] || OTHER_COLOR}
              descriptions={CATEGORY_DESCRIPTIONS}
              onSelect={setCategoryName}
              onBack={() => setCategoryName(null)}
            />
            </Motion.div>
          )}
          </AnimatePresence>
          </div>
        </div>
      </main>
    </div>
  );
};

export default Rasgos;
