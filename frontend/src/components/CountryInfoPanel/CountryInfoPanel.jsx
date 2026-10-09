import React, { useRef, useState } from 'react';
import gsap from 'gsap';
import { useGSAP } from '@gsap/react';
import { ChevronLeft } from 'lucide-react';
import AncestorHook from '../AncestorHook/AncestorHook';
import './CountryInfoPanel.css';

gsap.registerPlugin(useGSAP);

// Reference panels come from 1000 Genomes-style populations; texts describe the population, not a nationality.
const POPULATION_NOTES = {
  MAP: {
    summary: 'Los mapuche son el pueblo originario más numeroso de Chile: en el censo de 2017, cerca de 1,7 millones de personas se identificaron como mapuche.',
    curiosity: 'Mapudungun significa «la lengua de la tierra». Muchos lugares de Chile llevan nombres en mapudungun, como Temuco o Curicó.',
  },
  AYM: {
    summary: 'El pueblo aymara habita desde hace siglos el altiplano andino, alrededor del lago Titicaca, entre Bolivia, Perú y Chile.',
    curiosity: 'Las poblaciones andinas de altura tienen adaptaciones genéticas que les ayudan a vivir con menos oxígeno disponible.',
  },
  QUE: {
    summary: 'El quechua fue la lengua administrativa del Imperio inca y hoy lo hablan millones de personas en los Andes.',
    curiosity: 'La papa fue domesticada en los Andes del sur de Perú hace entre 7.000 y 10.000 años.',
  },
  IBS: {
    summary: 'Muestra de referencia de la península ibérica. Por la colonización española, es la referencia europea más cercana a la mayoría de los genomas chilenos.',
    curiosity: 'En el genoma ibérico conviven huellas de pueblos antiguos de la península, de Roma y del norte de África.',
  },
  TSI: {
    summary: 'Muestra de referencia tomada en la Toscana, representativa del sur de Europa.',
    curiosity: 'Entre fines del siglo XIX y comienzos del XX llegaron a Chile inmigrantes italianos, muchos de ellos desde Liguria.',
  },
  GBR: {
    summary: 'Muestra de referencia de Inglaterra y Escocia, representativa del noroeste de Europa.',
    curiosity: 'En el siglo XIX, Valparaíso tuvo una de las comunidades británicas más grandes de Sudamérica, ligada al comercio marítimo.',
  },
  YRI: {
    summary: 'Los yoruba son uno de los pueblos más grandes de África occidental, con decenas de millones de personas.',
    curiosity: 'Gran parte de la ancestría africana en América proviene de África occidental, por la trata transatlántica de personas esclavizadas.',
  },
  LWK: {
    summary: 'Los luhya viven en el oeste de Kenia y hablan lenguas bantúes.',
    curiosity: 'Las expansiones bantúes, iniciadas hace unos 3.000 a 5.000 años, llevaron estas lenguas por gran parte del centro y sur de África.',
  },
  CHB: {
    summary: 'Los han son el grupo étnico más grande del mundo. Esta muestra de referencia proviene de Pekín.',
    curiosity: 'Los pueblos de Asia oriental y los pueblos originarios de América comparten ancestros que vivieron hace más de 20.000 años.',
  },
  JPT: {
    summary: 'Muestra de referencia tomada en Tokio.',
    curiosity: 'El genoma japonés actual combina ancestría de los antiguos jōmon con la de agricultores llegados desde el continente.',
  },
};

const TABS = [
  { id: 'resumen', label: 'Resumen' },
  { id: 'comparacion', label: 'Comparación' },
  { id: 'curiosidad', label: 'Curiosidad' },
];

const percent = (proportion) => `${(proportion * 100).toFixed(1)}%`;
const prefersReducedMotion = () => Boolean(window.matchMedia?.('(prefers-reduced-motion: reduce)').matches);

const Comparison = ({ country, cohort }) => {
  if (!cohort || cohort.status === 'loading') return <p className="country-info__muted">Cargando comparación…</p>;
  if (cohort.status === 'error') return <p className="country-info__muted">No fue posible cargar la comparación.</p>;
  const stats = cohort.data.populations?.[country.population];
  if (!stats) {
    return (
      <p className="country-info__muted">
        Aún no hay suficientes personas secuenciadas para comparar de forma anónima.
        La comparación aparece cuando haya al menos {cohort.data.min_cohort}.
      </p>
    );
  }
  return (
    <>
      <p className="country-info__lead">
        Tu parecido con la población {country.label} es mayor que el de{' '}
        <strong>{Math.round(stats.percentile)} de cada 100</strong> personas secuenciadas en GenomIA.
      </p>
      <dl className="country-info__figures">
        <div><dt>Tú</dt><dd>{percent(country.proportion)}</dd></div>
        <div><dt>Promedio</dt><dd>{percent(stats.mean)}</dd></div>
        <div><dt>Con esta ancestría</dt><dd>{Math.round(stats.carriers * 100)} de cada 100</dd></div>
      </dl>
      <p className="country-info__footnote">
        Comparación con {cohort.data.cohort_size} personas. Solo se usan cifras agregadas.
      </p>
    </>
  );
};

const CountryInfoPanel = ({ country, group, rank, cohort, onRequestCohort, onBack }) => {
  const [activeTab, setActiveTab] = useState('resumen');
  const rootRef = useRef(null);
  const indicatorRef = useRef(null);
  const tabRefs = useRef({});
  const note = POPULATION_NOTES[country.population];
  const groupShare = group?.proportion ? country.proportion / group.proportion : 0;

  useGSAP(() => {
    if (prefersReducedMotion()) return;
    gsap.from('[data-anim]', { y: 14, autoAlpha: 0, duration: 0.6, ease: 'expo.out', stagger: 0.06 });
  }, { scope: rootRef });

  const isFirstTab = useRef(true);
  useGSAP(() => {
    const tab = tabRefs.current[activeTab];
    if (!tab || !indicatorRef.current) return;
    const target = { x: tab.offsetLeft, width: tab.offsetWidth };
    const first = isFirstTab.current;
    isFirstTab.current = false;
    if (first || prefersReducedMotion()) {
      gsap.set(indicatorRef.current, target);
      return;
    }
    gsap.to(indicatorRef.current, { ...target, duration: 0.45, ease: 'expo.out' });
    gsap.fromTo('.country-info__tabpanel', { y: 6, autoAlpha: 0 },
      { y: 0, autoAlpha: 1, duration: 0.35, ease: 'expo.out', overwrite: true });
  }, { scope: rootRef, dependencies: [activeTab] });

  const selectTab = (id) => {
    setActiveTab(id);
    if (id === 'comparacion') onRequestCohort?.();
  };

  const onTabKeyDown = (event) => {
    const step = { ArrowRight: 1, ArrowLeft: -1 }[event.key];
    if (!step) return;
    event.preventDefault();
    const index = (TABS.findIndex((tab) => tab.id === activeTab) + step + TABS.length) % TABS.length;
    selectTab(TABS[index].id);
    tabRefs.current[TABS[index].id]?.focus();
  };

  return (
    <div ref={rootRef} className="country-info" style={{ '--anc-color': group?.color }}>
      {onBack && (
        <button type="button" className="country-info__back" onClick={onBack} data-anim>
          <ChevronLeft size={16} aria-hidden="true" />
          Volver al resumen
        </button>
      )}

      <div data-anim>
        <AncestorHook country={country} group={group} rank={rank} full />
      </div>

      <div className="country-info__tabs" role="tablist" aria-label="Detalle del país" data-anim>
        {TABS.map((tab) => (
          <button
            key={tab.id}
            ref={(node) => { tabRefs.current[tab.id] = node; }}
            type="button"
            role="tab"
            id={`country-tab-${tab.id}`}
            aria-selected={activeTab === tab.id}
            aria-controls="country-tabpanel"
            tabIndex={activeTab === tab.id ? 0 : -1}
            className="country-info__tab"
            onClick={() => selectTab(tab.id)}
            onKeyDown={onTabKeyDown}
          >
            {tab.label}
          </button>
        ))}
        <span ref={indicatorRef} className="country-info__indicator" aria-hidden="true" />
      </div>

      <div
        id="country-tabpanel"
        className="country-info__tabpanel"
        role="tabpanel"
        aria-labelledby={`country-tab-${activeTab}`}
      >
        {activeTab === 'resumen' && (
          <>
            <p className="country-info__lead">
              <strong>{percent(country.proportion)}</strong> de tu genoma se parece a la población {country.label},
              el {Math.round(groupShare * 100)}% de tu componente {group?.label.toLowerCase()}.
            </p>
            {note && <p>{note.summary}</p>}
            <p className="country-info__footnote">
              Es una estimación de parecido genético con una población de referencia, no de nacionalidad.
            </p>
          </>
        )}
        {activeTab === 'comparacion' && <Comparison country={country} cohort={cohort} />}
        {activeTab === 'curiosidad' && (
          <p>{note?.curiosity ?? 'Todavía no tenemos una curiosidad para esta población.'}</p>
        )}
      </div>
    </div>
  );
};

export default CountryInfoPanel;
