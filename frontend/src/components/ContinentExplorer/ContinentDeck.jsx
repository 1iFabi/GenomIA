import React, { useEffect, useRef } from 'react';
import { ChevronLeft } from 'lucide-react';
import CountryInfoPanel from '../CountryInfoPanel/CountryInfoPanel';
import './ContinentDeck.css';

const percent = (proportion) => `${(proportion * 100).toFixed(1)}%`;
const countries = (n) => `${n} ${n === 1 ? 'país' : 'países'}`;

// The phone's way through the globe, with what the desktop panel shows: one card per continent, swiped
// sideways. The card in the middle turns the globe to its continent; a country opens its detail in place.
const ContinentDeck = ({
  continents, shapes, groups, active, selectedRow, selectedRank, cohort,
  onPick, onOpenCountry, onBack, onRequestCohort,
}) => {
  const deck = useRef(null);
  const steering = useRef(null);
  const at = continents.findIndex((continent) => continent.key === active);
  const step = () => {
    const [first, second] = deck.current?.children || [];
    return second ? second.offsetLeft - first.offsetLeft : first?.offsetWidth || 0;
  };

  const onScroll = () => {
    const el = deck.current, w = step();
    if (!el || !w) return;
    if (steering.current) {
      clearTimeout(steering.current);
      steering.current = setTimeout(() => { steering.current = null; }, 140);
      return;
    }
    const i = Math.max(0, Math.min(continents.length - 1, Math.round(el.scrollLeft / w)));
    if (i !== at) onPick(continents[i].key);
  };

  useEffect(() => {
    const el = deck.current, w = step();
    if (!el || !w || at < 0 || Math.abs(el.scrollLeft - at * w) <= w / 2) return;
    clearTimeout(steering.current);
    steering.current = setTimeout(() => { steering.current = null; }, 600);
    const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    el.scrollTo({ left: at * w, behavior: reduce ? 'auto' : 'smooth' });
  }, [at, selectedRow]);

  useEffect(() => () => clearTimeout(steering.current), []);

  if (selectedRow) {
    const continent = continents.find((item) => item.key === active);
    return (
      <section className="cdeck-detail" aria-label={`Detalle de ${selectedRow.country}`}>
        <button type="button" className="cdeck-detail__back" onClick={onBack}>
          <ChevronLeft size={18} aria-hidden="true" />
          {continent?.label || 'Continentes'}
        </button>
        <CountryInfoPanel
          key={selectedRow.population}
          country={selectedRow}
          group={groups.find((group) => group.code === selectedRow.group)}
          rank={selectedRank}
          cohort={cohort}
          onRequestCohort={onRequestCohort}
        />
      </section>
    );
  }

  return (
    <ul className="cdeck" ref={deck} onScroll={onScroll} aria-label="Tus orígenes por continente">
      {continents.map((continent, i) => {
        const shape = shapes[continent.key];
        return (
          <li key={continent.key} className="cdeck__card" aria-current={i === at ? 'true' : undefined}>
            <div className="cdeck__head">
              <h2 className="cdeck__name">{continent.label}</h2>
              <span className="cdeck__count">{countries(continent.rows.length)}</span>
              {shape && (
                <svg className="cdeck__shape" viewBox={shape.viewBox} preserveAspectRatio="xMidYMid meet" aria-hidden="true">
                  <path className="cdeck__shape-land" d={shape.land} />
                  <path className="cdeck__shape-ancestry" d={shape.ancestry} />
                </svg>
              )}
            </div>
            <p className="cdeck__share">
              {percent(continent.proportion)}
              <span>de tu genoma</span>
            </p>
            <ul className="cdeck__rows">
              {continent.rows.map((row) => (
                <li key={row.population}>
                  <button
                    type="button"
                    style={{ '--share': `${(row.proportion / continent.proportion) * 100}%` }}
                    aria-label={`${row.country}, población ${row.label}: ${percent(row.proportion)} de tu genoma`}
                    onClick={() => onOpenCountry(row)}
                  >
                    <img
                      className="cdeck__flag"
                      src={`https://flagcdn.com/w40/${row.country_code.toLowerCase()}.png`}
                      srcSet={`https://flagcdn.com/w80/${row.country_code.toLowerCase()}.png 2x`}
                      alt=""
                      width="24"
                      height="17"
                    />
                    <span className="cdeck__country">
                      {row.country}
                      <span>{row.label}</span>
                    </span>
                    <span className="cdeck__value">{percent(row.proportion)}</span>
                    <span className="cdeck__bar" aria-hidden="true" />
                  </button>
                </li>
              ))}
            </ul>
          </li>
        );
      })}
    </ul>
  );
};

export default ContinentDeck;
