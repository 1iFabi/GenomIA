import React, { useState } from 'react';
import './GlossaryCarousel.css';

/**
 * Shared glossary carousel. Renders the `.card-pro .glossary-pro` markup and a
 * `terms` prop drives the terms/dots. Used by Enfermedades and Rasgos.
 */
const GlossaryCarousel = ({ terms = [] }) => {
  const [current, setCurrent] = useState(0);
  const prev = () => setCurrent((c) => (c - 1 + terms.length) % terms.length);
  const next = () => setCurrent((c) => (c + 1) % terms.length);

  if (!terms.length) return null;

  return (
    <div className="card-pro card-small-pro glossary-pro">
      <div className="glossary-pro__content">
        <span className="glossary-pro__badge">GLOSARIO</span>
        <div className="glossary-pro__title">{terms[current].term}</div>
        <p className="glossary-pro__description">{terms[current].description}</p>
      </div>
      <div className="glossary-pro__controls">
        <button className="glossary-pro__arrow" onClick={prev} aria-label="Anterior">
          ‹
        </button>
        <div className="glossary-pro__dots">
          {terms.map((_, i) => (
            <button
              key={i}
              className={`glossary-pro__dot ${i === current ? 'active' : ''}`}
              onClick={() => setCurrent(i)}
              aria-label={`Término ${i + 1}`}
            />
          ))}
        </div>
        <button className="glossary-pro__arrow" onClick={next} aria-label="Siguiente">
          ›
        </button>
      </div>
    </div>
  );
};

export default GlossaryCarousel;
