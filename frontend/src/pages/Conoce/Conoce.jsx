// src/pages/Conoce/Conoce.jsx
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { animate, useInView, useMotionValue, useMotionValueEvent, useReducedMotion } from "motion/react";
import { UserRoundPlus, TestTubeDiagonal, MailCheck, MonitorCheck } from "lucide-react";
import { lengthAt, roadThrough } from "./route";
import useScrollReveal from "../../lib/useScrollReveal";
import "./Conoce.css";
import "../../styles/breadcrumb.css";

const STEPS = [
  {
    title: "Realiza tu registro en el sistema",
    description: "Aquí obtendrás tus credenciales para acceder a tus resultados.",
    Icon: UserRoundPlus,
  },
  {
    title: "Ve al laboratorio a muestrearte",
    description: "Se te tomará una pequeña muestra de saliva para recolectar tu ADN.",
    Icon: TestTubeDiagonal,
  },
  {
    title: "Espera el correo de afirmación",
    description: "Llegará un mensaje de confirmación a tu correo cuando tu test esté listo.",
    Icon: MailCheck,
  },
  {
    title: "Revisa en la web tus resultados",
    description: "Inicia sesión y revisa todo lo que tu genética tiene que decirte.",
    Icon: MonitorCheck,
  },
];
const LAST = STEPS.length - 1;

// one walk: travel a leg, rest a beat at the station, travel on. Seconds.
const LEG = 0.9;
const BEAT = 0.3;
const walkKeys = [0];
const walkTimes = [0];
for (let i = 1; i <= LAST; i++) {
  const t0 = walkTimes[walkTimes.length - 1];
  walkKeys.push(i);
  walkTimes.push(t0 + LEG);
  if (i < LAST) {
    walkKeys.push(i);
    walkTimes.push(t0 + LEG + BEAT);
  }
}
const WALK = walkTimes[walkTimes.length - 1];
const WALK_TIMES = walkTimes.map((x) => x / WALK);

// the loop, in milliseconds: walk, hold at the last station, clear the road, rest, walk again (about 8 s)
const LEAD = 900; // first walk, once the route is on screen
const HOLD = 2400;
const CLEAR = 1800; // longer than the slow reset in Conoce.css, so the sample only goes back once the road is clear
const RESTING = 1600;

// stops the loop's pending step and its walk
function halt(loop) {
  clearTimeout(loop.current.timer);
  loop.current.anim?.stop();
  loop.current.anim = null;
}

export default function Conoce() {
  const scope = useRef(null);
  useScrollReveal(scope);
  const routeRef = useRef(null);
  const roadRef = useRef(null);
  const trailRef = useRef(null);
  const capsuleRef = useRef(null);
  const geo = useRef({ stops: [0, 0, 0, 0] }); // road length at each station
  const furthest = useRef(-1); // furthest station the sample has passed in this walk; -1 = none yet
  const tracking = useRef(false); // true while the sample walks and lights stations
  const loop = useRef({ timer: null, anim: null });
  const reduce = useReducedMotion();
  const inView = useInView(routeRef, { amount: 0.5 });
  const t = useMotionValue(0); // where the sample is, in stations: 0 = first, 3 = last
  const [road, setRoad] = useState({ w: 0, h: 0, d: "" });
  const [reached, setReached] = useState(-1); // lit stations go up to this index
  const [current, setCurrent] = useState(-1);
  const [live, setLive] = useState(false); // the sample and its trail are on the road

  // the sample and the trail are written straight to the SVG; React only hears about lit and current steps
  const paint = useCallback((v) => {
    const path = roadRef.current;
    // reduced motion sets t before the road is measured: an empty path throws on getPointAtLength
    if (!path?.getPointAtLength || !path.getAttribute("d")) return;
    const { stops } = geo.current;
    const len = lengthAt(stops, v);
    const a = path.getPointAtLength(len);
    const ahead = path.getPointAtLength(Math.min(stops[LAST], len + 1));
    const behind = path.getPointAtLength(Math.max(0, len - 1));
    const angle = (Math.atan2(ahead.y - behind.y, ahead.x - behind.x) * 180) / Math.PI;
    capsuleRef.current.setAttribute("transform", `translate(${a.x} ${a.y}) rotate(${angle})`);
    trailRef.current.style.strokeDashoffset = stops[LAST] - lengthAt(stops, Math.max(0, furthest.current));
  }, []);

  // lights every station the sample has passed; the trail keeps the furthest one
  const light = (v) => {
    furthest.current = Math.max(furthest.current, v);
    setReached(Math.floor(furthest.current + 0.02));
  };

  useMotionValueEvent(t, "change", (v) => {
    paint(v);
    if (!tracking.current) return;
    light(v);
    setCurrent(Math.round(v));
  });

  // the road is drawn through the stations where the layout actually put them
  useLayoutEffect(() => {
    const route = routeRef.current;
    const measure = () => {
      const box = route.getBoundingClientRect();
      const pts = [...route.querySelectorAll(".conoce-station")].map((el) => {
        const r = el.getBoundingClientRect();
        return { x: Math.round(r.left + r.width / 2 - box.left), y: Math.round(r.top + r.height / 2 - box.top) };
      });
      setRoad({ w: Math.round(box.width), h: Math.round(box.height), d: roadThrough(pts) });
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(route);
    return () => ro.disconnect();
  }, []);

  useLayoutEffect(() => {
    const path = roadRef.current;
    if (!road.d || !path.getTotalLength) return;
    // road length at each station: the road cut short at that station, measured
    const parts = road.d.split(" C ");
    const probe = document.createElementNS("http://www.w3.org/2000/svg", "path");
    const stops = [0];
    for (let k = 1; k < parts.length; k++) {
      probe.setAttribute("d", parts.slice(0, k + 1).join(" C "));
      stops.push(probe.getTotalLength());
    }
    geo.current = { stops };
    trailRef.current.style.strokeDasharray = stops[LAST];
    paint(t.get());
  }, [road, paint, t]);

  // reduced motion: no loop, the route is complete and still
  useEffect(() => {
    if (!reduce) return;
    furthest.current = LAST;
    setLive(true);
    setReached(LAST);
    setCurrent(LAST);
    t.set(LAST);
  }, [reduce, t]);

  // the loop: walk, hold at the last station, clear, rest, walk again. It runs only while the route is on screen
  useEffect(() => {
    if (reduce || !inView) return undefined;
    const later = (ms, fn) => {
      loop.current.timer = setTimeout(fn, ms);
    };
    const walk = () => {
      tracking.current = true;
      setLive(true);
      loop.current.anim = animate(t, walkKeys, {
        duration: WALK,
        times: WALK_TIMES,
        ease: "easeInOut",
        onComplete: () => {
          loop.current.anim = null;
          later(HOLD, clear);
        },
      });
    };
    const clear = () => {
      tracking.current = false;
      furthest.current = -1;
      setLive(false);
      setReached(-1);
      setCurrent(-1);
      later(CLEAR, () => {
        t.set(0); // the road is empty now, so moving the sample back is not seen
        later(RESTING, walk);
      });
    };
    // back on screen after a walk was cut short: clear the road first; otherwise start the first walk
    if (furthest.current < 0) later(LEAD, walk);
    else clear();
    return () => halt(loop);
  }, [reduce, inView, t]);

  return (
    <section id="conoce" ref={scope} className="conoce-section" data-nav-theme="brand" aria-labelledby="conoce-title">
      <div className="conoce-container">
        <header className="conoce-header">
          <div className="breadcrumb breadcrumb--white" data-reveal>Conoce</div>
          <h2 id="conoce-title" className="conoce-title" data-reveal>¿Cómo funciona el mapeo?</h2>
          <p className="conoce-subtitle" data-reveal>
            Si quieres realizar un muestreo de tu ADN para conocer tu ancestría y la genómica de las
            enfermedades, rasgos y todo lo que te hace único, sigue lo siguiente:
          </p>
        </header>

        {/* Conoce measures its stations to draw the road: the route enters whole, never step by step */}
        <div className="conoce-route" ref={routeRef} data-reveal>
          <svg
            className="conoce-road"
            data-live={live}
            width={road.w}
            height={road.h}
            viewBox={`0 0 ${road.w || 1} ${road.h || 1}`}
            aria-hidden="true"
            focusable="false"
          >
            <path ref={roadRef} d={road.d} className="conoce-road__base" />
            <path ref={trailRef} d={road.d} className="conoce-road__trail" />
            {/* the sample: a two-tone capsule that travels the road and slips under each station */}
            <g ref={capsuleRef} className="conoce-capsule">
              <rect x="-16" y="-7.5" width="32" height="15" rx="7.5" fill="#f5fbff" />
              <path d="M0 -7.5 H-8.5 A7.5 7.5 0 0 0 -8.5 7.5 H0 Z" fill="#5cc8f5" />
            </g>
          </svg>

          <ol className="conoce-steps">
            {STEPS.map((step, i) => (
              <li
                key={step.title}
                className="conoce-step"
                data-lit={i <= reached || undefined}
                data-current={i === current || undefined}
              >
                <span className="conoce-station">
                  <step.Icon aria-hidden="true" strokeWidth={1.6} />
                  <span className="conoce-station__num" aria-hidden="true">{i + 1}</span>
                </span>
                <div className="conoce-step__copy">
                  <h3 className="conoce-step__title">{step.title}</h3>
                  <p className="conoce-step__text">{step.description}</p>
                </div>
              </li>
            ))}
          </ol>
        </div>
      </div>
    </section>
  );
}
