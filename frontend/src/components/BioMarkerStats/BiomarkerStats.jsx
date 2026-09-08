// BiomarkerStats.jsx
import React from 'react';
import './BiomarkerStats.css';

export default function BiomarkerStats({ data = {}, total = 0 }) {
  const userTotal = Object.values(data).reduce((sum, count) => sum + count, 0);
  const significantImpact = (data.alto || 0) + (data.medio || 0);
  
  return (
    <div className="stats-container">
      {/* Item 1: Base Global */}
      <div className="stat-item">
        <div className="stat-label">Base de Datos Global</div>
        <div className="stat-value-container">
          <div className="stat-value">{total}</div>
          <div className="stat-unit">Biomarcadores Analizados</div>
        </div>
        <div className="progress-bar">
          <div className="progress-fill" style={{ width: '100%' }}></div>
        </div>
      </div>
      
      {/* Item 2: Tu Perfil */}
      <div className="stat-item level-2">
        <div className="stat-label">Tu Perfil Genético</div>
        <div className="stat-value-container">
          <div className="stat-value">{userTotal}</div>
          <div className="stat-unit">Indicadores Identificados</div>
        </div>
        <div className="progress-bar">
          <div className="progress-fill" style={{ width: total > 0 ? `${(userTotal / total) * 100}%` : '0%' }}></div>
        </div>
      </div>
      
      {/* Item 3: Impacto Significativo */}
      <div className="stat-item level-3">
        <div className="stat-label">Impacto Significativo</div>
        <div className="stat-value-container">
          <div className="stat-value">{significantImpact}</div>
          <div className="stat-unit">Hallazgos Alto/Medio</div>
        </div>
        <div className="progress-bar">
          <div className="progress-fill" style={{ width: userTotal > 0 ? `${(significantImpact / userTotal) * 100}%` : '0%' }}></div>
        </div>
      </div>
    </div>
  );
}