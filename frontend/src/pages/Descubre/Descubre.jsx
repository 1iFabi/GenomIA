import { useRef } from "react";
import OriginsGlobe from "./visuals/OriginsGlobe";
import { DrugExample } from "./visuals/ExampleResults";
import EnfermedadesCard from "./EnfermedadesCard";
import TraitQuestions from "./visuals/TraitQuestions";
import CardHelp from "./CardHelp";
import useDescubreIntro from "./useDescubreIntro";
import "./Descubre.css";
import "../../styles/breadcrumb.css";

// row 1: Ancestría (wide) and Farmacogenética; row 2: Enfermedades, which tells its two risks in
// turn, then Rasgos.
// Each card asks its question in plain words and answers it with a sample of the report;
// the two risk terms carry a "?" that says what they mean without any genetics in it.
const FARMACOGENETICA = {
  id: "farmacogenetica",
  title: "Farmacogenética",
  text: "¿Te funcionan los medicamentos como a la mayoría?",
  visual: <DrugExample />,
};

const RASGOS = { id: "rasgos", title: "Rasgos", text: "Preguntas cotidianas que tu ADN ayuda a responder.", visual: <TraitQuestions /> };

const ModuleCard = ({ id, title, text, help, visual }) => (
  <article className={`dcard dcard--${id}`} aria-labelledby={`dcard-${id}`}>
    <div className="dcard__head">
      <h3 id={`dcard-${id}`} className="dcard__title">{title}</h3>
      {help && <CardHelp label={title.toLowerCase()}>{help}</CardHelp>}
    </div>
    <p className="dcard__text">{text}</p>
    <div className="dcard__visual">{visual}</div>
  </article>
);

const Descubre = () => {
  const sectionRef = useRef(null);
  useDescubreIntro(sectionRef);

  return (
    <section ref={sectionRef} className="descubre" data-nav-theme="light" id="learn-more" aria-labelledby="descubre-title">
      <div className="descubre-container">
        <header className="descubre-header">
          <div className="breadcrumb breadcrumb--blue">Descubre</div>
          <h2 id="descubre-title" className="descubre-title">Lo que tu ADN cuenta sobre ti</h2>
          <p className="descubre-subtitle">Transformamos tu ADN en reportes claros sobre tu origen, tu salud y tus rasgos.</p>
        </header>

        <div className="descubre-grid">
          <article className="dcard dcard--ancestria" aria-labelledby="dcard-ancestria">
            <div className="dcard__copy">
              <h3 id="dcard-ancestria" className="dcard__title">Ancestría</h3>
              <p className="dcard__text">Descubre de qué regiones del mundo viene tu ADN.</p>
            </div>
            <OriginsGlobe />
          </article>

          <ModuleCard {...FARMACOGENETICA} />

          <EnfermedadesCard />

          <ModuleCard {...RASGOS} />
        </div>
      </div>
    </section>
  );
};

export default Descubre;
