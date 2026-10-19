import { useEffect, useRef, useState } from "react";
import { geoDistance, geoOrthographic, geoPath } from "d3-geo";
import { feature, mesh } from "topojson-client";
import gsap from "gsap";
import { useReducedMotion } from "motion/react";
import useInView from "./useInView";

// the same atlas the dashboard's Ancestría globe loads
const ATLAS_URL = "https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json";
let atlas = null;
const loadAtlas = () => {
  atlas ??= fetch(ATLAS_URL)
    .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`atlas ${r.status}`))))
    .then((world) => ({
      land: feature(world, world.objects.countries),
      borders: mesh(world, world.objects.countries, (a, b) => a !== b),
    }))
    .catch((error) => { atlas = null; throw error; });
  return atlas;
};

// [name, view centre [lon, lat], markers]
const REGIONS = [
  ["América", [-64, -24], [[-70.6, -33.4], [-72, -13.5], [-68.1, -16.5]]],
  ["Europa", [2, 44], [[-3.7, 40.4], [8.9, 44.4], [2.3, 48.9]]],
  ["África", [14, 4], [[13.2, -8.8], [3.4, 6.5]]],
  ["Asia", [80, 32], [[35.5, 33.9], [77.2, 28.6], [116.4, 39.9]]],
];
const TOUR_MS = 4500;
const SPIN_DEG_PER_S = 2.5;

export default function OriginsGlobe() {
  const reduce = useReducedMotion() === true;
  const [hostRef, inView] = useInView(0.2);
  const svgRef = useRef(null);
  const landRef = useRef(null);
  const bordersRef = useRef(null);
  const marksRef = useRef(null);
  const [active, setActive] = useState(0);
  const [ready, setReady] = useState(false);
  const state = useRef({ view: { lon: REGIONS[0][1][0], lat: REGIONS[0][1][1] }, proj: geoOrthographic().clipAngle(90), geo: null, flying: false });

  // the globe is redrawn through refs, never through React state: it moves every frame of a flight
  const draw = () => {
    const { proj, view, geo } = state.current;
    if (!geo || !svgRef.current) return;
    proj.rotate([-view.lon, -view.lat]);
    const path = geoPath(proj);
    landRef.current.setAttribute("d", path(geo.land) ?? "");
    bordersRef.current.setAttribute("d", path(geo.borders) ?? "");
    for (const g of marksRef.current.children) {
      const p = JSON.parse(g.dataset.p), xy = proj(p);
      const facing = geoDistance(p, [view.lon, view.lat]) < Math.PI / 2 - 0.08;
      g.setAttribute("transform", `translate(${xy[0]},${xy[1]})`);
      g.style.display = facing ? "" : "none";
    }
  };

  // size: a large globe pushed into the card's lower right corner, bleeding past both edges, on every width
  useEffect(() => {
    const svg = svgRef.current;
    const fit = () => {
      const { width: W, height: H } = svg.getBoundingClientRect();
      if (!W || !H) return;
      svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
      const narrow = W < 560;
      state.current.proj.scale(narrow ? W * 1.0 : H * 1.05).translate(narrow ? [W * 0.72, H * 0.8] : [W * 0.8, H * 0.72]);
      draw();
    };
    const ro = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(fit);
    ro?.observe(svg);
    fit();
    return () => ro?.disconnect();
  }, []);

  useEffect(() => {
    let alive = true;
    loadAtlas().then((geo) => { if (!alive) return; state.current.geo = geo; setReady(true); draw(); }).catch(() => {});
    return () => { alive = false; };
  }, []);

  // fly to the active region, the short way round
  useEffect(() => {
    if (!ready) return undefined;
    const s = state.current, { view } = s;
    const [lon, lat] = REGIONS[active][1];
    const dLon = ((lon - view.lon + 540) % 360) - 180;
    s.flying = true;
    const flight = gsap.to(view, { lon: view.lon + dLon, lat, duration: reduce ? 0 : 1.9, ease: "power3.inOut", onUpdate: draw,
      onComplete: () => { s.flying = false; } });
    const dots = [...marksRef.current.querySelectorAll(".origins-globe__dot")];
    const pop = gsap.fromTo(dots, { attr: { r: 0 } }, { attr: { r: 3.5 }, duration: 0.5, delay: reduce ? 0 : 0.9, stagger: 0.12, ease: "expo.out" });
    draw();
    return () => { flight.kill(); s.flying = false; pop.kill(); };
  }, [active, ready, reduce]);

  // the markers' rings breathe while the card is on screen; scrolling away pauses them
  useEffect(() => {
    if (reduce || !inView || !ready) return undefined;
    const rings = [...marksRef.current.querySelectorAll(".origins-globe__ring")];
    const pulse = gsap.fromTo(rings, { attr: { r: 4 }, opacity: 0.8 },
      { attr: { r: 22 }, opacity: 0, duration: 2.6, ease: "expo.out", repeat: -1, delay: 1, stagger: 0.4 });
    return () => pulse.kill();
  }, [active, ready, reduce, inView]);

  // between flights the globe keeps turning slowly eastward, as a globe on a stand would
  useEffect(() => {
    if (reduce || !inView || !ready) return undefined;
    const spin = (_time, deltaMs) => {
      if (state.current.flying) return;
      state.current.view.lon += (deltaMs / 1000) * SPIN_DEG_PER_S;
      draw();
    };
    gsap.ticker.add(spin);
    return () => gsap.ticker.remove(spin);
  }, [reduce, inView, ready]);

  // the tour: the next region TOUR_MS after the last change, so a click on a name gets its full beat
  useEffect(() => {
    if (reduce || !inView || !ready) return undefined;
    const id = setTimeout(() => setActive((a) => (a + 1) % REGIONS.length), TOUR_MS);
    return () => clearTimeout(id);
  }, [active, reduce, inView, ready]);

  return (
    <div ref={hostRef} className="origins-globe">
      <svg ref={svgRef} className="origins-globe__map" role="img"
        aria-label={`Globo con las regiones de origen. Región destacada: ${REGIONS[active][0]}.`}>
        <path ref={landRef} className="origins-globe__land" />
        <path ref={bordersRef} className="origins-globe__borders" />
        <g ref={marksRef} key={active}>
          {REGIONS[active][2].map((p) => (
            <g key={p.join()} data-p={JSON.stringify(p)} style={{ display: "none" }}>
              <circle className="origins-globe__ring" r="4" opacity="0" />
              <circle className="origins-globe__dot" r="0" />
            </g>
          ))}
        </g>
      </svg>
      <nav className="origins-globe__regions" aria-label="Regiones de origen">
        {REGIONS.map(([name], i) => (
          <button key={name} type="button" aria-pressed={i === active} onClick={() => setActive(i)}>
            {name}
          </button>
        ))}
      </nav>
    </div>
  );
}
