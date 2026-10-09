import React, { useRef } from 'react';
import gsap from 'gsap';
import { Flip } from 'gsap/Flip';
import { useGSAP } from '@gsap/react';
import { ChevronRight } from 'lucide-react';
import CountryInfoPanel from '../CountryInfoPanel/CountryInfoPanel';
import { SkeletonBlock } from '../DashboardSkeleton/DashboardSkeleton';
import './ContinentExplorer.css';

gsap.registerPlugin(useGSAP, Flip);

const percent = (proportion) => `${(proportion * 100).toFixed(1)}%`;
const reducedMotion = () => Boolean(window.matchMedia?.('(prefers-reduced-motion: reduce)').matches);

// Flip moves the HTML wrapper, never the svg itself, so it measures boxes instead of SVG transforms.
const Shape = ({ shape, continentKey, className }) => (
  <span
    className={`cx-shape${shape ? '' : ' cx-shape--pending'} ${className}`}
    aria-hidden="true"
    data-flip-id={`shape-${continentKey}`}
  >
    {shape && (
      <svg viewBox={shape.viewBox} preserveAspectRatio="xMidYMid meet">
        <path className="cx-shape__context" d={shape.context} />
        <path className="cx-shape__land" d={shape.land} />
        <path className="cx-shape__ancestry" d={shape.ancestry} />
      </svg>
    )}
  </span>
);

const ContinentExplorer = ({
  status, continents, shapes, groups, activeContinent, selectedRow, selectedRank,
  onOpenContinent, onOpenCountry, onGoToWorld, onHoverContinent, onHoverCountry, cohort, onRequestCohort,
}) => {
  const rootRef = useRef(null);
  const flipState = useRef(null);
  const continent = continents.find((item) => item.key === activeContinent) || null;
  const depth = selectedRow ? 2 : continent ? 1 : 0;
  const previousDepth = useRef(depth);
  const viewKey = `${depth}:${activeContinent}:${selectedRow?.country_code}`;

  // The continent's own silhouette travels between the list and the header (Flip), so the step reads as one motion.
  const captureShapes = () => {
    if (rootRef.current && !reducedMotion()) {
      flipState.current = Flip.getState(rootRef.current.querySelectorAll('[data-flip-id]'));
    }
  };

  useGSAP(() => {
    const forward = depth >= previousDepth.current;
    previousDepth.current = depth;
    const state = flipState.current;
    flipState.current = null;
    if (reducedMotion() || !rootRef.current) return;
    if (state) {
      Flip.from(state, {
        targets: rootRef.current.querySelectorAll('[data-flip-id]'), duration: 0.6, ease: 'expo.out', scale: true,
      });
    }
    gsap.from(rootRef.current.querySelectorAll('[data-cx-in]'), {
      x: forward ? 20 : -20, autoAlpha: 0, duration: 0.45, ease: 'expo.out', stagger: 0.045,
    });
  }, { scope: rootRef, dependencies: [viewKey] });

  if (status === 'loading') {
    return (
      <div className="cx cx--fit cx--loading" aria-hidden="true">
        <SkeletonBlock className="cx-skeleton__title" />
        <SkeletonBlock className="cx-skeleton__lede" />
        <div className="cx-continents">
          {[0, 1, 2, 3].map((index) => (
            <div key={index} className="cx-card cx-card--skeleton">
              <SkeletonBlock className="cx-card__shape cx-skeleton__shape" />
              <SkeletonBlock className="cx-skeleton__name" />
              <SkeletonBlock className="cx-skeleton__value" />
            </div>
          ))}
        </div>
      </div>
    );
  }
  if (!continents.length) {
    return <p className="cx-empty">No hay resultados disponibles para este módulo.</p>;
  }

  const open = (key) => {
    captureShapes();
    onOpenContinent(key);
  };
  const toWorld = () => {
    captureShapes();
    onGoToWorld();
  };

  return (
    <div ref={rootRef} className={`cx${depth === 0 ? ' cx--fit' : ''}`}>
      {depth > 0 && (
        <nav className="cx-crumbs" aria-label="Ruta de exploración">
          <ol>
            <li><button type="button" onClick={toWorld}>Mundo</button></li>
            <li>
              <ChevronRight size={14} aria-hidden="true" />
              {depth > 1
                ? <button type="button" onClick={() => onOpenContinent(continent.key)}>{continent.label}</button>
                : <span aria-current="page">{continent.label}</span>}
            </li>
            {depth > 1 && (
              <li>
                <ChevronRight size={14} aria-hidden="true" />
                <span aria-current="page">{selectedRow.country}</span>
              </li>
            )}
          </ol>
        </nav>
      )}

      {depth === 0 && (
        <section aria-labelledby="ancestria-global-title">
          <h2 id="ancestria-global-title" className="cx-title" data-cx-in>Tus orígenes</h2>
          <p className="cx-lede" data-cx-in>
            {continents.length} {continents.length === 1 ? 'continente' : 'continentes'} en tu genoma. Elige uno para ver sus países.
          </p>
          <ul className="cx-continents">
            {continents.map((item) => (
              <li key={item.key} data-cx-in>
                <button
                  type="button"
                  className="cx-card"
                  aria-label={`${item.label}: ${percent(item.proportion)} de tu genoma, ${item.rows.length} ${item.rows.length === 1 ? 'país' : 'países'}`}
                  onClick={() => open(item.key)}
                  onPointerEnter={() => onHoverContinent(item.key)}
                  onPointerLeave={() => onHoverContinent(null)}
                  onFocus={() => onHoverContinent(item.key)}
                  onBlur={() => onHoverContinent(null)}
                >
                  <Shape shape={shapes[item.key]} continentKey={item.key} className="cx-card__shape" />
                  <span className="cx-card__name">{item.label}</span>
                  <span className="cx-card__value">{percent(item.proportion)}</span>
                  <span className="cx-card__count">{item.rows.length} {item.rows.length === 1 ? 'país' : 'países'}</span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

      {depth === 1 && (
        <section aria-labelledby="cx-continent-title">
          <header className="cx-head">
            <Shape shape={shapes[continent.key]} continentKey={continent.key} className="cx-head__shape" />
            <div>
              <h2 id="cx-continent-title" className="cx-title" data-cx-in>{continent.label}</h2>
              <p className="cx-lede" data-cx-in>
                <strong>{percent(continent.proportion)}</strong> de tu genoma se parece a poblaciones de {continent.label}.
              </p>
            </div>
          </header>
          <ul className="cx-countries">
            {continent.rows.map((row) => (
              <li key={row.population} data-cx-in>
                <button
                  type="button"
                  className="cx-country"
                  style={{ '--share': `${(row.proportion / continent.proportion) * 100}%` }}
                  aria-label={`${row.country}, población ${row.label}: ${percent(row.proportion)} de tu genoma`}
                  onClick={() => onOpenCountry(row)}
                  onPointerEnter={() => onHoverCountry(row.country_code)}
                  onPointerLeave={() => onHoverCountry(null)}
                  onFocus={() => onHoverCountry(row.country_code)}
                  onBlur={() => onHoverCountry(null)}
                >
                  <img
                    className="cx-country__flag"
                    src={`https://flagcdn.com/w40/${row.country_code.toLowerCase()}.png`}
                    srcSet={`https://flagcdn.com/w80/${row.country_code.toLowerCase()}.png 2x`}
                    alt=""
                    width="28"
                    height="20"
                  />
                  <span className="cx-country__name">
                    {row.country}
                    <span>{row.label}</span>
                  </span>
                  <span className="cx-country__value">{percent(row.proportion)}</span>
                  <ChevronRight className="cx-country__go" size={16} aria-hidden="true" />
                  <span className="cx-country__bar" aria-hidden="true" />
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

      {depth === 2 && (
        <div data-cx-in>
          <CountryInfoPanel
            key={selectedRow.population}
            country={selectedRow}
            group={groups.find((group) => group.code === selectedRow.group)}
            rank={selectedRank}
            cohort={cohort}
            onRequestCohort={onRequestCohort}
          />
        </div>
      )}
    </div>
  );
};

export default ContinentExplorer;
