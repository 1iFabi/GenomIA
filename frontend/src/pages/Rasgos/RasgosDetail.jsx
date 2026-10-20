import React, { useEffect, useLayoutEffect, useRef, useState } from 'react';
import NumberFlow from '@number-flow/react';
import { AnimatePresence, motion as Motion, useReducedMotion } from 'motion/react';
import { ArrowLeft } from 'lucide-react';
import gsap from 'gsap';
import { SplitText } from 'gsap/SplitText';
import { useGSAP } from '@gsap/react';
import { prefersStill } from '../../lib/utils';

gsap.registerPlugin(useGSAP, SplitText);

const percent = (share) => `${Math.round(share * 100)}%`;
// The pill hints where it is going: the leading edge runs ahead, the trailing edge follows a beat
// later. Both settle critically damped: a tap carries no momentum, so nothing overshoots.
function CategoryTabs({ groups, active, colors, onSelect }) {
  const listRef = useRef(null);
  const tabRefs = useRef({});
  const reduce = useReducedMotion();
  const [edges, setEdges] = useState(null);

  useLayoutEffect(() => {
    const measure = () => {
      const tab = tabRefs.current[active];
      const list = listRef.current;
      if (!tab || !list) return;
      const left = tab.offsetLeft;
      const right = list.scrollWidth - (tab.offsetLeft + tab.offsetWidth);
      setEdges((prev) => ({ left, right, forward: !prev || left >= prev.left }));
    };
    measure();
    // on a narrow row the chosen tab slides to the middle, so its neighbours stay in reach of the thumb
    const tab = tabRefs.current[active];
    const list = listRef.current;
    if (tab && list && list.scrollWidth > list.clientWidth) {
      list.scrollTo({ left: tab.offsetLeft - (list.clientWidth - tab.offsetWidth) / 2, behavior: reduce ? 'auto' : 'smooth' });
    }
    window.addEventListener('resize', measure);
    return () => window.removeEventListener('resize', measure);
  }, [active, groups.length, reduce]);

  const lead = { type: 'spring', bounce: 0, duration: 0.32 };
  const trail = { type: 'spring', bounce: 0, duration: 0.46 };
  const transition = reduce ? { duration: 0 }
    : edges?.forward ? { right: lead, left: trail } : { left: lead, right: trail };

  return (
    <div className="rasgos-tabs" ref={listRef} role="group" aria-label="Categorías de rasgos">
      {edges && (
        <Motion.span
          className="rasgos-tabs__indicator"
          aria-hidden="true"
          initial={false}
          animate={{ left: edges.left, right: edges.right }}
          transition={transition}
          style={{ '--tab-color': colors(active) }}
        />
      )}
      {groups.map((group) => (
        <button
          key={group.name}
          ref={(node) => { tabRefs.current[group.name] = node; }}
          type="button"
          className="rasgos-tabs__tab"
          data-label={group.name}
          aria-current={group.name === active ? 'true' : undefined}
          onClick={() => onSelect(group.name)}
        >
          {group.name}
        </button>
      ))}
    </div>
  );
}

// Rolls from 0 to the share as its bar grows; static text when motion is off.
function Share({ value, delay }) {
  const [shown, setShown] = useState(() => (prefersStill() ? value : 0));
  useEffect(() => {
    if (prefersStill()) return undefined;
    const timer = window.setTimeout(() => setShown(value), delay * 1000);
    return () => window.clearTimeout(timer);
  }, [value, delay]);
  if (prefersStill()) return `${value}%`;
  return (
    <NumberFlow
      value={shown}
      suffix="%"
      transformTiming={{ duration: 900, easing: 'cubic-bezier(0.16, 1, 0.3, 1)' }}
      spinTiming={{ duration: 900, easing: 'cubic-bezier(0.16, 1, 0.3, 1)' }}
    />
  );
}

// Emphasis bar chart: one row per possible result, the client's in the category color and the
// rest in gray, so the comparison with everyone else reads at a glance.
function PopulationBars({ trait, delay }) {
  const total = trait.options.reduce((sum, option) => sum + option.frequency, 0) || 1;
  const rows = trait.options.map((option) => ({
    result: option.result,
    value: Math.round((option.frequency / total) * 100),
    mine: option.result === trait.result,
  }));
  return (
    <figure className="rasgos-bars">
      <figcaption className="rasgos-visually-hidden">{`Cómo se reparte ${trait.label} en las personas`}</figcaption>
      <ul className="rasgos-bars__list">
        {rows.map((row) => {
          const summary = `${row.value}% de las personas${row.mine ? ' · tu resultado' : ''}`;
          return (
            <li
              key={row.result}
              className={`rasgos-bars__row${row.mine ? ' is-mine' : ''}`}
              tabIndex={0}
              aria-label={`${row.result}: ${summary}`}
            >
              <span className="rasgos-bars__label" aria-hidden="true">
                {row.result}
                {row.mine && <span className="rasgos-bars__you">Tú</span>}
              </span>
              <span className="rasgos-bars__track" aria-hidden="true">
                <span className="rasgos-bars__fill" style={{ width: `${row.value}%` }} />
                <span className="rasgos-bars__tip" style={{ left: `${row.value}%` }}>{summary}</span>
              </span>
              <span className="rasgos-bars__value" aria-hidden="true">
                <Share value={row.value} delay={delay} />
              </span>
            </li>
          );
        })}
      </ul>
    </figure>
  );
}

// The gene's name carries what it does: hover, focus or tap opens it, Escape closes it.
function GeneTip({ trait }) {
  if (!trait.description) return <strong>{trait.gene}</strong>;
  const id = `gene-tip-${trait.trait}`;
  return (
    <span className="rasgos-gene-tip">
      <button type="button" className="rasgos-gene-tip__name" aria-describedby={id}
        onKeyDown={(event) => { if (event.key === 'Escape') event.currentTarget.blur(); }}>
        {trait.gene}
      </button>
      <span role="tooltip" id={id} className="rasgos-gene-tip__bubble">
        <b>Qué hace {trait.gene}</b>
        {trait.description}
      </span>
    </span>
  );
}

function TraitRow({ trait, delay }) {
  const options = Array.isArray(trait.options) ? trait.options : [];
  const mine = options.find((option) => option.result === trait.result);
  const total = options.reduce((sum, option) => sum + option.frequency, 0) || 1;
  return (
    <article className="rasgos-trait" aria-labelledby={`trait-${trait.trait}`}>
      <div className="rasgos-trait__head">
        <h3 className="rasgos-trait__title" id={`trait-${trait.trait}`}>{trait.label}</h3>
        {(trait.gene || trait.rsid) && (
          <p className="rasgos-trait__gene">
            {trait.gene && <>Gen <GeneTip trait={trait} /></>}
            {trait.gene && trait.rsid && ' · '}
            {trait.rsid}
          </p>
        )}
      </div>
      <div className="rasgos-trait__score">
        <p className="rasgos-trait__result">
          <strong>{trait.result}</strong>
          {mine && <span>Como el {percent(mine.frequency / total)} de las personas</span>}
        </p>
        {options.length > 1 && <PopulationBars trait={{ ...trait, options }} delay={delay} />}
      </div>
      {trait.explanation && <p className="rasgos-trait__explanation">{trait.explanation}</p>}
      {trait.description && !trait.gene && (
        <p className="rasgos-trait__about">
          <span>Sobre este rasgo</span>
          {trait.description}
        </p>
      )}
    </article>
  );
}

// Opening from the overview gets the full authored moment; moving between tabs only lets the
// traits settle and the bars regrow, so a quick run along the row never waits on a title.
const timing = (intro) => {
  const trait = intro ? (index) => 0.25 + index * 0.12 : (index) => 0.08 + index * 0.05;
  // Shares start rolling exactly when their bars start growing.
  return { trait, bar: (index) => trait(index) + 0.15 };
};

function CategoryBody({ category, description, intro }) {
  const scope = useRef(null);
  const [{ trait: traitDelay, bar: barDelay }] = useState(() => timing(intro));

  useGSAP(() => {
    if (prefersStill()) return undefined;
    if (!intro) {
      const tl = gsap.timeline({ defaults: { ease: 'expo.out' } });
      gsap.utils.toArray('.rasgos-trait', scope.current).forEach((trait, index) => {
        tl.from(trait, { autoAlpha: 0, y: 10, duration: 0.5 }, traitDelay(index));
        const fills = trait.querySelectorAll('.rasgos-bars__fill');
        if (fills.length) tl.from(fills, { scaleX: 0, transformOrigin: 'left center', duration: 0.8, stagger: 0.06 }, barDelay(index));
      });
      return undefined;
    }
    const title = new SplitText('.rasgos-detail__title', { type: 'words', mask: 'words' });
    const tl = gsap.timeline({ defaults: { ease: 'expo.out' } });
    tl.from(title.words, { yPercent: 110, duration: 0.8, stagger: 0.07 })
      .from('.rasgos-detail__rule', { scaleX: 0, transformOrigin: 'left center', duration: 0.7 }, '-=0.55')
      .from('.rasgos-detail__desc, .rasgos-detail__count', { autoAlpha: 0, y: 10, duration: 0.6, stagger: 0.06 }, '-=0.5');

    gsap.utils.toArray('.rasgos-trait', scope.current).forEach((trait, index) => {
      tl.from(trait, { autoAlpha: 0, y: 18, duration: 0.7 }, traitDelay(index));
      const fills = trait.querySelectorAll('.rasgos-bars__fill');
      if (fills.length) {
        tl.from(fills, { scaleX: 0, transformOrigin: 'left center', duration: 0.9, stagger: 0.08 }, barDelay(index));
      }
    });
    return () => title.revert();
  }, { scope });

  return (
    <div className="rasgos-detail__body" ref={scope}>
      <header className="rasgos-detail__aside">
        <h2 className="rasgos-detail__title" id="traits-title">{category.name}</h2>
        <span className="rasgos-detail__rule" aria-hidden="true" />
        {description && <p className="rasgos-detail__desc">{description}</p>}
        <p className="rasgos-detail__count">
          {category.traits.length} {category.traits.length === 1 ? 'rasgo' : 'rasgos'}
        </p>
      </header>
      <div className="rasgos-detail__traits">
        {category.traits.map((trait, index) => (
          <TraitRow key={trait.trait} trait={trait} delay={barDelay(index)} />
        ))}
      </div>
    </div>
  );
}

// Categories sit side by side in the tab row: the next one drifts in from the side it lives on
// while the one you leave drifts out the other way, both in the same place at once, so there is
// never an empty gap and a new tap simply retargets. Reduced motion keeps only the crossfade.
const slide = {
  enter: ({ dir, reduce }) => ({ opacity: 0, x: reduce ? 0 : dir * 24 }),
  center: { opacity: 1, x: 0 },
  exit: ({ dir, reduce }) => ({
    opacity: 0,
    x: reduce ? 0 : dir * -24,
    pointerEvents: 'none',
    // the old words clear quickly so the two never read on top of each other
    transition: { default: { type: 'spring', bounce: 0, duration: 0.3 }, opacity: { duration: 0.12, ease: 'easeOut' } },
  }),
};

export default function RasgosDetail({ groups, category, colors, descriptions, onSelect, onBack }) {
  const reduce = useReducedMotion();
  const index = groups.findIndex((group) => group.name === category.name);
  const previous = useRef(index);
  const dir = index >= previous.current ? 1 : -1;
  useEffect(() => { previous.current = index; }, [index]);
  // only the category opened from the overview plays the full entrance
  const mounted = useRef(false);
  useEffect(() => { mounted.current = true; }, []);

  return (
    <section className="rasgos-detail" aria-labelledby="traits-title" style={{ '--cat-color': colors(category.name) }}>
      <div className="rasgos-detail__bar">
        <button type="button" className="rasgos-detail__back" onClick={onBack}>
          <ArrowLeft size={16} aria-hidden="true" /> Todas las categorías
        </button>
        <CategoryTabs groups={groups} active={category.name} colors={colors} onSelect={onSelect} />
      </div>
      <div className="rasgos-detail__stage">
      <AnimatePresence initial={false} custom={{ dir, reduce }}>
        <Motion.div
          key={category.name}
          custom={{ dir, reduce }}
          variants={slide}
          initial="enter"
          animate="center"
          exit="exit"
          transition={{ type: 'spring', bounce: 0, duration: 0.4 }}
        >
          <CategoryBody category={category} description={descriptions[category.name]} intro={!mounted.current} />
        </Motion.div>
      </AnimatePresence>
      </div>
    </section>
  );
}
