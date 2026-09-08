import React, { useState } from "react";
import { RISK_COLORS } from "../../constants/geneticRisk";
import "./SemiGauge.css";

const SemiGauge = ({ data, riskConfig = {} }) => {
  const [tooltip, setTooltip] = useState({
    visible: false,
    content: "",
    x: 0,
    y: 0,
  });

  const RISK_CONFIG = {
    bajo: { color: riskConfig.bajo?.color || RISK_COLORS.bajo, label: riskConfig.bajo?.label || "Riesgo Bajo" },
    medio: { color: riskConfig.medio?.color || RISK_COLORS.medio, label: riskConfig.medio?.label || "Riesgo Medio" },
    alto: { color: riskConfig.alto?.color || RISK_COLORS.alto, label: riskConfig.alto?.label || "Riesgo Alto" },
  };

  const total = Object.values(data).reduce((sum, count) => sum + count, 0);

  if (total === 0) {
    return (
      <div className="gauge-card">
        <div className="gauge-wrap empty">
          <p>No hay datos de biomarcadores para mostrar.</p>
        </div>
      </div>
    );
  }

  const radius = 85;
  const strokeWidth = 30;

  const circumference = Math.PI * radius;

  let cumulativeAngle = -180;

  const handleMouseMove = (e, content) => {
    setTooltip({
      visible: true,
      content,
      x: e.clientX,
      y: e.clientY,
    });
  };

  const handleMouseLeave = () => {
    setTooltip({ ...tooltip, visible: false });
  };

  const getPath = (startAngle, endAngle) => {
    const start = polarToCartesian(radius, startAngle);
    const end = polarToCartesian(radius, endAngle);
    const largeArcFlag = endAngle - startAngle <= 180 ? "0" : "1";

    return [
      "M", start.x, start.y,
      "A", radius, radius, 0, largeArcFlag, 1, end.x, end.y
    ].join(" ");
  };

  const polarToCartesian = (radius, angleInDegrees) => {
    const angleInRadians = (angleInDegrees * Math.PI) / 180.0;
    return {
      x: 100 + (radius * Math.cos(angleInRadians)),
      y: 100 + (radius * Math.sin(angleInRadians)),
    };
  };

  const RISK_ORDER = ['bajo', 'medio', 'alto'];

  const segments = RISK_ORDER.map(riskKey => {
    const count = data[riskKey] || 0;
    if (count === 0) return null;

    const percentage = (count / total);
    const angle = percentage * 180;
    const startAngle = cumulativeAngle;
    const endAngle = cumulativeAngle + angle;
    cumulativeAngle = endAngle;

    const percentageString = `${(percentage * 100).toFixed(1)}%`;
    const arcLength = (angle / 180) * circumference;

    return {
      path: getPath(startAngle, endAngle),
      color: RISK_CONFIG[riskKey].color,
      content: `${RISK_CONFIG[riskKey].label}: ${percentageString}`,
      arcLength,
    };
  }).filter(Boolean);

  return (
    <div className="gauge-card">
      <div className="gauge-wrap" aria-label={`Distribución de riesgos: ${RISK_ORDER.map(k => `${data[k] || 0} ${k}`).join(', ')}`}>
        <svg viewBox="0 0 200 105" className="gauge-svg">
          {segments.map((segment, index) => (
            <path
              key={index}
              d={segment.path}
              fill="none"
              stroke={segment.color}
              strokeWidth={strokeWidth}
              strokeDasharray={segment.arcLength}
              strokeDashoffset={segment.arcLength}
              onMouseMove={(e) => handleMouseMove(e, segment.content)}
              onMouseLeave={handleMouseLeave}
              className="gauge-segment"
              style={{ animationDelay: `${index * 0.2}s` }}
            />
          ))}
        </svg>
      </div>

      {tooltip.visible && (
        <div
          className="gauge-tooltip"
          style={{
            left: tooltip.x,
            top: tooltip.y,
          }}
        >
          {tooltip.content}
        </div>
      )}

      <div className="gauge-legend">
        {RISK_ORDER
          .filter(riskKey => data[riskKey] > 0)
          .map(riskKey => (
            <span className="legend-item" key={riskKey}>
              <span className="dot" style={{ backgroundColor: RISK_CONFIG[riskKey].color }} />
              {RISK_CONFIG[riskKey].label} ({data[riskKey]})
            </span>
        ))}
      </div>
    </div>
  );
};

export default SemiGauge;
