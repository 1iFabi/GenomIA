import { Loupe, Riffle, Terrain } from "@lucasmarkes/hairline/react";
import { STAGE } from "./figureStage";

/**
 * A sample of what the report says, set as type (no box, no badge), and the figure placed per card
 * (layout: br, band, tr), so the row reads as a composition instead of three copies of one template.
 *
 * The figures rest still. Each one answers the pointer while it is on it, and when the pointer leaves
 * it settles back into its rest position.
 */
function Example({ layout, figure, children }) {
  return (
    <div className={`example example--${layout}`}>
      <div className="example__result">
        <p className="example__label">Ejemplo de resultado</p>
        {children}
      </div>
      <div className="example__figure">{figure}</div>
    </div>
  );
}

export function MonogenicExample() {
  return (
    <Example layout="br" figure={<Loupe intensity={0.55} label="Una lupa que recorre una hoja: buscar una sola variante." />}>
      <p className="example__lead">BRCA2</p>
      <p className="example__line">Cáncer de mama hereditario</p>
      <p className="example__line"><span className="example__flag">Variante probablemente patogénica</span></p>
    </Example>
  );
}

const LEVELS = ["Más bajo", "Promedio", "Más alto"];
export function PolygenicExample() {
  return (
    <Example layout="band" figure={<Terrain style={STAGE} intensity={0.85} label="Un campo de pilares que suben juntos: muchas variantes pequeñas que se suman." />}>
      <p className="example__lead">Más alto que el promedio</p>
      <p className="example__line">Enfermedad coronaria</p>
      <div className="example__scale" role="img" aria-label="Nivel: más alto que el promedio.">
        <span className="example__track"><i style={{ left: "80%" }} /></span>
        <span className="example__ticks" aria-hidden="true">{LEVELS.map((l) => <span key={l}>{l}</span>)}</span>
      </div>
    </Example>
  );
}

export function DrugExample() {
  return (
    <Example layout="tr" figure={<Riffle intensity={0.5} label="Una bandeja de fichas: cada medicamento, con su propia respuesta." />}>
      <dl className="example__rows">
        <div><dt>Clopidogrel</dt><dd className="example__flag">Podría funcionarte menos</dd></div>
        <div><dt>Omeprazol</dt><dd>Funciona como a la mayoría</dd></div>
      </dl>
      <p className="example__line example__line--muted">Los dos dependen del gen CYP2C19: tu variante explica por qué uno te funciona distinto y el otro no.</p>
    </Example>
  );
}
