import React, { useState, useMemo, useRef, useEffect } from 'react';
import { HelpCircle } from 'lucide-react';
import { getImpactLevel, getImpactColor } from '../../constants/geneticRisk';
import './SunburstChart.css';

const SunburstChart = ({ data = [] }) => {
  const [hoveredSegment, setHoveredSegment] = useState(null);
  const [activeTooltipContent, setActiveTooltipContent] = useState(null);
  const [activeTooltipPosition, setActiveTooltipPosition] = useState({ x: 0, y: 0 });
  const [tooltipStyle, setTooltipStyle] = useState({});
  const tooltipRef = useRef(null);

  useEffect(() => {
    if (activeTooltipContent && tooltipRef.current) {
      const tooltipRect = tooltipRef.current.getBoundingClientRect();
      const viewportWidth = window.innerWidth;
      const viewportHeight = window.innerHeight;
      const gap = 16;

      const fitsRight = activeTooltipPosition.x + gap + tooltipRect.width <= viewportWidth;
      const finalLeft = fitsRight
        ? activeTooltipPosition.x + gap
        : activeTooltipPosition.x - tooltipRect.width - gap;

      const desiredTop = activeTooltipPosition.y - tooltipRect.height / 2;
      const minTop = 10;
      const maxTop = viewportHeight - tooltipRect.height - 10;
      const finalTop = Math.max(minTop, Math.min(desiredTop, maxTop));

      setTooltipStyle({
        position: 'fixed',
        left: `${finalLeft}px`,
        top: `${finalTop}px`,
        visibility: 'visible',
      });
    } else {
      setTooltipStyle({ visibility: 'hidden' });
    }
  }, [activeTooltipContent, activeTooltipPosition]);
  
  const sistemasConFarmacos = useMemo(() => data.filter(item => item.drugs && item.drugs.length > 0), [data]);
  const cantidadSistemas = sistemasConFarmacos.length;

  const dataWithPercentages = useMemo(() => {
    if (cantidadSistemas === 0) return [];
    return sistemasConFarmacos.map(sistema => {
      const impactCounts = { alto: 0, medio: 0, bajo: 0 };
      (sistema.drugs || []).forEach(drug => {
        const impact = getImpactLevel(drug.magnitud);
        impactCounts[impact]++;
      });
      return {
        ...sistema,
        porcentajeTotal: (1 / cantidadSistemas) * 100,
        impactCounts,
      };
    });
  }, [sistemasConFarmacos, cantidadSistemas]);

  const generateSegmentTooltipContent = (item) => {
    const { name, impactCounts } = item;
    let content = `<div style="margin-bottom:4px"><strong>${name}</strong></div>`;
    if (impactCounts.alto > 0) content += `<div style="color:#ef4444">● ${impactCounts.alto} de Impacto Alto</div>`;
    if (impactCounts.medio > 0) content += `<div style="color:#f59e0b">● ${impactCounts.medio} de Impacto Medio</div>`;
    if (impactCounts.bajo > 0) content += `<div style="color:#10b981">● ${impactCounts.bajo} de Impacto Bajo</div>`;
    return content;
  };

  const getSegmentPath = (startAngle, endAngle, innerRadius, outerRadius) => {
    const startRad = (startAngle - 90) * Math.PI / 180;
    const endRad = (endAngle - 90) * Math.PI / 180;
    const x1 = 200 + innerRadius * Math.cos(startRad);
    const y1 = 200 + innerRadius * Math.sin(startRad);
    const x2 = 200 + outerRadius * Math.cos(startRad);
    const y2 = 200 + outerRadius * Math.sin(startRad);
    const x3 = 200 + outerRadius * Math.cos(endRad);
    const y3 = 200 + outerRadius * Math.sin(endRad);
    const x4 = 200 + innerRadius * Math.cos(endRad);
    const y4 = 200 + innerRadius * Math.sin(endRad);
    const largeArc = endAngle - startAngle > 180 ? 1 : 0;
    return `M ${x1} ${y1} L ${x2} ${y2} A ${outerRadius} ${outerRadius} 0 ${largeArc} 1 ${x3} ${y3} L ${x4} ${y4} A ${innerRadius} ${innerRadius} 0 ${largeArc} 0 ${x1} ${y1} Z`;
  };

  let currentAngle = 0;

  return (
    <div className="sunburst-pure-container">
        <div className="sunburst-svg-wrapper">
          <svg viewBox="0 0 400 400" className="sunburst-main-svg">
            {dataWithPercentages.map((item, index) => {
              const startAngle = currentAngle;
              const sweepAngle = (item.porcentajeTotal / 100) * 360;
              const endAngle = currentAngle + sweepAngle;
              currentAngle = endAngle;
              const path = getSegmentPath(startAngle, endAngle, 95, 155);
              const isHovered = hoveredSegment === index;

              return (
                <path
                  key={`sistema-${index}`}
                  d={path}
                  fill={item.color}
                  className={`sunburst-segment ${hoveredSegment !== null && !isHovered ? 'dimmed' : ''}`}
                  onMouseEnter={(e) => {
                    setHoveredSegment(index);
                    setActiveTooltipContent(generateSegmentTooltipContent(item));
                    setActiveTooltipPosition({ x: e.clientX, y: e.clientY });
                  }}
                  onMouseMove={(e) => setActiveTooltipPosition({ x: e.clientX, y: e.clientY })}
                  onMouseLeave={() => { setHoveredSegment(null); setActiveTooltipContent(null); }}
                  style={{ fillOpacity: isHovered ? 1 : 0.8, transition: 'all 0.3s ease' }}
                />
              );
            })}

            {hoveredSegment !== null && (() => {
              const hoveredData = dataWithPercentages[hoveredSegment];
              let farmacoAngle = dataWithPercentages.slice(0, hoveredSegment).reduce((acc, seg) => acc + (seg.porcentajeTotal / 100) * 360, 0);
              const sistemaAngleTotal = (hoveredData.porcentajeTotal / 100) * 360;
              const totalFarmacos = hoveredData.drugs.length;
              if (totalFarmacos === 0) return null;

              return hoveredData.drugs.map((farmaco, fIndex) => {
                const farmacoSweep = (1 / totalFarmacos) * sistemaAngleTotal;
                const farmacoEndAngle = farmacoAngle + farmacoSweep;
                const farmacoPath = getSegmentPath(farmacoAngle, farmacoEndAngle, 160, 185);
                farmacoAngle = farmacoEndAngle;
                return (
                  <path
                    key={`farmaco-${fIndex}`}
                    d={farmacoPath}
                    fill={getImpactColor(farmaco.magnitud)}
                    stroke="white"
                    strokeWidth="1"
                    style={{ animation: 'fadeIn 0.3s ease forwards' }}
                  />
                );
              });
            })()}
            
            <circle cx="200" cy="200" r="85" fill="#f8fafc" />
            <text x="200" y="195" textAnchor="middle" className="center-label-top">SISTEMAS</text>
            <text x="200" y="215" textAnchor="middle" className="center-label-bottom">MÉDICOS</text>
          </svg>
        </div>

        <div className="sunburst-legend-integrated">
          <div className="systems-mini-grid">
            {sistemasConFarmacos.map((item, index) => (
              <div key={index} className="mini-legend-item">
                <div className="mini-dot" style={{ backgroundColor: item.color }} />
                <span>{item.name}</span>
              </div>
            ))}
          </div>
        </div>

        {activeTooltipContent && (
          <div ref={tooltipRef} className="sunburst-tooltip-new" style={tooltipStyle} dangerouslySetInnerHTML={{ __html: activeTooltipContent }} />
        )}
    </div>
  );
};

export default SunburstChart;