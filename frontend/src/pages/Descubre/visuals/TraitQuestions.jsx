import { useState } from "react";
import { Coffee, Milk, Sprout, SunMoon } from "lucide-react";

// everyday questions, each with the icon of what it asks about and the gene the report reads to answer it
const TRAITS = [
  { q: "¿El café te desvela?", gene: "CYP1A2", icon: <Coffee size={16} aria-hidden="true" />, a: "Algunas variantes de CYP1A2 hacen que tu cuerpo elimine la cafeína más lento." },
  { q: "¿Sientes amargo el brócoli?", gene: "TAS2R38", icon: <Sprout size={16} aria-hidden="true" />, a: "TAS2R38 es un receptor del gusto: algunas versiones perciben más el amargor." },
  { q: "¿Toleras la lactosa?", gene: "LCT", icon: <Milk size={16} aria-hidden="true" />, a: "Una variante cerca de LCT mantiene activa la lactasa en la adultez." },
  { q: "¿Madrugador o nocturno?", gene: "PER3", icon: <SunMoon size={16} aria-hidden="true" />, a: "Genes del reloj interno, como PER3, se asocian a tu horario preferido." },
];

export default function TraitQuestions() {
  const [open, setOpen] = useState(0);
  return (
    <ul className="traits">
      {TRAITS.map(({ q, gene, icon, a }, i) => (
        <li key={gene} className={i === open ? "traits__item traits__item--open" : "traits__item"}>
          <button type="button" className="traits__q" aria-expanded={i === open} aria-controls={`trait-${gene}`}
            onPointerEnter={() => setOpen(i)} onFocus={() => setOpen(i)} onClick={() => setOpen(i)}>
            <span className="traits__ask">
              {icon}
              <span>{q}</span>
            </span>
            <span className="traits__gene">{gene}</span>
          </button>
          <div id={`trait-${gene}`} className="traits__a"><p><span>{a}</span></p></div>
        </li>
      ))}
    </ul>
  );
}
