import React, { useId, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ChevronDown } from 'lucide-react';
import { clearToken } from '../../config/api';
import { moduleRows, useLatestGenomicsResults } from '../../hooks/useLatestGenomicsResults';
import { useSession } from '../../hooks/useSession';
import ModuleTitle from '../../components/ModuleTitle/ModuleTitle';
import ResultsBar from '../../components/ResultsBar/ResultsBar';
import {
  MOI_PLAIN, MOI_TEXT, QUESTIONS, bucket, byGene, certainty, certaintyWhy, consequence, significanceOf,
} from './monogenic';
import './Monogenico.css';

const resultMessages = {
  loading: 'Cargando datos…',
  empty: 'Aún no tienes resultados disponibles.',
  missing: 'Tu último servicio no tiene resultados de riesgo monogénico.',
  permission: 'No tienes permiso para consultar estos resultados.',
  error: 'No fue posible cargar los datos. Puedes reintentar.',
  ready: 'Datos disponibles.',
};
const CERTAINTY_TONE = (stars) => (stars >= 3 ? 'var(--brand)' : stars === 2 ? 'var(--rung)' : 'var(--line)');
const positionOf = (v) => `chr${v.contig}:${v.position}`;
const conditionsOf = (variants) => [...new Set(variants.flatMap((v) => v.conditions ?? []))].join(', ');

// One gene, all its variants; the first is the best ranked and speaks for the row.
const GeneRow = ({ variants, question, idPrefix, open, onToggle }) => {
  const [first] = variants;
  const two = variants.some((v) => v.zygosity === 'homocigoto');
  const stars = Math.max(...variants.map((v) => v.review_stars ?? 0));
  const gene = first.gene || 'Gen no informado';
  const detailId = `${idPrefix}-${first.variant_id}`;
  return (
    <div className={`row${open ? ' is-open' : ''}`}>
      <button type="button" className="row__head" aria-expanded={open} aria-controls={open ? detailId : undefined}
        onClick={() => onToggle(first.variant_id)}>
        <span>
          <span className="row__gene">{gene}</span>
          <span className="row__cond">{conditionsOf(variants) || 'Condición no informada'}</span>
        </span>
        <span className="copies" role="img"
          aria-label={two ? 'Las dos copias del gen tienen la variante' : 'Una de tus dos copias tiene la variante'}>
          <i className="is-var" /><i className={two ? 'is-var' : undefined} />
          <span aria-hidden="true">{two ? 'Dos copias' : 'Una copia'}</span>
        </span>
        <ChevronDown size={18} className="chev" aria-hidden="true" />
      </button>
      {open && (
        <div className="detail" id={detailId}>
          <p className="detail__say">{consequence({ ...first, zygosity: two ? 'homocigoto' : first.zygosity }, question)}</p>
          <dl className="facts">
            <div>
              <dt>Cómo se hereda</dt>
              <dd><b>{MOI_TEXT[first.inheritance] || 'Aún no curada'}</b>
                {MOI_PLAIN[first.inheritance] || 'Todavía no sabemos con certeza cómo se hereda este gen.'}</dd>
            </div>
            <div>
              <dt>Tus copias</dt>
              <dd><b>{two ? 'Las dos' : 'Una de dos'}</b>
                {two ? 'Las dos copias del gen tienen una variante.' : 'Una copia tiene la variante; la otra no.'}</dd>
            </div>
            <div>
              <dt>Qué tan segura es</dt>
              <dd><b className="detail__cert" style={{ '--c': CERTAINTY_TONE(stars) }}>{certainty(stars)}</b>
                {certaintyWhy(stars)}</dd>
            </div>
          </dl>
          <details className="techbox">
            <summary>
              Datos técnicos para tu especialista
              {variants.length > 1 && ` (${variants.length} variantes en ${gene})`}
            </summary>
            {variants.map((variant) => (
              <dl className="tech" key={variant.variant_id}>
                <dt>Variante</dt><dd>{variant.hgvs || 'No informada'}</dd>
                <dt>Clasificación</dt>
                <dd>{significanceOf(variant.clinical_significance)}, {variant.review_stars ?? 0} de 4 estrellas en ClinVar</dd>
                <dt>ClinVar</dt>
                <dd>
                  {variant.clinvar_id
                    ? <a href={`https://www.ncbi.nlm.nih.gov/clinvar/variation/${variant.clinvar_id}/`}
                      target="_blank" rel="noreferrer">{variant.clinvar_id}</a>
                    : 'No informado'}
                </dd>
                <dt>Posición</dt><dd>{positionOf(variant)} (GRCh38)</dd>
              </dl>
            ))}
          </details>
        </div>
      )}
    </div>
  );
};

const MonoLoading = () => (
  <section className="mono-loading" role="status" aria-live="polite" aria-busy="true">
    <span className="mono-sr">{resultMessages.loading}</span>
    <div aria-hidden="true">
      <span className="mono-skel mono-skel--lede" />
      <div className="mono-skel-tabs">
        {[0, 1, 2].map((key) => (
          <span className="mono-skel-tab" key={key}><i /><b /><span /></span>
        ))}
      </div>
      <div className="list">
        {[0, 1, 2, 3].map((key) => (
          <div className="mono-skel-row" key={key}><i /><span /><b /></div>
        ))}
      </div>
    </div>
  </section>
);

const Monogenico = () => {
  const { user } = useSession();
  const navigate = useNavigate();
  const results = useLatestGenomicsResults();
  const variants = moduleRows(results, 'monogenic_risk');
  // A ready service without the module is "missing"; a module with no rows is the designed empty state.
  const status = results.status === 'ready' && !Array.isArray(results.data?.modules?.monogenic_risk)
    ? 'missing' : results.status;
  const failed = ['permission', 'error'].includes(status);
  const [chosen, setChosen] = useState(null);
  const [open, setOpen] = useState(null);
  const uid = useId();

  const groups = useMemo(() => {
    const grouped = { salud: [], transmitir: [], conversar: [] };
    variants.forEach((variant) => grouped[bucket(variant)].push(variant));
    return Object.fromEntries(Object.entries(grouped).map(([key, list]) => [key, byGene(list)]));
  }, [variants]);
  const shown = Object.keys(QUESTIONS).filter((key) => groups[key].length);
  const active = chosen && shown.includes(chosen) ? chosen : shown[0] ?? null;

  const handleLogout = async () => {
    await clearToken();
    navigate('/');
  };

  const onTabKey = (event) => {
    if (!['ArrowRight', 'ArrowLeft', 'ArrowDown', 'ArrowUp'].includes(event.key)) return;
    const tabs = [...event.currentTarget.querySelectorAll('[role="tab"]:not(:disabled)')];
    const here = tabs.indexOf(document.activeElement);
    if (here < 0) return;
    const step = /Right|Down/.test(event.key) ? 1 : -1;
    const next = tabs[(here + step + tabs.length) % tabs.length];
    next.focus();
    setChosen(next.dataset.q);
    event.preventDefault();
  };

  const genes = new Set(variants.map((v) => v.gene || v.variant_id)).size;
  const found = `${variants.length === 1 ? 'Una variante' : `${variants.length} variantes`}${
    genes < variants.length ? ` en ${genes === 1 ? 'un gen' : `${genes} genes`}` : ''}`;
  const lede = !variants.length ? (
    <>En lo que cubre tu análisis <b>no encontramos variantes patogénicas</b>.</>
  ) : groups.salud.length ? (
    <><b>{found}</b>, y no todas significan lo mismo. Toca un gen para ver qué significa y qué no.</>
  ) : (
    <><b>{found}</b>, y ninguna cambia tu salud hoy. Toca un gen para ver qué significa.</>
  );

  return (
    <div className="mono">
      <main className="mono-main-content">
        <ResultsBar user={user} onLogout={handleLogout} />
        <div className="pgx">
          <header className="mono-hero">
            <ModuleTitle className="mono-title" moduleKey="monogenic_risk" title="Gen por gen" />
            {status === 'ready' && <p className="lede">{lede}</p>}
          </header>

          {status === 'loading' && <MonoLoading />}

          {status === 'ready' && (
            <>
              <p className="mono-sr" role="status" aria-label="Estado de los resultados" aria-busy={false}>
                {resultMessages.ready}
              </p>
              {!variants.length ? (
                <section className="empty">
                  <h2>Sin variantes patogénicas en tu muestra</h2>
                  <p>Revisamos las variantes clasificadas como patogénicas en ClinVar dentro de las regiones que cubre el análisis.</p>
                  <p>No cubre todo el genoma ni todas las condiciones hereditarias. Si tienes antecedentes familiares, vale la pena conversarlo con un especialista.</p>
                </section>
              ) : (
                <>
                  <section className="ask" aria-labelledby={`${uid}-ask`}>
                    <h2 id={`${uid}-ask`}>Cada gen responde una pregunta</h2>
                    <p className="ask__intro">Depende de cómo se hereda el gen y de cuántas copias tienes alteradas. Elige una para ver sus genes.</p>
                    <div className="tabs" role="tablist" aria-label="Preguntas" onKeyDown={onTabKey}>
                      {Object.entries(QUESTIONS).map(([key, question]) => (
                        <button key={key} type="button" role="tab" id={`${uid}-tab-${key}`} data-q={key}
                          className="tab" aria-selected={active === key}
                          aria-controls={groups[key].length ? `${uid}-list-${key}` : undefined}
                          tabIndex={active === key ? 0 : -1} disabled={!groups[key].length}
                          onClick={() => setChosen(key)}>
                          <span className="tab__q">{question.q}</span>
                          <span className="tab__n">{groups[key].length}</span>
                          <span className="tab__sub">{question.sub}</span>
                        </button>
                      ))}
                    </div>
                  </section>
                  {shown.map((key) => (
                    <section key={key} className="list" role="tabpanel" id={`${uid}-list-${key}`}
                      aria-labelledby={`${uid}-tab-${key}`} data-q={key} hidden={active !== key}>
                      <div className="notmean">
                        <h3>Qué no significa</h3>
                        <p>{QUESTIONS[key].not}</p>
                      </div>
                      {groups[key].map((gene) => (
                        <GeneRow key={gene[0].variant_id} variants={gene} question={key} idPrefix={`${uid}-${key}`}
                          open={open === gene[0].variant_id} onToggle={(id) => setOpen(open === id ? null : id)} />
                      ))}
                    </section>
                  ))}
                </>
              )}
              <footer className="foot">
                <p><b>Esto no es un diagnóstico.</b> Un especialista en genética debe confirmar cualquier hallazgo con un estudio clínico.</p>
              </footer>
            </>
          )}

          {status !== 'ready' && status !== 'loading' && (
            <div className="mono-status">
              <p role={failed ? 'alert' : 'status'} aria-label="Estado de los resultados" aria-busy={false}>
                {resultMessages[status]}
              </p>
              <button type="button" className="mono-retry" aria-label="Reintentar carga de resultados" onClick={results.retry}>
                Reintentar
              </button>
            </div>
          )}
        </div>
      </main>
    </div>
  );
};

export default Monogenico;
