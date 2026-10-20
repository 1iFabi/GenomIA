import React, { Fragment, useEffect, useId, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ChevronDown, ChevronsUpDown, Search, X } from 'lucide-react';
import { clearToken } from '../../config/api';
import { moduleRows, useLatestGenomicsResults } from '../../hooks/useLatestGenomicsResults';
import { useSession } from '../../hooks/useSession';
import ModuleTitle from '../../components/ModuleTitle/ModuleTitle';
import ResultsBar from '../../components/ResultsBar/ResultsBar';
import { PGX_TITLE, PgxLoadingContent } from './FarmacoLoading';
import { ORDER, SCALES, VERDICTS, buildTable, genePlain, matches, placeOf, usualStep } from './pharmaco';
import './Farmacogenetica.css';

const resultMessages = {
  loading: 'Cargando datos…',
  empty: 'Aún no tienes resultados disponibles.',
  missing: 'Tu último servicio no tiene resultados de farmacogenética.',
  permission: 'No tienes permiso para consultar estos resultados.',
  error: 'No fue posible cargar los datos. Puedes reintentar.',
  ready: 'Datos disponibles.',
};
const SAFETY = 'No cambies ni dejes un medicamento sin hablar con tu médico.';
const NO_GUIDE = 'No encontramos ese remedio entre los que tienen guía genética: tus genes no cambian la indicación conocida.';

const reducedMotion = () => Boolean(window.matchMedia?.('(prefers-reduced-motion: reduce)').matches);

// Where you sit on your gene's scale: the dot falls into its stretch as it comes into view; "habitual"
// marks the expected stretch. Position only, never a verdict colour.
const SpeedRule = ({ gene }) => {
  const place = placeOf(gene.phenotype, gene.gene);
  const ref = useRef(null);
  const [lit, setLit] = useState(false);
  useEffect(() => {
    if (!place) return undefined;
    if (reducedMotion() || typeof IntersectionObserver === 'undefined') { setLit(true); return undefined; }
    const io = new IntersectionObserver(([entry]) => { if (entry.isIntersecting) { setLit(true); io.disconnect(); } }, { threshold: 0.6 });
    io.observe(ref.current);
    return () => io.disconnect();
  }, [place]);
  if (!place) return null;
  const { steps } = SCALES[place.scale];
  const usual = usualStep(gene.gene, place.scale);
  const n = steps.length;
  const at = `${((place.step + 0.5) / n) * 100}%`;
  const capAt = usual === 0 ? { left: 0 } : usual === n - 1 ? { right: 0 } : { left: `${((usual + 0.5) / n) * 100}%`, transform: 'translateX(-50%)' };
  return (
    <div ref={ref} className={`pgx-rule${lit ? ' is-lit' : ''}`} style={{ '--n': n, '--at': at }}
      role="img" aria-label={`${gene.gene}: ${gene.phenotype}. Escala de ${steps[0].toLowerCase()} a ${steps[n - 1].toLowerCase()}; lo habitual es ${steps[usual].toLowerCase()}.`}>
      <div className="pgx-rule__caps" aria-hidden="true">{place.step !== usual && <span style={capAt}>habitual</span>}</div>
      <div className="pgx-rule__track" aria-hidden="true">
        {steps.map((step, k) => <span key={step} className={k === usual ? 'is-usual' : undefined} />)}
        <i className="pgx-rule__dot" />
      </div>
      <div className="pgx-rule__labels" aria-hidden="true">
        <span className={place.step === 0 ? 'is-you' : undefined}>{steps[0]}</span>
        {place.step > 0 && place.step < n - 1 && <b className="is-you pgx-rule__at">{steps[place.step]}</b>}
        <span className={place.step === n - 1 ? 'is-you' : undefined}>{steps[n - 1]}</span>
      </div>
    </div>
  );
};

const Verdict = ({ v }) => <span className="pgx-verdict"><i className={`pgx-dot pgx-dot--${v}`} aria-hidden="true" />{VERDICTS[v]}</span>;

// how the table splits: one segment per verdict, wide as its share; a segment filters the table
const PartitionBar = ({ counts, filter, onFilter }) => {
  const shown = ORDER.filter((v) => counts[v]);
  return (
    <div className={`pgx-pbar${filter ? ' is-filtered' : ''}`} role="group" aria-label="Filtrar por efecto">
      {shown.map((v) => (
        <button key={v} type="button" className={`pgx-pbar__seg pgx-pbar__seg--${v}`} style={{ flexGrow: counts[v] }}
          aria-pressed={filter === v} onClick={() => onFilter(filter === v ? null : v)}>
          <i aria-hidden="true" />
          <b>{counts[v]}</b>
          <span>{VERDICTS[v]}</span>
        </button>
      ))}
    </div>
  );
};

const MedDetail = ({ med, id }) => (
  <div className="pgx-detail" id={id}>
    <div className="pgx-detail__main">
      <p className="pgx-detail__say">{med.say}</p>
      {med.missing && <p className="pgx-detail__missing">{med.missing}</p>}
    </div>
    {med.genes?.length > 0 && (
      <div className="pgx-detail__genes">
        {med.genes.map((gene) => (
          <section key={gene.gene} className="pgx-gene">
            <h4>Tu {gene.gene} <span>{gene.diplotype}</span></h4>
            <p><b>{gene.phenotype}</b> · {genePlain(gene.gene)}</p>
            <SpeedRule gene={gene} />
          </section>
        ))}
      </div>
    )}
  </div>
);

const SORTS = {
  v: (a, b) => ORDER.indexOf(a.v) - ORDER.indexOf(b.v),
  name: () => 0,
  gene: (a, b) => (a.genes?.[0]?.gene || a.gene || '').localeCompare(b.genes?.[0]?.gene || b.gene || ''),
};

const MedTable = ({ table }) => {
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState(null);
  const [sort, setSort] = useState(['v', 1]);
  const [open, setOpen] = useState(null);
  const uid = useId();

  // a search also reaches the drugs whose genes this exam does not read, so they never pass as "as usual"
  const rows = useMemo(() => {
    const untested = query.trim()
      ? table.untested.filter((m) => matches(m, query)).map((m) => ({
        ...m, v: 'miss', say: `Depende de ${m.gene}, que tu examen no lee. No sabemos cómo te afecta: no es lo mismo que «como la mayoría».`,
      }))
      : [];
    const [key, dir] = sort;
    return [...table.meds.filter((m) => matches(m, query)), ...untested]
      .filter((m) => !filter || m.v === filter)
      .sort((a, b) => dir * (SORTS[key](a, b) || a.name.localeCompare(b.name, 'es')));
  }, [table, query, filter, sort]);

  const head = (key, label, className) => (
    <th className={className} aria-sort={sort[0] === key ? (sort[1] > 0 ? 'ascending' : 'descending') : undefined}>
      <button type="button" onClick={() => setSort(([k, d]) => [key, k === key ? -d : 1])}>
        {label}<ChevronsUpDown size={13} aria-hidden="true" />
      </button>
    </th>
  );
  const toggle = (name) => setOpen((current) => (current === name ? null : name));
  let group = null;

  return (
    <>
      <PartitionBar counts={table.counts} filter={filter} onFilter={setFilter} />
      <div className="pgx-table">
        <div className="pgx-table__bar">
          <label className="pgx-search">
            <Search size={17} aria-hidden="true" />
            <span className="pgx-sr">Buscar remedio</span>
            <input type="search" autoComplete="off" placeholder="Buscar remedio" value={query}
              onChange={(e) => { setQuery(e.target.value); setOpen(null); }} />
            {query && (
              <button type="button" className="pgx-search__clear" aria-label="Borrar búsqueda" onClick={() => setQuery('')}>
                <X size={15} aria-hidden="true" />
              </button>
            )}
          </label>
          <span className="pgx-table__count" aria-live="polite">{rows.length} {rows.length === 1 ? 'remedio' : 'remedios'}</span>
        </div>
        <table>
          <thead>
            <tr>
              {head('name', 'Remedio')}
              {head('gene', 'Gen', 'pgx-wide')}
              <th className="pgx-wide"><span className="pgx-th">Tu gen</span></th>
              {head('v', 'Efecto en ti')}
              <th className="pgx-chev"><span className="pgx-sr">Detalle</span></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((med) => {
              const header = sort[0] === 'v' && med.v !== group;
              group = med.v;
              const isOpen = open === med.name;
              const detailId = `${uid}-${med.name}`;
              return (
                <Fragment key={med.name}>
                  {header && <tr className="pgx-group"><th colSpan={5} scope="rowgroup">{VERDICTS[med.v]}</th></tr>}
                  <tr className={`pgx-row${isOpen ? ' is-open' : ''}`} data-med={med.name} onClick={() => toggle(med.name)}>
                    <td>
                      <button type="button" className="pgx-row__name" aria-expanded={isOpen} aria-controls={isOpen ? detailId : undefined}>{med.name}</button>
                      <span className="pgx-row__use">{med.use || 'Fuera de tu examen'}</span>
                    </td>
                    <td className="pgx-wide">{med.genes ? med.genes.map((g) => g.gene).join(' + ') : med.gene}</td>
                    <td className="pgx-wide">{med.genes ? med.genes.map((g) => g.phenotype).join(' · ') : 'No analizado'}</td>
                    <td><Verdict v={med.v} /></td>
                    <td className="pgx-chev"><ChevronDown size={16} aria-hidden="true" /></td>
                  </tr>
                  {isOpen && (
                    <tr className="pgx-row-detail">
                      <td colSpan={5}><MedDetail med={med} id={detailId} /></td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
            {!rows.length && (
              <tr className="pgx-none"><td colSpan={5}>{filter ? `Ningún remedio de «${VERDICTS[filter]}» coincide con tu búsqueda.` : NO_GUIDE}</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </>
  );
};

const Farmacogenetica = () => {
  const { user } = useSession();
  const navigate = useNavigate();
  const results = useLatestGenomicsResults();
  const genes = moduleRows(results, 'pharmacogenetics');
  const status = results.status === 'ready' && !genes.length ? 'missing' : results.status;
  const failed = ['permission', 'error'].includes(status);
  const table = useMemo(() => buildTable(genes), [genes]);

  const handleLogout = async () => {
    await clearToken();
    navigate('/');
  };

  return (
    <div className="farmacogenetica-layout-new">
      <main className="farmaco-main-content">
        <ResultsBar user={user} onLogout={handleLogout} />
        <div className="pgx">
          {status !== 'ready' && (
            status === 'loading' ? (
              <>
                <header className="pgx-hero"><ModuleTitle className="pgx-title" moduleKey="pharmacogenetics" title={PGX_TITLE} /></header>
                <PgxLoadingContent label={resultMessages.loading} />
              </>
            ) : (
              <div className="pgx-status">
                <h1 className="pgx-title">Farmacogenética</h1>
                <p role={failed ? 'alert' : 'status'} aria-label="Estado de los resultados" aria-busy={false}>{resultMessages[status]}</p>
                <button type="button" className="pgx-retry" aria-label="Reintentar carga de resultados" onClick={results.retry}>Reintentar</button>
              </div>
            )
          )}

          {status === 'ready' && (
            <>
              <p className="pgx-sr" role="status" aria-label="Estado de los resultados" aria-busy={false}>{resultMessages.ready}</p>
              <header className="pgx-hero">
                <ModuleTitle className="pgx-title" moduleKey="pharmacogenetics" title={PGX_TITLE} />
                <p className="pgx-hero__lede">
                  <b>{table.meds.length} remedios</b> tienen una guía según tus genes. Toca uno para ver qué gen lo decide y qué significa para ti.
                </p>
              </header>
              <MedTable table={table} />
              <footer className="pgx-foot">
                <p><b>{SAFETY}</b> Es una estimación genética: tu dosis también depende de tu edad, tu peso y otros remedios.</p>
              </footer>
            </>
          )}
        </div>
      </main>
    </div>
  );
};

export default Farmacogenetica;
