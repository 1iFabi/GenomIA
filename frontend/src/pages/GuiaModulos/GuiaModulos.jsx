import React, { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Menu, X } from 'lucide-react';
import { clearToken } from '../../config/api';
import { RESULT_NAV_ITEMS } from '../../config/resultNav';
import { useLatestGenomicsResults } from '../../hooks/useLatestGenomicsResults';
import { useSession } from '../../hooks/useSession';
import Sidebar from '../../components/Sidebar/Sidebar';
import { animatedSidebarIcons } from '../../components/Sidebar/animatedSidebarIcons';
import { DashboardPageSkeleton, SkeletonBlock } from '../../components/DashboardSkeleton/DashboardSkeleton';
import './GuiaModulos.css';

const MAX_ROWS = 10;

// One entry per backend module: what it means, where it comes from and which fields it sends.
const MODULE_GUIDE = [
  {
    key: 'global_ancestry', title: 'Ancestría global', page: '/dashboard/ancestria', pageLabel: 'Ancestría',
    what: 'Qué proporción de tu genoma proviene de cada población de referencia. Cada población está asociada '
      + 'a un país y pertenece a una región continental.',
    source: 'Simulado. Se calcula sumando los segmentos de ancestría local.',
    shownAs: 'Mapa con los países coloreados según su % y lista agrupada por región.',
    fields: [
      ['label', 'Población de referencia (ej. Mapuche, Ibérico).'],
      ['country', 'País asociado a la población; se usa para marcar el mapa.'],
      ['country_code', 'Código ISO del país (CL, ES…).'],
      ['group_label', 'Región continental (Amerindio, Europeo, Africano, Asiático).'],
      ['proportion', 'Fracción del genoma, de 0 a 1 (0,30 = 30%).'],
    ],
  },
  {
    key: 'local_ancestry', title: 'Ancestría local', page: '/dashboard/ancestria', pageLabel: 'Ancestría',
    what: 'De qué región proviene cada tramo de tu cromosoma, por separado en cada una de tus dos copias '
      + '(una heredada de cada progenitor).',
    source: 'Simulado. Hoy solo cubre el cromosoma 1.',
    shownAs: 'Lista de segmentos en el panel lateral de Ancestría.',
    fields: [
      ['haplotype', 'Copia del cromosoma: 0 o 1.'],
      ['contig', 'Cromosoma.'],
      ['start', 'Inicio del tramo, en pares de bases.'],
      ['end', 'Fin del tramo, en pares de bases.'],
      ['label', 'Región de origen del tramo.'],
      ['confidence', 'Confianza de la asignación, de 0 a 1.'],
    ],
  },
  {
    key: 'monogenic_risk', title: 'Riesgo monogénico', page: '/dashboard/enfermedades', pageLabel: 'Enfermedades',
    what: 'Variantes patogénicas o probablemente patogénicas encontradas en tu genoma. En estas condiciones '
      + 'una sola variante puede ser relevante.',
    source: 'Real: significado clínico de ClinVar para las variantes asignadas.',
    shownAs: 'Tarjeta «Variantes patogénicas (ClinVar)» en Enfermedades.',
    fields: [
      ['gene', 'Gen donde está la variante.'],
      ['clinical_significance', 'Clasificación ClinVar (Pathogenic, Likely_pathogenic…).'],
      ['conditions', 'Condiciones asociadas según ClinVar.'],
      ['zygosity', 'Heterocigoto = una copia (portador); homocigoto = dos copias.'],
      ['review_status', 'Nivel de revisión de la evidencia en ClinVar.'],
      ['position', 'Posición en el cromosoma.'],
    ],
  },
  {
    key: 'polygenic_risk', title: 'Riesgo poligénico', page: '/dashboard/enfermedades', pageLabel: 'Enfermedades',
    what: 'Suma el efecto de muchas variantes de bajo impacto para una condición y te compara con una '
      + 'población de referencia.',
    source: 'Simulado a partir de tus genotipos asignados.',
    shownAs: 'Tarjeta «Riesgo poligénico» en Enfermedades.',
    fields: [
      ['label', 'Condición evaluada.'],
      ['percentile', 'Tu posición frente a la población, de 0 a 100.'],
      ['category', 'Bajo (≤ 20), Promedio o Elevado (≥ 80).'],
      ['score', 'Puntaje poligénico crudo.'],
      ['risk_loci', 'Cantidad de variantes que aportan al puntaje.'],
    ],
  },
  {
    key: 'pharmacogenetics', title: 'Farmacogenética', page: '/dashboard/farmacogenetica', pageLabel: 'Farmacogenética',
    what: 'Cómo tus genes influyen en la forma en que tu cuerpo procesa ciertos medicamentos.',
    source: 'Simulado.',
    shownAs: 'Lista de genes con su fenotipo y fármacos en Farmacogenética.',
    fields: [
      ['gene', 'Gen que procesa los fármacos.'],
      ['diplotype', 'Combinación de alelos heredados (ej. *1/*2).'],
      ['phenotype', 'Tipo de metabolizador resultante.'],
      ['drugs', 'Medicamentos afectados.'],
    ],
  },
  {
    key: 'traits', title: 'Rasgos', page: '/dashboard/rasgos', pageLabel: 'Rasgos',
    what: 'Características no clínicas como apariencia, metabolismo, rendimiento o cronotipo.',
    source: 'Simulado; los genes y rsID son asociaciones conocidas.',
    shownAs: 'Categorías en Rasgos; cada rasgo muestra su resultado y explicación.',
    fields: [
      ['category', 'Categoría del rasgo.'],
      ['label', 'Nombre del rasgo.'],
      ['result', 'Tu resultado.'],
      ['explanation', 'Qué significa tu resultado.'],
      ['description', 'Qué hace el gen.'],
      ['gene', 'Gen asociado.'],
      ['rsid', 'Variante de referencia.'],
    ],
  },
  {
    key: 'variants', title: 'Variantes asignadas (base)', page: null,
    what: 'Las variantes de tu genoma de las que salen los otros módulos.',
    source: 'Real: variantes y significado de ClinVar; los genotipos son asignados.',
    shownAs: 'Aún no se muestran en ninguna página.',
    fields: [
      ['rsid', 'Identificador de la variante.'],
      ['gene', 'Gen afectado.'],
      ['genotype', 'Tus alelos (0|1 = una copia alternativa).'],
      ['zygosity', 'Heterocigoto u homocigoto.'],
      ['clinical_significance', 'Clasificación ClinVar.'],
      ['alt_allele_ancestry', 'Región de origen de la copia que porta la variante.'],
    ],
  },
];

const formatValue = (value) => {
  if (value === null || value === undefined || value === '') return '—';
  if (Array.isArray(value)) return value.join(', ') || '—';
  if (typeof value === 'number') return Number.isInteger(value) ? String(value) : value.toFixed(4);
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
};

const rowsFor = (data, key) => {
  const rows = key === 'variants' ? data?.variants : data?.modules?.[key];
  return Array.isArray(rows) ? rows : [];
};

function ModuleCard({ module, data, ready, loading }) {
  const rows = rowsFor(data, module.key);
  const columns = module.fields.map(([field]) => field);
  return (
    <section className="guia-card" aria-labelledby={`guia-${module.key}-title`}>
      <header className="guia-card__header">
        <h2 id={`guia-${module.key}-title`}>{module.title}</h2>
        <code>{module.key}</code>
      </header>
      <p className="guia-card__what">{module.what}</p>
      <dl className="guia-card__meta">
        <div><dt>Origen del dato</dt><dd>{module.source}</dd></div>
        <div>
          <dt>Cómo se muestra hoy</dt>
          <dd>
            {module.shownAs}
            {module.page && <> <Link to={module.page}>Ir a {module.pageLabel}</Link></>}
          </dd>
        </div>
      </dl>
      <h3>Campos que envía el backend</h3>
      <dl className="guia-card__fields">
        {module.fields.map(([field, meaning]) => (
          <div key={field}><dt><code>{field}</code></dt><dd>{meaning}</dd></div>
        ))}
      </dl>
      <h3>{loading ? 'Tus datos' : `Tus datos (${rows.length} ${rows.length === 1 ? 'fila' : 'filas'})`}</h3>
      {loading ? (
        <div className="guia-card__loading">
          {[0, 1].map((index) => (
            <div className="guia-card__loading-row" key={index}>
              <SkeletonBlock className="guia-card__loading-field" />
              <SkeletonBlock className="guia-card__loading-value" />
            </div>
          ))}
        </div>
      ) : !ready ? <p className="guia-card__empty">Sin datos cargados.</p> : rows.length === 0 ? (
        <p className="guia-card__empty">Tu último servicio no tiene filas para este módulo.</p>
      ) : (
        <div className="guia-card__table">
          <table>
            <thead><tr>{columns.map((column) => <th key={column} scope="col">{column}</th>)}</tr></thead>
            <tbody>
              {rows.slice(0, MAX_ROWS).map((row, index) => (
                <tr key={index}>{columns.map((column) => <td key={column}>{formatValue(row[column])}</td>)}</tr>
              ))}
            </tbody>
          </table>
          {rows.length > MAX_ROWS && <p className="guia-card__more">… y {rows.length - MAX_ROWS} filas más.</p>}
        </div>
      )}
    </section>
  );
}

const statusMessages = {
  loading: 'Cargando tus datos…',
  empty: 'Aún no tienes resultados; la guía muestra solo la descripción de cada módulo.',
  permission: 'No tienes permiso para consultar estos resultados.',
  error: 'No fue posible cargar tus datos.',
};

const GuiaModulos = () => {
  const { user } = useSession();
  const navigate = useNavigate();
  const results = useLatestGenomicsResults();
  const [isMobile, setIsMobile] = useState(false);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const ready = results.status === 'ready';

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
    <div className="guia-layout">
      {isMobile && (
        <button
          type="button"
          className="guia-burger"
          onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
          aria-label={isMobileMenuOpen ? 'Cerrar menú' : 'Abrir menú'}
          aria-expanded={isMobileMenuOpen}
        >
          {isMobileMenuOpen ? <X size={24} aria-hidden="true" /> : <Menu size={24} aria-hidden="true" />}
        </button>
      )}
      <aside className="guia-layout__sidebar">
        <Sidebar
          iconOverrides={animatedSidebarIcons}
          items={RESULT_NAV_ITEMS}
          onLogout={handleLogout}
          user={user}
          isMobileMenuOpen={isMobileMenuOpen}
          setIsMobileMenuOpen={setIsMobileMenuOpen}
        />
      </aside>
      <main className="guia-layout__main">
        <header className="guia-header">
          <span className="guia-header__kicker">Referencia</span>
          <h1>Guía de módulos</h1>
          <p>Qué información entrega cada módulo, de dónde viene y cómo se muestra hoy, junto a tus datos reales.</p>
        </header>
        {results.status === 'loading' ? (
          <DashboardPageSkeleton className="guia-loading-status" label={statusMessages.loading} />
        ) : statusMessages[results.status] && (
          <p className="guia-status" role={['permission', 'error'].includes(results.status) ? 'alert' : 'status'}>
            {statusMessages[results.status]}
          </p>
        )}
        {results.data?.disclaimer && <p className="guia-disclaimer">{results.data.disclaimer}</p>}
        <div className="guia-grid">
          {MODULE_GUIDE.map((module) => (
            <ModuleCard key={module.key} module={module} data={results.data} ready={ready} loading={results.status === 'loading'} />
          ))}
        </div>
      </main>
    </div>
  );
};

export default GuiaModulos;
