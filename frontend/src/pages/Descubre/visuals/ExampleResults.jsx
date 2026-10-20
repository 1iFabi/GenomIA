import { Riffle, Terrain } from "@lucasmarkes/hairline/react";

/**
 * The polygenic reading drawn by the hairline system: a field of pillars that rise together, many
 * small variants that add up. It rests still and answers the pointer while it is on it.
 */
export function PolygenicFigure() {
  return <Terrain intensity={0.85} label="Un campo de pilares que suben juntos: muchas variantes pequeñas que se suman." />;
}

/**
 * A sample of what the report says for Farmacogenética, set as type (no box, no badge), with the
 * figure beside the title.
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
