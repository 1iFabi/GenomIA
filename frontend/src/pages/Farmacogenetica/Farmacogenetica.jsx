import React, { useContext, useEffect, useId, useMemo, useRef, useState } from 'react';
import { flushSync } from 'react-dom';
import { useNavigate } from 'react-router-dom';
import { ChevronLeft, Search, X } from 'lucide-react';
import { clearToken } from '../../config/api';
import { moduleRows, useLatestGenomicsResults } from '../../hooks/useLatestGenomicsResults';
import { useSession } from '../../hooks/useSession';
import { GenominContext } from '../../context/use-genomin';
import ModuleTitle from '../../components/ModuleTitle/ModuleTitle';
import ResultsBar from '../../components/ResultsBar/ResultsBar';
import { PGX_TITLE, PgxLoadingContent } from './FarmacoLoading';
import { SCALES, WARFARIN_SHORT, buildMedications, genePlain, matches, placeOf } from './pharmaco';
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

const reducedMotion = () => Boolean(window.matchMedia?.('(prefers-reduced-motion: reduce)').matches);
const slug = (s) => s.normalize('NFD').replace(/[^\w]/g, '').toLowerCase();
// the card grows into the page and back (View Transitions); without them the swap is instant
const transition = (update) => {
  if (!document.startViewTransition || reducedMotion()) update();
  else document.startViewTransition(update);
};

// Where you sit on your gene's scale: the dot falls into its stretch as it comes into view; "habitual"
// marks the expected stretch. Position only, never a verdict colour.
const SpeedRule = ({ gene, big = false }) => {
  const place = placeOf(gene.phenotype);
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
  const { steps, usual } = SCALES[place.scale];
  const n = steps.length;
  const at = `${((place.step + 0.5) / n) * 100}%`;
  const capAt = usual === 0 ? { left: 0 } : usual === n - 1 ? { right: 0 } : { left: `${((usual + 0.5) / n) * 100}%`, transform: 'translateX(-50%)' };
  return (
    <div ref={ref} className={`pgx-rule${big ? ' pgx-rule--big' : ''}${lit ? ' is-lit' : ''}`} style={{ '--n': n, '--at': at }}
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

const Note = ({ usual }) => <span className={`pgx-note${usual ? ' pgx-note--same' : ''}`}>{usual ? 'Como la mayoría' : 'Para conversar con tu médico'}</span>;

const MedCard = ({ med, mine, onOpen }) => (
  <li>
    <button type="button" className={`pgx-card${mine ? ' is-mine' : ''}`} data-med={med.name} style={{ viewTransitionName: `pgx-${slug(med.name)}` }} onClick={() => onOpen(med.name)}>
      {mine && <span className="pgx-card__mine">Lo tomas</span>}
      <span className="pgx-card__head">
        <span className="pgx-card__name">{med.name}</span>
        {med.use && <span className="pgx-card__use">{med.use}</span>}
      </span>
      <span className="pgx-card__say">{med.say}</span>
      <SpeedRule gene={med.genes[0]} />
      {med.genes.length > 1 && <span className="pgx-card__two">Lo deciden <b>{med.genes.map((g) => g.gene).join(' y ')}</b></span>}
    </button>
  </li>
);

// two genes meeting at one medication (the warfarin): the lines draw in toward it
const Converge = ({ med }) => {
  const [a, b] = med.genes;
  const label = (gene) => WARFARIN_SHORT[gene.gene]?.[placeOf(gene.phenotype)?.step] || gene.phenotype.toLowerCase();
  return (
    <svg className="pgx-converge" viewBox="0 0 340 150" role="img" aria-label={`${a.gene} y ${b.gene} llegan juntos a ${med.name.toLowerCase()}`}>
      <path d="M86 32 C 170 32, 190 75, 250 75" />
      <path d="M86 118 C 170 118, 190 75, 250 75" />
      <rect x="2" y="14" width="96" height="36" rx="10" /><text x="14" y="37">{a.gene}</text>
      <rect x="2" y="100" width="96" height="36" rx="10" /><text x="14" y="123">{b.gene}</text>
      <text x="104" y="22">{label(a)}</text><text x="104" y="144">{label(b)}</text>
      <rect className="pgx-converge__end" x="228" y="57" width="112" height="36" rx="18" />
      <text className="pgx-converge__name" x="284" y="80" textAnchor="middle">{med.name}</text>
    </svg>
  );
};

const MedDetail = ({ med, onBack }) => {
  const genomin = useContext(GenominContext);
  const back = useRef(null);
  useEffect(() => { back.current?.focus({ preventScroll: true }); }, []);
  return (
    <article className="pgx-detail" style={{ viewTransitionName: `pgx-${slug(med.name)}` }} aria-labelledby="pgx-detail-title">
      <button ref={back} type="button" className="pgx-back" onClick={onBack}>
        <ChevronLeft size={20} aria-hidden="true" />Medicamentos
      </button>
      <h2 id="pgx-detail-title">{med.name}</h2>
      {med.use && <p className="pgx-detail__use">{med.use}</p>}
      <p className="pgx-detail__say">{med.say}</p>
      <Note usual={med.usual} />
      {med.genes.length === 2 && <Converge med={med} />}
      {med.genes.map((gene) => (
        <section key={gene.gene} className="pgx-why">
          <h3>{gene.gene}: {gene.phenotype.toLowerCase()}</h3>
          <p>{genePlain(gene.gene)}</p>
          <SpeedRule gene={gene} big />
        </section>
      ))}
      <details className="pgx-tech">
        <summary>Detalle técnico para tu médico</summary>
        <dl>
          {med.genes.map((gene) => (
            <div key={gene.gene}>
              <dt>{gene.gene} <span>{gene.diplotype}</span></dt>
              <dd>{gene.phenotype}</dd>
            </div>
          ))}
        </dl>
      </details>
      {genomin && (
        <button type="button" className="pgx-ask" onClick={() => genomin.openGenomin()}>
          <img src="/genomin.png" alt="" width="26" height="26" />Pregúntale a Genomin
        </button>
      )}
    </article>
  );
};

// "¿Cuáles tomas?": what you pick goes to your velador; it never leaves this screen
const Kit = ({ meds, mine, onAdd, onDrop, onOpen }) => {
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);
  const [at, setAt] = useState(-1);
  const listId = useId();
  const hits = meds.filter((m) => !mine.includes(m.name) && matches(m, query));
  const add = (name) => { onAdd(name); setQuery(''); setAt(-1); };
  const onKeyDown = (event) => {
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      setOpen(true);
      if (hits.length) setAt((i) => (i + (event.key === 'ArrowDown' ? 1 : -1) + hits.length) % hits.length);
    } else if (event.key === 'Enter' && hits.length) {
      event.preventDefault();
      add(hits[Math.max(at, 0)].name);
    } else if (event.key === 'Escape') setOpen(false);
  };
  return (
    <section className="pgx-kit" aria-labelledby={`${listId}-label`}>
      <label id={`${listId}-label`} htmlFor={`${listId}-q`}>¿Cuáles tomas o te recetaron?</label>
      <div className="pgx-search">
        <Search size={20} aria-hidden="true" />
        <input
          id={`${listId}-q`} type="search" autoComplete="off" placeholder="Busca un medicamento"
          role="combobox" aria-expanded={open} aria-controls={`${listId}-list`} aria-autocomplete="list"
          aria-activedescendant={open && at >= 0 && hits[at] ? `${listId}-o${at}` : undefined}
          value={query}
          onChange={(e) => { setQuery(e.target.value); setOpen(true); setAt(-1); }}
          onFocus={() => setOpen(true)}
          onBlur={() => setTimeout(() => setOpen(false), 150)}
          onKeyDown={onKeyDown}
        />
      </div>
      {open && (
        <ul className="pgx-suggest" id={`${listId}-list`} role="listbox" aria-label="Medicamentos de tu informe">
          {hits.length ? hits.map((m, i) => (
            <li key={m.name} id={`${listId}-o${i}`} role="option" aria-selected={i === at}
              onMouseDown={(e) => e.preventDefault()} onClick={() => add(m.name)}>
              <span>{m.name}</span><small>{m.use}</small>
            </li>
          )) : <li className="pgx-suggest__none">No está en tu informe</li>}
        </ul>
      )}
      <p className="pgx-kit__hint">Tu lista no se guarda ni se envía: vive solo en esta pantalla.</p>
      {mine.length > 0 && (
        <ul className="pgx-velador" aria-label="Tu velador">
          {mine.map((name) => {
            const med = meds.find((m) => m.name === name);
            return (
              <li key={name} className="pgx-pill">
                <button type="button" className="pgx-pill__open" onClick={() => onOpen(name)}>
                  <b>{name}</b><span>{med.usual ? 'Como la mayoría' : 'Para conversar con tu médico'}</span>
                </button>
                <button type="button" className="pgx-pill__drop" aria-label={`Quitar ${name}`} onClick={() => onDrop(name)}>
                  <X size={14} aria-hidden="true" />
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
};

const Farmacogenetica = () => {
  const { user } = useSession();
  const navigate = useNavigate();
  const results = useLatestGenomicsResults();
  const genes = moduleRows(results, 'pharmacogenetics');
  const status = results.status === 'ready' && !genes.length ? 'missing' : results.status;
  const failed = ['permission', 'error'].includes(status);
  const meds = useMemo(() => buildMedications(genes), [genes]);
  const [lens, setLens] = useState('med');
  const [mine, setMine] = useState([]);
  const [selected, setSelected] = useState(null);
  const [said, setSaid] = useState('');
  const scrollBack = useRef(0);

  const handleLogout = async () => {
    await clearToken();
    navigate('/');
  };

  const openMed = (name) => {
    scrollBack.current = window.scrollY;
    transition(() => { flushSync(() => setSelected(name)); window.scrollTo?.(0, 0); });
  };
  // back to where the reader was, the focus on the card they opened
  const closeMed = () => {
    const name = selected;
    transition(() => {
      flushSync(() => setSelected(null));
      window.scrollTo?.(0, scrollBack.current);
      document.querySelector(`.pgx-card[data-med="${name}"]`)?.focus({ preventScroll: true });
    });
  };
  useEffect(() => {
    if (!selected) return undefined;
    const onKey = (event) => { if (event.key === 'Escape') closeMed(); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  });

  const selectedMed = selected && meds.all.find((m) => m.name === selected);
  const picked = mine.length > 0;
  const count = (n, one, many) => `${n} ${n === 1 ? one : many}`;

  return (
    <div className="farmacogenetica-layout-new">
      <main className="farmaco-main-content">
        <ResultsBar user={user} onLogout={handleLogout} />
        <div className="pgx">
          <p className="pgx-sr" aria-live="polite">{said}</p>
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

          {status === 'ready' && selectedMed && <MedDetail med={selectedMed} onBack={closeMed} />}

          {status === 'ready' && !selectedMed && (
            <>
              <p className="pgx-sr" role="status" aria-label="Estado de los resultados" aria-busy={false}>{resultMessages.ready}</p>
              <header className="pgx-hero">
                <ModuleTitle className="pgx-title" moduleKey="pharmacogenetics" title={PGX_TITLE} />
                <p>
                  Revisamos <b>{count(meds.all.length, 'medicamento', 'medicamentos')}</b> con {count(genes.length, 'de tus genes', 'de tus genes')}.
                  {meds.talk.length > 0 && <> En <b>{meds.talk.length}</b> tu cuerpo los procesa distinto a la mayoría</>}
                  {meds.talk.length > 0 && meds.same.length > 0 && <>; en {meds.same.length}, igual.</>}
                  {meds.talk.length > 0 && !meds.same.length && '.'}
                  {!meds.talk.length && ' Todos los procesas como la mayoría.'}
                </p>
              </header>

              <Kit
                meds={meds.all}
                mine={mine}
                onAdd={(name) => { setMine((list) => [...list, name]); setSaid(`${name} quedó en tu velador`); }}
                onDrop={(name) => { setMine((list) => list.filter((n) => n !== name)); setSaid(`${name} salió de tu velador`); }}
                onOpen={openMed}
              />

              <div className="pgx-lens" role="group" aria-label="Ver por">
                {[['med', 'Por medicamento'], ['gene', 'Por gen']].map(([key, label]) => (
                  <button key={key} type="button" aria-pressed={lens === key} onClick={() => setLens(key)}>{label}</button>
                ))}
              </div>

              {lens === 'med' ? (
                <>
                  {meds.talk.length > 0 && (
                    <section className={`pgx-group${picked ? ' is-dim' : ''}`} aria-labelledby="pgx-talk">
                      <h2 id="pgx-talk">Para conversar con tu médico</h2>
                      <p>Tu cuerpo los procesa distinto a la mayoría. No es una alerta: es algo que tu médico puede usar al elegir la dosis.</p>
                      <ul className="pgx-cards">{meds.talk.map((m) => <MedCard key={m.name} med={m} mine={mine.includes(m.name)} onOpen={openMed} />)}</ul>
                    </section>
                  )}
                  {meds.same.length > 0 && (
                    <section className={`pgx-group${picked ? ' is-dim' : ''}`} aria-labelledby="pgx-same">
                      <h2 id="pgx-same">Como la mayoría</h2>
                      <p>Los procesas como se espera.</p>
                      <ul className="pgx-cards">{meds.same.map((m) => <MedCard key={m.name} med={m} mine={mine.includes(m.name)} onOpen={openMed} />)}</ul>
                    </section>
                  )}
                </>
              ) : (
                <section className="pgx-group" aria-labelledby="pgx-genes">
                  <h2 id="pgx-genes">Tus {genes.length} genes</h2>
                  <p>Cada uno decide cómo procesas uno o más medicamentos.</p>
                  <ul className="pgx-cards">
                    {genes.map((gene) => (
                      <li key={gene.gene} className="pgx-card pgx-card--gene">
                        <h3 className="pgx-card__head"><span className="pgx-card__name">{gene.gene}</span><span className="pgx-card__use">{gene.phenotype.toLowerCase()}</span></h3>
                        <p className="pgx-card__say">{genePlain(gene.gene)}</p>
                        <SpeedRule gene={gene} />
                        <ul className="pgx-chips" aria-label="Medicamentos">
                          {(gene.drugs || []).map((d) => <li key={d}><button type="button" onClick={() => openMed(d)}>{d}</button></li>)}
                        </ul>
                      </li>
                    ))}
                  </ul>
                </section>
              )}
            </>
          )}

          {status === 'ready' && (
            <footer className="pgx-foot">
              <p><b>{SAFETY}</b> Es una estimación genética: tu dosis también depende de tu edad, tu peso y otros remedios.</p>
              {results.data?.disclaimer && <p className="farmaco-disclaimer">{results.data.disclaimer}</p>}
            </footer>
          )}
        </div>
      </main>
    </div>
  );
};

export default Farmacogenetica;
