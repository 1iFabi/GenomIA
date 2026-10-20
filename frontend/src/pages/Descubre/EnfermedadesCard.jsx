import { useState } from "react";
import CardHelp from "./CardHelp";
import { PolygenicFigure } from "./visuals/ExampleResults";
import { VariantLetters } from "./visuals/RiskVisuals";
import useInView from "./visuals/useInView";

// Enfermedades tells its two risks one after the other: the monogenic, then the polygenic.
// Each step uses the whole card, the explanation on one side and its picture on the other.
const RISKS = [
  {
    id: "monogenico",
    title: "Riesgo monogénico",
    how: "Un solo cambio que pesa mucho.",
    help: "Lo decide un solo gen. Si heredaste una variante concreta (como BRCA2), tu riesgo sube mucho; si no la tienes, es el riesgo de siempre. Por eso el informe va variante por variante.",
    visual: <VariantLetters />,
    result: "Tienes una variante en BRCA2",
    meaning: <>Tu riesgo de cáncer de mama es <strong>más alto que el de la mayoría</strong>.</>,
  },
  {
    id: "poligenico",
    title: "Riesgo poligénico",
    how: "Muchos cambios pequeños que se suman.",
    help: "Lo deciden miles de variantes pequeñas que se suman entre sí. Ninguna pesa sola, pero juntas te dejan por encima o por debajo del promedio. Por eso se mide en una escala, no en un sí o no.",
    visual: <PolygenicFigure />,
    result: "Enfermedad coronaria",
    meaning: <>Tu riesgo es <strong>más alto que el promedio</strong>.</>,
    scale: 80,
  },
];

const LEVELS = ["Más bajo", "Promedio", "Más alto"];

/**
 * The card advances on its own while it is on screen: the active tab's bar fills, and when the fill
 * ends the next risk comes in. Pointing at the card or focusing inside it pauses the fill; choosing a
 * tab stops the tour for good. With reduced motion the fill never runs, so nothing
 * advances by itself.
 */
export default function EnfermedadesCard() {
  const [active, setActive] = useState(0);
  const [touring, setTouring] = useState(true);
  const [paused, setPaused] = useState(false);
  const [ref, inView] = useInView(0.4);

  const go = (i) => {
    setTouring(false);
    setActive(i);
  };

  return (
    <article
      ref={ref}
      className={`dcard dcard--enfermedades${touring && inView && !paused ? "" : " is-held"}`}
      aria-labelledby="dcard-enfermedades"
      onPointerEnter={() => setPaused(true)}
      onPointerLeave={() => setPaused(false)}
      onFocus={() => setPaused(true)}
      onBlur={(e) => { if (!e.currentTarget.contains(e.relatedTarget)) setPaused(false); }}
    >
      <h3 id="dcard-enfermedades" className="dcard__title">Enfermedades</h3>
      <p className="dcard__text">¿Tus genes te dan más riesgo de alguna enfermedad?</p>

      <div className="enf__stage">
        {RISKS.map((risk, i) => (
          <section
            key={risk.id}
            id={`enf-panel-${risk.id}`}
            role="tabpanel"
            aria-labelledby={`enf-tab-${risk.id}`}
            className={`risk risk--${risk.id}${i === active ? " is-active" : ""}`}
            aria-hidden={i !== active}
            inert={i === active ? undefined : ""}
          >
            <div className="risk__copy">
              <div>
                <div className="dcard__head">
                  <h4 className="risk__name">{risk.title}</h4>
                  <CardHelp label={risk.title.toLowerCase()}>{risk.help}</CardHelp>
                </div>
                <p className="risk__how">{risk.how}</p>
              </div>
              <div className="risk__result">
                <p className="risk__label">Ejemplo de resultado</p>
                <p className="risk__lead">{risk.result}</p>
                <p className="risk__meaning">{risk.meaning}</p>
                {risk.scale != null && (
                  <div className="risk__scale" role="img" aria-label="Nivel: más alto que el promedio.">
                    <span className="risk__track"><i style={{ left: `${risk.scale}%` }} /></span>
                    <span className="risk__ticks" aria-hidden="true">{LEVELS.map((l) => <span key={l}>{l}</span>)}</span>
                  </div>
                )}
              </div>
            </div>
            <div className="risk__visual">{risk.visual}</div>
          </section>
        ))}
      </div>

      {/* one control bar at the foot, like a player: the two steps, each with its progress */}
      <div className="enf__nav">
        <div className="enf__tabs" role="tablist" aria-label="Tipos de riesgo">
          {RISKS.map((risk, i) => (
            <button
              key={risk.id}
              type="button"
              role="tab"
              id={`enf-tab-${risk.id}`}
              aria-selected={i === active}
              aria-controls={`enf-panel-${risk.id}`}
              className="enf__tab"
              onClick={() => go(i)}
            >
              <span className="enf__bar" aria-hidden="true">
                {i === active && touring && (
                  <i key={active} onAnimationEnd={() => setActive((active + 1) % RISKS.length)} />
                )}
              </span>
              {risk.title.replace("Riesgo m", "M").replace("Riesgo p", "P")}
            </button>
          ))}
        </div>
      </div>
    </article>
  );
}
