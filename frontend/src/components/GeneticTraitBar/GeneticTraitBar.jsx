import React, { useEffect, useState } from "react";
import { ChevronDown } from "lucide-react";
import NalaTipButton from "../Nala/NalaTipButton";
import { formatFrequency } from "../../lib/utils";
import "./GeneticTraitBar.css";

const GeneticTraitBar = ({
  title,
  rsid,
  genotype,
  percentage,
  impactLabel,
  impactColor,
  details = {},
  freqChile,
  explanation,
  delay = 0,
  intensityLevel,
}) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const [animate, setAnimate] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => setAnimate(true), delay);
    return () => clearTimeout(timer);
  }, [delay]);

  const intensity =
    typeof intensityLevel === 'number' ? intensityLevel : percentage >= 66 ? 3 : percentage >= 33 ? 2 : 1;
  const toggleCard = () => setIsExpanded(!isExpanded);

  const nalaQueries = {
    rsid: rsid ? `¿Qué es un rsID? (${rsid})` : "rsid",
    genotype: genotype ? `¿Qué significa el genotipo ${genotype}?` : "genotipo",
    impacto: impactLabel ? `¿Qué significa impacto ${impactLabel}?` : "impacto",
    cromopos: "¿Qué significa cromosoma y posición?",
    categoria: details.categoria ? `¿Qué significa la categoría ${details.categoria}?` : "categoría",
    magnitud:
      details.magnitud !== null && details.magnitud !== undefined
        ? `¿Qué significa magnitud ${details.magnitud}?`
        : "magnitud",
  };

  return (
    <div className={`genetic-trait-bar ${isExpanded ? "open" : ""}`}>
      <div className="genetic-trait-bar__header" onClick={toggleCard}>
        <div className="genetic-trait-bar__title-row">
          <h3 className="genetic-trait-bar__title">{title}</h3>
          <div className="genetic-trait-bar__badges">
            <span className="genetic-trait-bar__badge-rsid">{rsid || "N/A"}</span>
            {genotype && genotype !== "N/A" && (
              <span className="genetic-trait-bar__badge-genotype">{genotype}</span>
            )}
          </div>
          <span className="genetic-trait-bar__impact" style={{ color: impactColor }}>
            {Math.round(percentage)}% ({impactLabel})
          </span>
        </div>

        <div className="genetic-trait-bar__progress-bg">
          <div
            className="genetic-trait-bar__progress-fill"
            style={{
              width: animate ? `${percentage}%` : "0%",
              backgroundColor: impactColor,
            }}
          />
        </div>

        <button className="genetic-trait-bar__toggle">
          <span>Ver más información</span>
          <ChevronDown
            size={16}
            className="genetic-trait-bar__toggle-icon"
            style={{ transform: isExpanded ? "rotate(180deg)" : "rotate(0deg)" }}
          />
        </button>
      </div>

      {isExpanded && (
        <div className="genetic-trait-bar__details">
          <div className="genetic-trait-bar__section">
            <h4 className="genetic-trait-bar__section-title">DETALLE</h4>
            <div className="genetic-trait-bar__grid">
              <div className="genetic-trait-bar__grid-item">
                <div className="genetic-trait-bar__label-row">
                  <span className="genetic-trait-bar__label">RS ID</span>
                  <NalaTipButton query={nalaQueries.rsid} ariaLabel="Pregúntale a Nala sobre RS ID" />
                </div>
                <span className="genetic-trait-bar__value">{rsid || "N/A"}</span>
              </div>
              <div className="genetic-trait-bar__grid-item">
                <div className="genetic-trait-bar__label-row">
                  <span className="genetic-trait-bar__label">Genotipo</span>
                  <NalaTipButton query={nalaQueries.genotype} ariaLabel="Pregúntale a Nala sobre genotipo" />
                </div>
                <span className="genetic-trait-bar__value">{genotype || "NA"}</span>
              </div>
              <div className="genetic-trait-bar__grid-item">
                <div className="genetic-trait-bar__label-row">
                  <span className="genetic-trait-bar__label">Impacto</span>
                  <NalaTipButton query={nalaQueries.impacto} ariaLabel="Pregúntale a Nala sobre impacto" />
                </div>
                <span className="genetic-trait-bar__value" style={{ color: impactColor }}>
                  {impactLabel}
                </span>
              </div>
              <div className="genetic-trait-bar__grid-item">
                <div className="genetic-trait-bar__label-row">
                  <span className="genetic-trait-bar__label">Cromosoma / Posición</span>
                  <NalaTipButton
                    query={nalaQueries.cromopos}
                    ariaLabel="Pregúntale a Nala sobre cromosoma y posición"
                  />
                </div>
                <span className="genetic-trait-bar__value">
                  {details.cromosoma || "NA"} {details.posicion ? `/ ${details.posicion}` : ""}
                </span>
              </div>
              <div className="genetic-trait-bar__grid-item">
                <div className="genetic-trait-bar__label-row">
                  <span className="genetic-trait-bar__label">Categoría</span>
                  <NalaTipButton
                    query={nalaQueries.categoria}
                    ariaLabel="Pregúntale a Nala sobre categoría"
                  />
                </div>
                <span className="genetic-trait-bar__value">{details.categoria || "Sin categoría"}</span>
              </div>
              <div className="genetic-trait-bar__grid-item">
                <div className="genetic-trait-bar__label-row">
                  <span className="genetic-trait-bar__label">Magnitud</span>
                  <NalaTipButton query={nalaQueries.magnitud} ariaLabel="Pregúntale a Nala sobre magnitud" />
                </div>
                <span className="genetic-trait-bar__value">
                  {details.magnitud !== null && details.magnitud !== undefined ? details.magnitud : "N/A"}
                </span>
              </div>
              <div className="genetic-trait-bar__grid-item">
                <div className="genetic-trait-bar__label-row">
                  <span className="genetic-trait-bar__label">Frecuencia Chile</span>
                </div>
                <span className="genetic-trait-bar__value">{formatFrequency(freqChile)}</span>
                <span className="genetic-trait-bar__note">Frecuencia estimada en poblacion chilena.</span>
              </div>
            </div>
          </div>

          <div className="genetic-trait-bar__section">
            <h4 className="genetic-trait-bar__section-title">INTERPRETACIÓN</h4>
            <div className="genetic-trait-bar__interpretation">
              <span className="genetic-trait-bar__label">Intensidad estimada</span>
              <div className="genetic-trait-bar__intensity-dots">
                {[1, 2, 3].map((level) => (
                  <div
                    key={level}
                    className="genetic-trait-bar__dot"
                    style={{
                      background: intensity >= level ? impactColor : "#e2e8f0",
                      boxShadow: intensity >= level ? "0 2px 6px rgba(0,0,0,0.15)" : "none",
                    }}
                  />
                ))}
              </div>
            </div>
          </div>

          {explanation && (
            <div>
              <h4 className="genetic-trait-bar__section-title">EXPLICACIÓN</h4>
              <p className="genetic-trait-bar__description">{explanation}</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default GeneticTraitBar;
