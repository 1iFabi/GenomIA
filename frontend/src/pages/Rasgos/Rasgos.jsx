import React, { useEffect, useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { Menu, X, ChevronRight } from 'lucide-react';
import { PieChart } from '../../components/charts/pie-chart';
import { PieSlice } from '../../components/charts/pie-slice';
import { PieCenter } from '../../components/charts/pie-center';
import { API_ENDPOINTS, apiRequest, clearToken } from '../../config/api';
import Sidebar from '../../components/Sidebar/Sidebar';
import NalaTipButton from '../../components/Nala/NalaTipButton';
import GlossaryCarousel from '../../components/GlossaryCarousel/GlossaryCarousel';
import '../../styles/cards.css';
import './Rasgos.css';

const glossaryData = [
  { term: 'RSID', description: 'Código único (ej: rs1234567) que identifica una variante específica en bases de datos científicas.' },
  { term: 'Magnitud', description: 'Escala (0-5) que mide la importancia clínica de una variante. Mayor valor = mayor impacto.' },
  { term: 'Alelo', description: 'Cada variante posible de un gen. Heredas una de cada progenitor.' },
  { term: 'Fenotipo', description: 'Características observables (p.ej., color de ojos). Surge de genes + ambiente.' },
  { term: 'Genotipo', description: 'Tu composición genética heredada de ambos progenitores.' },
  { term: 'Gen', description: 'Segmento de ADN con instrucciones para una proteína.' },
];

const groupDescriptions = {
  'Metabolismo': 'Rasgos asociados a las reacciones químicas del cuerpo para convertir alimentos en energía.',
  'Rendimiento Físico y Sensorial': 'Rasgos vinculados al desempeño físico y a cómo percibes y procesas estímulos.',
  'Cognición': 'Rasgos ligados a procesos mentales como pensamiento, aprendizaje, memoria y atención.',
  'Bienestar y Salud': 'Rasgos relacionados con el equilibrio físico, mental y social.',
  'Apariencia Física': 'Rasgos asociados a características externas como piel, cabello u ojos.',
};

const DISCLAIMER = 'La predisposición indica una tendencia genética, no es un diagnóstico ni una certeza. El estilo de vida y el ambiente también influyen.';
const CATEGORY_COLORS = {
  'Metabolismo': '#00a896',
  'Rendimiento Físico y Sensorial': '#f15a24',
  'Cognición': '#6c5ce7',
  'Bienestar y Salud': '#e9b949',
  'Apariencia Física': '#e8488a',
};
const CATEGORY_ORDER = [
  'Metabolismo',
  'Rendimiento Físico y Sensorial',
  'Cognición',
  'Bienestar y Salud',
  'Apariencia Física',
];
const CATEGORY_PATTERN_IDS = {
  'Metabolismo': 'rasgos-pattern-dots',
  'Rendimiento Físico y Sensorial': 'rasgos-pattern-rings',
  'Cognición': 'rasgos-pattern-cross',
  'Bienestar y Salud': 'rasgos-pattern-diagonal',
  'Apariencia Física': 'rasgos-pattern-diamond',
};

function DotsPattern({ id, color }) {
  return (
    <pattern id={id} width="16" height="16" patternUnits="userSpaceOnUse">
      <rect width="16" height="16" fill={color} />
      <circle cx="4" cy="4" r="1.8" fill="#ffffff" fillOpacity="0.25" />
      <circle cx="12" cy="12" r="1.8" fill="#ffffff" fillOpacity="0.25" />
    </pattern>
  );
}
DotsPattern.displayName = 'DotsPattern';

function RingsPattern({ id, color }) {
  return (
    <pattern id={id} width="18" height="18" patternUnits="userSpaceOnUse">
      <rect width="18" height="18" fill={color} />
      <circle cx="9" cy="9" r="4" fill="none" stroke="#ffffff" strokeOpacity="0.27" strokeWidth="1.5" />
      <circle cx="0" cy="0" r="4" fill="none" stroke="#ffffff" strokeOpacity="0.2" strokeWidth="1.5" />
    </pattern>
  );
}
RingsPattern.displayName = 'RingsPattern';

function CrossPattern({ id, color }) {
  return (
    <pattern id={id} width="16" height="16" patternUnits="userSpaceOnUse">
      <rect width="16" height="16" fill={color} />
      <path d="M8 2v12M2 8h12" fill="none" stroke="#ffffff" strokeOpacity="0.24" strokeWidth="1.5" />
    </pattern>
  );
}
CrossPattern.displayName = 'CrossPattern';

function DiagonalPattern({ id, color }) {
  return (
    <pattern id={id} width="14" height="14" patternUnits="userSpaceOnUse">
      <rect width="14" height="14" fill={color} />
      <path d="M-3 3 3-3M0 14 14 0M11 17 17 11" fill="none" stroke="#ffffff" strokeOpacity="0.2" strokeWidth="2" />
    </pattern>
  );
}
DiagonalPattern.displayName = 'DiagonalPattern';

function DiamondPattern({ id, color }) {
  return (
    <pattern id={id} width="18" height="18" patternUnits="userSpaceOnUse">
      <rect width="18" height="18" fill={color} />
      <path d="m9 3 6 6-6 6-6-6 6-6Z" fill="none" stroke="#ffffff" strokeOpacity="0.22" strokeWidth="1.5" />
    </pattern>
  );
}
DiamondPattern.displayName = 'DiamondPattern';

/* ------------------------------------------------------------------ */
/* Level system (no numeric percentages)                               */
/* ------------------------------------------------------------------ */
const LEVEL_META = {
  Bajo:      { key: 'Bajo',      label: 'Por debajo del promedio', color: '#15803d', description: 'Una tendencia menor que el promedio de referencia para este rasgo.', segments: 1 },
  Neutral:   { key: 'Neutral',   label: 'En el promedio', color: '#1d4ed8', description: 'Un resultado cercano al promedio de referencia para este rasgo.', segments: 1 },
  Intermedio:{ key: 'Intermedio',label: 'Por encima del promedio', color: '#d97706', description: 'Una tendencia mayor que el promedio de referencia para este rasgo.', segments: 2 },
  Alto:      { key: 'Alto',      label: 'Muy por encima del promedio', color: '#b91c1c', description: 'Una tendencia marcadamente mayor que el promedio de referencia.', segments: 3 },
};
const LEVEL_SEVERITY = ['Neutral', 'Bajo', 'Intermedio', 'Alto'];
const LEVEL_SUMMARY_ORDER = ['Bajo', 'Neutral', 'Intermedio', 'Alto'];

function getLevelMeta(nivelRiesgo, magnitude) {
  const n = String(nivelRiesgo || '').trim().toLowerCase();
  if (n.includes('alto') || n.includes('elev')) return LEVEL_META.Alto;
  if (n.includes('intermedio') || n.includes('medio')) return LEVEL_META.Intermedio;
  if (n.includes('bajo')) return LEVEL_META.Bajo;
  if (n.includes('neutral')) return LEVEL_META.Neutral;
  const m = Number.parseFloat(magnitude);
  if (Number.isFinite(m) && m >= 2) return LEVEL_META.Alto;
  if (Number.isFinite(m) && m >= 1) return LEVEL_META.Intermedio;
  return LEVEL_META.Bajo;
}

function getLevelCounts(traitList) {
  return traitList.reduce((counts, trait) => {
    const meta = getLevelMeta(trait.nivel_riesgo, trait.magnitud_efecto ?? trait.magnitude ?? trait.effect_size);
    counts[meta.key] = (counts[meta.key] || 0) + 1;
    return counts;
  }, {});
}

const tint = (hex, alpha) => `${hex}${alpha}`;

/* ------------------------------------------------------------------ */
/* Breadcrumb                                                          */
/* ------------------------------------------------------------------ */
function Breadcrumb({ crumbs }) {
  return (
    <nav className="rasgos-breadcrumb" aria-label="Ruta de navegación">
      {crumbs.map((crumb, i) => {
        const isLast = i === crumbs.length - 1;
        return (
          <React.Fragment key={i}>
            {isLast || !crumb.onClick ? (
              <span className={`rasgos-breadcrumb__crumb ${isLast ? 'rasgos-breadcrumb__crumb--current' : ''}`}>
                {crumb.label}
              </span>
            ) : (
              <button type="button" className="rasgos-breadcrumb__crumb" onClick={crumb.onClick}>
                {crumb.label}
              </button>
            )}
            {!isLast && <ChevronRight className="rasgos-breadcrumb__sep" size={14} aria-hidden="true" />}
          </React.Fragment>
        );
      })}
    </nav>
  );
}

/* ------------------------------------------------------------------ */
/* Overview                                                            */
/* ------------------------------------------------------------------ */
function Overview({ groupedData, onOpenCategory }) {
  const totalCategories = groupedData.length;
  const totalTraits = groupedData.reduce((acc, group) => acc + group.traits.length, 0);
  const categoryGroups = CATEGORY_ORDER
    .map((name) => groupedData.find((group) => group.name === name))
    .filter(Boolean);
  const chartData = categoryGroups.map((group) => ({
    label: group.name,
    value: group.traits.length,
    color: CATEGORY_COLORS[group.name],
    fill: `url(#${CATEGORY_PATTERN_IDS[group.name]})`,
  }));
  const chartTotal = chartData.reduce((total, item) => total + item.value, 0);

  return (
    <div className="rasgos-view">
      <header className="rasgos-header">
        <div className="rasgos-header__text">
          <span className="rasgos-header__kicker">Perfil genético</span>
          <h1 className="rasgos-header__title">
            Rasgos <span className="rasgos-header__accent">genéticos</span>
          </h1>
          <p className="rasgos-header__subtitle">
            Tus resultados están agrupados en {totalCategories} categorías, con {totalTraits} rasgos en total.
            Elige una categoría para ver qué indica cada rasgo.
          </p>
        </div>
      </header>

      <section className="rasgos-overview" aria-labelledby="rasgos-overview-title">
        <div className="rasgos-overview__intro">
          <div>
            <span className="rasgos-report__eyebrow">Explorar resultados</span>
            <h2 id="rasgos-overview-title" className="rasgos-report__heading"></h2>
          </div>
          <span className="rasgos-report__hint">Selecciona una categoría</span>
        </div>

        <div className="rasgos-overview__body">
          <div
            className="rasgos-overview__chart"
            role="img"
            aria-label={`Distribución de rasgos por categoría. Total: ${chartTotal} rasgos.`}
          >
            <PieChart
              data={chartData}
              innerRadius={78}
              padAngle={0.025}
              cornerRadius={3}
              hoverOffset={8}
              className="rasgos-overview__pie"
            >
              <DotsPattern id={CATEGORY_PATTERN_IDS.Metabolismo} color={CATEGORY_COLORS.Metabolismo} />
              <RingsPattern id={CATEGORY_PATTERN_IDS['Rendimiento Físico y Sensorial']} color={CATEGORY_COLORS['Rendimiento Físico y Sensorial']} />
              <CrossPattern id={CATEGORY_PATTERN_IDS.Cognición} color={CATEGORY_COLORS.Cognición} />
              <DiagonalPattern id={CATEGORY_PATTERN_IDS['Bienestar y Salud']} color={CATEGORY_COLORS['Bienestar y Salud']} />
              <DiamondPattern id={CATEGORY_PATTERN_IDS['Apariencia Física']} color={CATEGORY_COLORS['Apariencia Física']} />
              {chartData.map((item, index) => (
                <PieSlice
                  key={item.label}
                  index={index}
                  ariaLabel={`Abrir categoría ${item.label}, ${item.value} rasgos`}
                  onClick={() => onOpenCategory(categoryGroups[index])}
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
            {categoryGroups.map((group) => (
              <button
                key={group.name}
                type="button"
                className="rasgos-overview__legend-item"
                onClick={() => onOpenCategory(group)}
                aria-label={`Abrir categoría ${group.name}, ${group.traits.length} rasgos`}
              >
                <span className="rasgos-overview__legend-marker" style={{ backgroundColor: CATEGORY_COLORS[group.name] }} aria-hidden="true" />
                <span className="rasgos-overview__legend-copy">
                  <span className="rasgos-overview__legend-name">{group.name}</span>
                  <span className="rasgos-overview__legend-count">{group.traits.length} rasgos</span>
                </span>
                <ChevronRight size={16} aria-hidden="true" />
              </button>
            ))}
          </div>
        </div>
      </section>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Category detail                                                     */
/* ------------------------------------------------------------------ */
function CategoryDetail({ group, onBack, onOpenTrait }) {
  if (!group) return null;

      const levelData = LEVEL_SUMMARY_ORDER.map((key) => LEVEL_META[key]);

      return (
    <div className="rasgos-view">
      <Breadcrumb
        crumbs={[
          { label: 'Rasgos', onClick: onBack },
          { label: group.name },
        ]}
      />

      <header className="rasgos-cat-header" style={{ '--cat-color': group.levelMeta.color }}>
        <div className="rasgos-cat-header__info">
          <span className="rasgos-cat-header__eyebrow">Índice de categoría</span>
            <h2 id="rasgos-category-title" className="rasgos-cat-header__title">{group.name}</h2>
          <p className="rasgos-cat-header__desc">
            {groupDescriptions[group.name] || 'Rasgos asociados a esta categoría.'}
          </p>
        </div>
        <div className="rasgos-cat-header__metric">
                    <span className="rasgos-cat-header__count">{group.traits.length} rasgos</span>
        </div>
      </header>

      <section className="rasgos-category-guide" aria-label="Guía de lectura">
        <div className="rasgos-category-guide__intro">
          <span className="rasgos-category-guide__eyebrow">Guía de lectura</span>
        </div>
        <ul className="rasgos-category-guide__legend" aria-label="Significado de los estados de los rasgos">
          {levelData.map((item) => (
            <li key={item.key} className="rasgos-category-guide__legend-item">
              <span className="rasgos-category-guide__legend-marker" style={{ backgroundColor: item.color }} aria-hidden="true" />
              <span className="rasgos-category-guide__legend-label">{item.label}</span>
            </li>
          ))}
        </ul>
      </section>
           <span> </span>
          <div className="rasgos-trait-list" aria-labelledby="rasgos-category-title">
          <div className="rasgos-trait-list__header">

            <span></span>
            <span>Selecciona un rasgo para ver su detalle</span>
          </div>
        {group.traits.map((trait, index) => {
          const meta = getLevelMeta(trait.nivel_riesgo, trait.magnitud_efecto ?? trait.magnitude ?? trait.effect_size);
          return (
            <button
              key={index}
              type="button"
              className="rasgos-trait-row"
              aria-label={`${trait.name || trait.fenotipo}. ${meta.label}`}
              onClick={() => onOpenTrait(trait)}
            >
              <span className="rasgos-trait-row__bar" style={{ backgroundColor: meta.color }} aria-hidden="true" />
              <span className="rasgos-trait-row__main">
                <span className="rasgos-trait-row__title">{trait.name || trait.fenotipo}</span>
                {(trait.genotipo || trait.genotype) && !['n/a', 'na'].includes(String(trait.genotipo || trait.genotype).trim().toLowerCase()) && (
                  <span className="rasgos-trait-row__genotype">{trait.genotipo || trait.genotype}</span>
                )}
              </span>
              
              <ChevronRight className="rasgos-trait-row__chevron" size={18} aria-hidden="true" />
            </button>
          );
        })}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Trait detail                                                        */
/* ------------------------------------------------------------------ */
function TraitDetail({ trait, group, onBackToCategory, onBackToOverview }) {
  if (!trait) return null;

  const meta = getLevelMeta(trait.nivel_riesgo, trait.magnitud_efecto ?? trait.magnitude ?? trait.effect_size);
  const rsid = trait.rsid || trait.rsId || trait.rsID || 'N/A';
  const genotype = trait.genotipo || trait.genotype || 'N/A';
  const explanation = trait.phenotype_description || trait.description || trait.explicacion;

  const field = (labelText, value, query, ariaLabel) => (
    <div className="rasgos-field">
      <div className="rasgos-field__label-row">
        <span className="rasgos-field__label">{labelText}</span>
        {query && <NalaTipButton query={query} ariaLabel={ariaLabel} />}
      </div>
      <span className="rasgos-field__value">{value}</span>
    </div>
  );

  return (
    <div className="rasgos-view">
      <Breadcrumb
        crumbs={[
          { label: 'Rasgos', onClick: onBackToOverview },
          { label: group.name, onClick: onBackToCategory },
          { label: trait.name || trait.fenotipo },
        ]}
      />

      <article className="rasgos-trait-detail" style={{ '--cat-color': meta.color }} aria-labelledby="rasgos-trait-title">
        <header className="rasgos-trait-detail__header">
            <span className="rasgos-trait-detail__eyebrow">Resultado individual</span>
            <div className="rasgos-trait-detail__title-row">
          <span className="rasgos-trait-detail__bar" style={{ backgroundColor: meta.color }} aria-hidden="true" />
          <h2 id="rasgos-trait-title" className="rasgos-trait-detail__title">{trait.name || trait.fenotipo}</h2>
          <span className="rasgos-trait-detail__chip" style={{ color: meta.color, background: tint(meta.color, '14') }}>
                {meta.label}
              </span>
            </div>
          </header>

        <details className="rasgos-glossary">
          <summary>Consultar glosario</summary>
          <div className="rasgos-glossary__content">
            <GlossaryCarousel terms={glossaryData} />
          </div>
        </details>

        <div className="rasgos-trait-detail__intro">
          <span className="rasgos-trait-detail__section-label">Qué significa</span>
          <p className="rasgos-trait-detail__explanation">
            {explanation || 'Aún no tenemos una descripción detallada para este rasgo.'}
          </p>
        </div>

        <div className="rasgos-trait-detail__metadata">
          <span className="rasgos-trait-detail__section-label">Datos del rasgo</span>
          <div className="rasgos-field-grid">
          {field('RS ID', rsid, `¿Qué es un rsID? (${rsid})`, 'Pregúntale a Nala sobre RS ID')}
          {field('Genotipo', genotype, `¿Qué significa el genotipo ${genotype}?`, 'Pregúntale a Nala sobre genotipo')}
          {field('Cromosoma', trait.cromosoma || 'N/A', '¿Qué significa cromosoma?', 'Pregúntale a Nala sobre cromosoma')}
          {field('Posición', trait.posicion || 'N/A', '¿Qué significa posición genómica?', 'Pregúntale a Nala sobre posición')}
          {field('Categoría', group.name, `¿Qué significa la categoría ${group.name}?`, 'Pregúntale a Nala sobre categoría')}
          </div>
        </div>

        <p className="rasgos-trait-detail__disclaimer">{DISCLAIMER}</p>
      </article>

      
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Main page                                                           */
/* ------------------------------------------------------------------ */
const Rasgos = () => {
  const [traits, setTraits] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [user, setUser] = useState(null);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [isMobile, setIsMobile] = useState(typeof window !== 'undefined' ? window.innerWidth <= 1024 : false);

  const [view, setView] = useState('overview'); // 'overview' | 'category' | 'trait'
  const [selectedGroup, setSelectedGroup] = useState(null);
  const [selectedTrait, setSelectedTrait] = useState(null);

  const navigate = useNavigate();

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

  useEffect(() => {
    fetchUser();
    fetchTraits();
  }, []);

  const fetchUser = async () => {
    const response = await apiRequest(API_ENDPOINTS.ME, { method: 'GET' });
    if (response.data) {
      setUser(response.data.user || response.data);
    }
  };

  const fetchTraits = async () => {
    setLoading(true);
    setError(null);
    const response = await apiRequest(API_ENDPOINTS.TRAITS, { method: 'GET' });
    if (!response.ok) {
      setError('No pudimos cargar tus rasgos genéticos. Intenta nuevamente.');
      setLoading(false);
      return;
    }
    const traitsData = response.data?.data?.traits || [];
    setTraits(traitsData);
    setLoading(false);
  };

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
    { label: 'Biomarcadores', href: '/dashboard/biomarcadores' },
    { label: 'Biométricas', href: '/dashboard/biometricas' },
    { label: 'Enfermedades', href: '/dashboard/enfermedades' },
  ], []);

  const groupedData = useMemo(() => {
    if (!traits || traits.length === 0) return [];
    const groups = {};
    traits.forEach((trait) => {
      const groupName = trait.group || 'Rasgos';
      if (!groups[groupName]) groups[groupName] = { traits: [] };
      groups[groupName].traits.push(trait);
    });

    const priorityOrder = [
      'Metabolismo',
      'Rendimiento Físico y Sensorial',
      'Cognición',
      'Bienestar y Salud',
      'Apariencia Física',
      'Rasgos',
    ];

    return Object.keys(groups)
      .sort((a, b) => {
        const ia = priorityOrder.indexOf(a);
        const ib = priorityOrder.indexOf(b);
        if (ia === -1 && ib === -1) return a.localeCompare(b);
        if (ia === -1) return 1;
        if (ib === -1) return -1;
        return ia - ib;
      })
      .map((groupName) => {
        const group = groups[groupName];
        const levelCounts = getLevelCounts(group.traits);
            let predominant = 'Neutral';
        let maxCount = 0;
        LEVEL_SEVERITY.forEach((key) => {
          const c = levelCounts[key] || 0;
          if (c > maxCount) {
            maxCount = c;
            predominant = key;
          }
        });
        return { name: groupName, traits: group.traits, levelMeta: LEVEL_META[predominant], levelCounts };
      });
  }, [traits]);

  const openCategory = (group) => {
    setSelectedGroup(group);
    setSelectedTrait(null);
    setView('category');
  };

  const openTrait = (trait, group) => {
    setSelectedGroup(group || selectedGroup);
    setSelectedTrait(trait);
    setView('trait');
  };

  const goToOverview = () => {
    setView('overview');
    setSelectedGroup(null);
    setSelectedTrait(null);
  };

  const goToCategory = () => {
    setView('category');
    setSelectedTrait(null);
  };

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
          {isMobileMenuOpen ? <X size={24} /> : <Menu size={24} />}
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
          {loading ? (
            <div className="rasgos-page__loading">
              <div className="spinner" />
              <p>Analizando tus rasgos genéticos...</p>
            </div>
          ) : error ? (
            <div className="rasgos-page__error">
              <p>{error}</p>
              <button type="button" onClick={fetchTraits}>Reintentar</button>
            </div>
          ) : !groupedData.length ? (
            <div className="rasgos-page__empty">
              <p>Aún no tenemos rasgos disponibles. Cuando tus resultados estén listos, verás aquí tus rasgos genéticos.</p>
            </div>
          ) : view === 'category' ? (
            <CategoryDetail group={selectedGroup} onBack={goToOverview} onOpenTrait={openTrait} />
          ) : view === 'trait' ? (
            <TraitDetail
              trait={selectedTrait}
              group={selectedGroup}
              onBackToCategory={goToCategory}
              onBackToOverview={goToOverview}
            />
          ) : (
            <Overview groupedData={groupedData} onOpenCategory={openCategory} />
          )}
        </div>
      </main>
    </div>
  );
};

export default Rasgos;
