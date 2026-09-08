import React, { useEffect, useMemo, useState } from 'react';
import ReactECharts from 'echarts-for-react';
import { API_ENDPOINTS, apiRequest } from '../../config/api';
import '../../styles/cards.css';
import './IndigenousRadarChart.css';

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

  const colors = [
    '#8b5cf6', // Purple
    '#06b6d4', // Cyan
    '#f59e0b', // Orange
    '#ec4899', // Pink
    '#22c55e'  // Green
  ];

  const normalizeName = (name = '') => {
    const cleaned = name.replace(/_/g, ' ').trim();
    const fixes = {
      Aimara: 'Aymara',
      Aymara: 'Aymara',
      Chileno_general: 'Chileno general'
    };
    return fixes[cleaned] || cleaned || 'Desconocido';
  };

  const chartData = useMemo(() => {
    return (data?.indigenous_peoples || []).map((item, index) => ({
      label: normalizeName(item.name),
      value: Number(item.percentage) || 0,
      color: colors[index % colors.length],
      variant_count: item.variant_count || 0,
      avg_allele_frequency: item.avg_allele_frequency || 0
    })).filter(item => item.value > 0);
  }, [data]);

  const total = chartData.reduce((a, b) => a + b.value, 0) || 100;

  // Determinar qué mostrar en el centro
  const centerText = hoveredItem ? hoveredItem.label : '';
  const centerValue = hoveredItem ? `${hoveredItem.value}%` : '';

  const option = {
    tooltip: { 
      show: false
    },
    legend: { show: false },
    series: [
      {
        name: 'Pueblos Indígenas',
        type: 'pie',
        radius: ['70%', '85%'],
        padAngle: 3,
        avoidLabelOverlap: false,
        itemStyle: { 
          borderRadius: 10, 
          borderColor: '#fff', 
          borderWidth: 2 
        },
        label: { show: false },
        emphasis: {
          label: { show: false },
          itemStyle: { 
            shadowBlur: 10, 
            shadowOffsetX: 0, 
            shadowColor: 'rgba(0,0,0,0.3)' 
          }
        },
        labelLine: { show: false },
        data: chartData.map(d => ({
          value: d.value,
          name: d.label,
          itemStyle: { color: d.color }
        }))
      }
    ],
    graphic: [
      {
        type: 'text',
        left: 'center',
        top: '38%',
        style: {
          text: centerValue,
          fontSize: 40,
          fontWeight: 'bold',
          fill: '#111827',
          opacity: hoveredItem ? 1 : 0
        },
        transition: ['shape']
      },
      {
        type: 'text',
        left: 'center',
        top: '56%',
        style: {
          text: centerText,
          fontSize: 15,
          fontWeight: '600',
          fill: '#6B7280',
          opacity: hoveredItem ? 1 : 0
        },
        transition: ['shape']
      }
    ]
  };

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
        <h3>Pueblos Indígenas de Chile</h3>
        <p className="chart-subtitle">
          Distribución por ancestría genética
        </p>
      </div>

      <div className="chart-main-content">
        <div className="chart-container-donut">
          <ReactECharts 
            option={option} 
            style={{ height: '320px', marginTop: '5px' }} 
            opts={{ renderer: 'svg' }}
            onEvents={{
              mouseover: (params) => {
                if (params.data) {
                  const item = chartData.find(d => d.label === params.data.name);
                  if (item) setHoveredItem(item);
                }
              },
              mouseout: () => {
                setHoveredItem(null);
              }
            }}
          />
        </div>
        
        <div className="chart-info">
          <h4>Desglose</h4>
          <div className="peoples-list">
            {chartData.map((item, index) => (
              <div key={index} className="people-item">
                <div className="people-header">
                  <span className="people-name" style={{ color: item.color }}>
                    - {item.label}
                  </span>
                  <span className="people-percentage">{item.value}%</span>
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
