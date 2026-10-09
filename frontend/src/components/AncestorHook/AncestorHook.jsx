import React, { useRef } from 'react';
import gsap from 'gsap';
import { useGSAP } from '@gsap/react';
import { ancestorEquivalent } from './ancestorEquivalent';
import './AncestorHook.css';

gsap.registerPlugin(useGSAP);

// Where each 1000 Genomes-style reference population lives; geography only, no lineage claim.
const REGIONS = {
  MAP: 'del sur de Chile',
  AYM: 'del altiplano andino',
  QUE: 'de los Andes centrales',
  IBS: 'de la península ibérica',
  TSI: 'de la Toscana, Italia',
  GBR: 'de Gran Bretaña',
  YRI: 'de África occidental',
  LWK: 'de África oriental',
  CHB: 'del norte de China',
  JPT: 'de Japón',
};
const TREE_LIMIT = 5; // Beyond 32 ancestors a tree is unreadable, so the deeper ones become a grid.
const W = 176;

const percent = (proportion) => `${(proportion * 100).toFixed(1)}%`;
const reducedMotion = () => Boolean(window.matchMedia?.('(prefers-reduced-motion: reduce)').matches);

const Tree = ({ generation, lit, partial }) => {
  const rowGap = generation <= 3 ? 22 : 17;
  const height = generation * rowGap + 30;
  const rootY = height - 10;
  const node = (g, i) => ({ x: ((i + 0.5) * W) / 2 ** g, y: rootY - g * rowGap });
  const leafR = [0, 7, 6.5, 5.5, 4.2, 2.8][generation];
  const edges = [];
  for (let g = 1; g <= generation; g += 1) {
    for (let i = 0; i < 2 ** g; i += 1) {
      const a = node(g, i);
      const b = node(g - 1, Math.floor(i / 2));
      edges.push(`M${a.x},${a.y} L${b.x},${b.y}`);
    }
  }
  const lineage = (leaf) => {
    const points = [];
    for (let g = generation, i = leaf; g >= 0; g -= 1, i = Math.floor(i / 2)) points.push(node(g, i));
    return `M${points.map((p) => `${p.x},${p.y}`).join(' L')}`;
  };
  const glowing = Array.from({ length: lit + (partial ? 1 : 0) }, (_, i) => i);
  const root = node(0, 0);
  return (
    <svg className="hook-tree" viewBox={`0 0 ${W} ${height}`} width={W} height={height} aria-hidden="true">
      <path className="hook-tree__edges" d={edges.join(' ')} />
      {glowing.map((leaf) => (
        <path key={`l${leaf}`} className="hook-tree__lineage" d={lineage(leaf)} pathLength="1" data-hook-line />
      ))}
      {Array.from({ length: 2 ** generation }, (_, i) => {
        const { x, y } = node(generation, i);
        const isLit = i < lit;
        const isPartial = !isLit && partial && i === lit;
        return (
          <circle
            key={i}
            cx={x}
            cy={y}
            r={leafR}
            className={`hook-dot${isLit ? ' hook-dot--lit' : ''}${isPartial ? ' hook-dot--half' : ''}`}
            data-hook-dot={isLit || isPartial ? '' : undefined}
          />
        );
      })}
      <circle className="hook-tree__root" cx={root.x} cy={root.y} r="4" />
      <text className="hook-tree__you" x={root.x + 8} y={root.y + 3.5}>tú</text>
    </svg>
  );
};

// Too many ancestors for a tree: the crowd becomes a faint texture and yours sit lit in the middle of it.
const Grid = ({ total, lit, partial }) => {
  const cols = 16;
  const rows = total / cols;
  const gap = 10;
  const glowing = lit + (partial ? 1 : 0);
  const first = Math.floor(rows / 2) * cols + Math.floor((cols - glowing) / 2);
  const at = (i) => ({ cx: (i % cols) * gap + gap / 2, cy: Math.floor(i / cols) * gap + gap / 2 });
  return (
    <svg className="hook-tree" viewBox={`0 0 ${cols * gap} ${rows * gap}`} width={cols * gap} height={rows * gap} aria-hidden="true">
      {Array.from({ length: total }, (_, i) => (
        i >= first && i < first + glowing ? null : <circle key={i} {...at(i)} r="2.4" className="hook-crowd" />
      ))}
      {Array.from({ length: glowing }, (_, k) => {
        const isPartial = partial && k === glowing - 1;
        return (
          <g key={`g${k}`} data-hook-dot>
            <circle {...at(first + k)} r="9" className="hook-halo" />
            <circle {...at(first + k)} r="4.6" className={`hook-dot ${isPartial ? 'hook-dot--half' : 'hook-dot--lit'}`} />
          </g>
        );
      })}
    </svg>
  );
};

const AncestorHook = ({ country, group, rank, full = false }) => {
  const rootRef = useRef(null);
  const valueRef = useRef(null);
  const equivalent = ancestorEquivalent(country.proportion);

  useGSAP(() => {
    if (reducedMotion()) return;
    const counter = { value: 0 };
    const timeline = gsap.timeline({ delay: 0.15 });
    timeline.to(counter, {
      value: country.proportion,
      duration: 0.9,
      ease: 'expo.out',
      onUpdate: () => { if (valueRef.current) valueRef.current.textContent = percent(counter.value); },
    });
    timeline.fromTo('[data-hook-line]', { strokeDashoffset: 1 }, { strokeDashoffset: 0, duration: 0.6, ease: 'expo.out', stagger: 0.08 }, 0.1);
    timeline.from('[data-hook-dot]', {
      scale: 0, transformOrigin: '50% 50%', duration: 0.45, ease: 'back.out(2)', stagger: 0.07,
    }, 0.35);
  }, { scope: rootRef });

  return (
    <div ref={rootRef} className={`hook${full ? ' hook--full' : ''}`} style={{ '--anc-color': group?.color }}>
      <div className="hook__text">
        <h3 className="hook__title">Tu lado {country.label.toLowerCase()}</h3>
        {REGIONS[country.population] && <p className="hook__region">{REGIONS[country.population]}</p>}
        <p className="hook__figure">
          <span ref={valueRef} className="hook__value">{percent(country.proportion)}</span>
          <span className="hook__equiv">{equivalent.phrase}</span>
        </p>
      </div>
      <div className="hook__visual">
        {equivalent.generation <= TREE_LIMIT ? <Tree {...equivalent} /> : <Grid {...equivalent} />}
      </div>
      <p className="hook__meta">
        <img
          className="hook__flag"
          src={`https://flagcdn.com/w40/${country.country_code.toLowerCase()}.png`}
          srcSet={`https://flagcdn.com/w80/${country.country_code.toLowerCase()}.png 2x`}
          alt=""
          width="20"
          height="14"
        />
        <span className="country-info__name">{country.country}</span>
        <span> · {group?.label}{rank ? ` · tu origen n.º ${rank}` : ''}</span>
      </p>
      {full && (
        <p className="hook__note">
          Equivalencia aproximada con una población de referencia: la herencia real se reparte al azar entre tus ancestros.
        </p>
      )}
    </div>
  );
};

export default AncestorHook;
