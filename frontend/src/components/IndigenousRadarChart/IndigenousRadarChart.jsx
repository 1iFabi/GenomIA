import React, { useEffect, useMemo, useState } from 'react';
import { API_ENDPOINTS, apiRequest } from '../../config/api';
import '../../styles/cards.css';
import IndigenousBarChart from './IndigenousBarChart';
import './IndigenousRadarChart.css';

const colors = [
  '#2563eb', // Blue
  '#0f766e', // Teal
  '#b45309', // Amber
  '#be185d', // Rose
  '#4d7c0f'  // Olive
];

const normalizeName = (name = '') => {
  const cleaned = String(name ?? '').replace(/_/g, ' ').trim();
  const fixes = {
    Aimara: 'Aymara',
    Aymara: 'Aymara',
    Chileno_general: 'Chileno general'
  };
  return fixes[cleaned] || cleaned || 'Desconocido';
};

const formatPercentage = (value) => {
  const number = Number(value) || 0;
  return Number.isInteger(number) ? `${number}` : number.toFixed(2).replace(/\.0+$/, '');
};

const IndigenousRadarChart = () => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [hoveredItem, setHoveredItem] = useState(null);

  useEffect(() => {
    fetchIndigenousData();
  }, []);

  const fetchIndigenousData = async () => {
    try {
      setLoading(true);
      const response = await apiRequest(API_ENDPOINTS.INDIGENOUS, { method: 'GET' });
      
      if (response.ok && response.data && response.data.data) {
        setData(response.data.data);
      } else {
        setError('No se pudieron cargar los datos de pueblos indígenas.');
      }
    } catch (err) {
      console.error('Error fetching indigenous data:', err);
      setError('Error al cargar los datos.');
    } finally {
      setLoading(false);
    }
  };

  const chartData = useMemo(() => {
    return (data?.indigenous_peoples || [])
      .map((item, index) => ({
        label: normalizeName(item.name),
        value: Number(item.percentage) || 0,
        sourceIndex: index,
        variant_count: Number(item.variant_count) || 0,
        avg_allele_frequency: Number(item.avg_allele_frequency) || 0
      }))
      .filter(item => item.value > 0)
      .sort((first, second) => second.value - first.value || first.sourceIndex - second.sourceIndex)
      .map((item, index) => ({
        ...item,
        color: colors[index % colors.length]
      }));
  }, [data]);

  const chartHeight = Math.max(260, chartData.length * 56 + 64);
  const hoveredLabel = hoveredItem?.label;

  if (loading) {
    return (
      <div className="indigenous-radar-chart">
        <div className="loading-container">
          <div className="spinner"></div>
          <p>Cargando datos de pueblos indígenas...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="indigenous-radar-chart">
        <div className="error-container">
          <p className="error-message">{error}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="indigenous-radar-chart">
      <div className="chart-header">
        <h3 className="chart-editorial-title">
          <span className="chart-title-main">
            <span className="chart-title-pueblos">PUEBLOS</span>{' '}
            <span className="chart-title-indigenas">INDÍGENAS</span>
          </span>
          <span className="chart-title-separator" aria-hidden="true">|</span>
          <span className="chart-title-supporting">
            Distribución genética asociada a poblaciones indígenas de Chile.
          </span>
        </h3>
      </div>

      <div className="chart-main-content">
        <div className="chart-container-bars">
          <IndigenousBarChart
            data={chartData}
            height={chartHeight}
            onItemHover={setHoveredItem}
            onItemLeave={() => setHoveredItem(null)}
          />
        </div>
        
        <div className="chart-info">
          <h4>Desglose</h4>
          <div className="peoples-list">
            {chartData.map((item, index) => (
              <div
                key={index}
                className={`people-item${hoveredLabel === item.label ? ' is-hovered' : ''}`}
                onMouseEnter={() => setHoveredItem(item)}
                onMouseLeave={() => setHoveredItem(null)}
              >
                <div className="people-header">
                  <span className="people-name" style={{ color: item.color }}>
                    - {item.label}
                  </span>
                  <span className="people-percentage">{formatPercentage(item.value)}%</span>
                </div>
                <div className="people-details">
                  <span className="detail-item">
                    {item.variant_count} variante{item.variant_count !== 1 ? 's' : ''}
                  </span>
                  <span className="detail-separator">•</span>
                  <span className="detail-item">
                    Frec. alélica: {(item.avg_allele_frequency * 100).toFixed(2)}%
                  </span>
                </div>
                <div className="people-bar">
                  <div 
                    className="people-bar-fill" 
                    style={{ 
                      width: `${item.value}%`,
                      backgroundColor: item.color
                    }}
                  ></div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};

export default IndigenousRadarChart;
