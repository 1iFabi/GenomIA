import React, { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { Dna, Menu, X } from 'lucide-react';
import Sidebar from '../../components/Sidebar/Sidebar';
import SectionHeader from '../../components/SectionHeader/SectionHeader';
import { API_ENDPOINTS, apiRequest, clearToken } from '../../config/api';
import GeneticTraitBar from '../../components/GeneticTraitBar/GeneticTraitBar';
import { impactColor } from '../../constants/geneticRisk';
import '../../styles/cards.css';
import './Biometrics.css';

const Biometrics = () => {
  const [user, setUser] = useState(null);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [isMobile, setIsMobile] = useState(false);
  const [biometrics, setBiometrics] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [hoveredMetric, setHoveredMetric] = useState(null);
  const navigate = useNavigate();

  useEffect(() => {
    fetchUser();
    fetchBiometrics();
  }, []);

  useEffect(() => {
    const checkMobile = () => {
      const mobile = window.innerWidth <= 1024;
      setIsMobile(mobile);
      if (!mobile) {
        setIsMobileMenuOpen(false);
      }
    };

    checkMobile();
    window.addEventListener('resize', checkMobile);
    return () => window.removeEventListener('resize', checkMobile);
  }, []);

  const fetchUser = async () => {
    const response = await apiRequest(API_ENDPOINTS.ME, { method: 'GET' });
    if (response.ok && response.data) {
      setUser(response.data.user || response.data);
    }
  };

  const fetchBiometrics = async () => {
    setLoading(true);
    setError(null);
    const response = await apiRequest(API_ENDPOINTS.BIOMETRICS, { method: 'GET' });

    if (response.ok && response.data) {
      const payload = response.data.data || response.data;
      if (payload?.matrix || payload?.variants) {
        setBiometrics(payload);
      } else {
        setError('No hay datos biometrico-geneticos disponibles.');
      }
    } else {
      setError('No se pudieron cargar tus biometrias. Intenta nuevamente.');
    }
    setLoading(false);
  };

  const handleLogout = async () => {
    try {
      await apiRequest(API_ENDPOINTS.LOGOUT, { method: 'POST' });
    } catch (err) {
      console.error('Error al cerrar sesion', err);
    }
    clearToken();
    navigate('/');
  };

  const sidebarItems = useMemo(
    () => [
      { label: 'Ancestria', href: '/dashboard/ancestria' },
      { label: 'Rasgos', href: '/dashboard/rasgos' },
      { label: 'Farmacogenetica', href: '/dashboard/farmacogenetica' },
      { label: 'Biomarcadores', href: '/dashboard/biomarcadores' },
      { label: 'Biometricas', href: '/dashboard/biometricas' },
      { label: 'Enfermedades', href: '/dashboard/enfermedades' },
    ],
    []
  );

  const impactScore = (impact) => {
    if (impact === 'high') return 3;
    if (impact === 'medium') return 2;
    return 1;
  };

  const impactLabel = (impact) => {
    if (impact === 'high') return 'Alto';
    if (impact === 'medium') return 'Intermedio';
    return 'Bajo';
  };

  const variants = useMemo(() => {
    if (biometrics?.variants?.length) {
      return biometrics.variants.map((v, idx) => ({
        id: `${v.rsid || 'var'}-${v.genotipo || idx}-${idx}`,
        rsid: v.rsid || 'NA',
        genotipo: v.genotipo || 'NA',
        fenotipo: v.fenotipo || v.explanation || 'Variante',
        cromosoma: v.cromosoma || '',
        posicion: v.posicion || '',
        categoria: v.categoria || v.grupo || '',
        magnitud: typeof v.magnitud_efecto === 'number' ? v.magnitud_efecto : null,
        impact: v.impact || 'low',
        freq_chile_percent: v.freq_chile_percent,
        explanation: v.phenotype_description || v.explanation || v.fenotipo || 'Sin detalles.',
      }));
    }

    if (biometrics?.matrix) {
      return biometrics.matrix.flatMap((row, rIdx) =>
        (row.cells || []).map((cell, idx) => ({
          id: `${row.name}-${cell.column}-${idx}`,
          rsid: cell.explanation?.split(':').pop()?.trim() || `Cell-${rIdx}-${idx}`,
          genotipo: '',
          fenotipo: `${row.name} - ${cell.column}`,
          cromosoma: '',
          posicion: '',
          categoria: row.name,
          magnitud: null,
          impact: cell.impact || 'low',
          explanation: cell.explanation || 'Sin detalles.',
        }))
      );
    }

    return [];
  }, [biometrics]);

  const avgImpact = useMemo(() => {
    if (!variants.length) return '0.0';
    return (
      variants.reduce((sum, item) => sum + impactScore(item.impact), 0) /
      variants.length
    ).toFixed(1);
  }, [variants]);

  const totalsByImpact = useMemo(() => {
    return variants.reduce(
      (acc, cell) => {
        acc[cell.impact] = (acc[cell.impact] || 0) + 1;
        return acc;
      },
      { high: 0, medium: 0, low: 0 }
    );
  }, [variants]);

  return (
    <div className="biometrics-layout">
      {/* Burger button para moviles */}
      <button
        className="biometrics-layout__burger"
        onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
        aria-label={isMobileMenuOpen ? 'Cerrar menu' : 'Abrir menu'}
        style={{ display: isMobile ? 'flex' : 'none' }}
      >
        {isMobileMenuOpen ? <X size={24} strokeWidth={2.5} /> : <Menu size={24} strokeWidth={2.5} />}
      </button>

      <aside className={`biometrics-layout__sidebar ${isMobileMenuOpen ? 'open' : ''}`}>
        <Sidebar
          items={sidebarItems}
          onLogout={handleLogout}
          user={user}
          isMobileMenuOpen={isMobileMenuOpen}
          setIsMobileMenuOpen={setIsMobileMenuOpen}
        />
      </aside>

      <main className="biometrics-layout__main">
        <div className="biometrics-page">
          <SectionHeader
            title="Biométricas"
            subtitle="Analisis de tus predisposiciones geneticas segun datos biometricos"
            icon={Dna}
          />

          {loading && (
            <div className="biometrics-page__loading">
              <div className="spinner" />
              <p>Cargando biometrias personalizadas...</p>
            </div>
          )}

          {!loading && error && (
            <div className="biometrics-page__error">
              <p>{error}</p>
              <button onClick={fetchBiometrics}>Reintentar</button>
            </div>
          )}

          {!loading && !error && (
            <div className="biometrics-page__content">
              {/* Resumen Global */}
              <div className="bio-summary-card">
                <div className="bio-summary-title">
                  <h3>Resumen Global de Factores</h3>
                </div>
                <div className="bio-summary-grid">
                  {[
                    {
                      label: 'Promedio impacto',
                      value: avgImpact,
                      fixedColor: null,
                      description: 'Promedio de los impactos de todas tus variantes biometrico-geneticas.'
                    },
                    {
                      label: 'Impacto alto',
                      value: totalsByImpact.high,
                      fixedColor: '#ef4444',
                      description: 'Cantidad de variantes con impacto alto segun magnitud/efecto.'
                    },
                    {
                      label: 'Impacto medio',
                      value: totalsByImpact.medium,
                      fixedColor: '#f59e0b',
                      description: 'Cantidad de variantes con impacto medio.'
                    },
                    {
                      label: 'Impacto bajo',
                      value: totalsByImpact.low,
                      fixedColor: '#10b981',
                      description: 'Cantidad de variantes con impacto bajo.'
                    },
                  ].map(({ label, value, fixedColor, description }) => {
                    const numericValue = typeof value === 'number' ? value : parseFloat(value);
                    const percentage = (Math.min(numericValue, 3) / 3) * 100;
                    
                    let color = fixedColor;
                    if (!color) {
                       color = numericValue >= 2.5 ? '#ef4444' : numericValue >= 1.5 ? '#f59e0b' : '#10b981';
                    }

                    return (
                      <div
                        key={label}
                        className="circular-stat"
                        onMouseEnter={() => setHoveredMetric(label)}
                        onMouseLeave={() => setHoveredMetric(null)}
                      >
                        <div
                          style={{
                            position: 'relative',
                            width: '100px',
                            height: '100px',
                            marginBottom: '0.5rem',
                          }}
                        >
                          <svg width="100" height="100" style={{ transform: 'rotate(-90deg)' }}>
                            <circle cx="50" cy="50" r="42" fill="none" stroke="#f3f4f6" strokeWidth="8" />
                            <circle
                              cx="50"
                              cy="50"
                              r="42"
                              fill="none"
                              stroke={color}
                              strokeWidth="8"
                              strokeDasharray={`${(percentage / 100) * 264} 264`}
                              strokeLinecap="round"
                              style={{ transition: 'stroke-dasharray 0.6s ease' }}
                            />
                          </svg>
                          <div className="circular-stat__value" style={{ color: color, fontSize: '1.5rem' }}>
                            {value}
                          </div>
                        </div>
                        <div className="circular-stat__label">{label}</div>
                        {hoveredMetric === label && (
                          <div className="circular-stat__tooltip">
                            {description}
                            <span className="circular-stat__tooltip-arrow" />
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Lista de variantes */}
              <div className="bio-traits-list">
                {variants.map((item, index) => {
                  const color = impactColor(item.impact);
                  const baseScore = impactScore(item.impact);
                  const percentage =
                    item.magnitud && !Number.isNaN(item.magnitud)
                      ? Math.min(Math.round((item.magnitud / 3) * 100), 100)
                      : (baseScore / 3) * 100;

                  return (
                    <GeneticTraitBar
                      key={item.id}
                      title={item.fenotipo}
                      rsid={item.rsid}
                      genotype={item.genotipo}
                      percentage={percentage}
                      impactLabel={impactLabel(item.impact)}
                      impactColor={color}
                      intensityLevel={baseScore}
                      details={{
                        cromosoma: item.cromosoma || 'NA',
                        posicion: item.posicion || '',
                        categoria: item.categoria || 'Sin categoría',
                        magnitud: item.magnitud,
                      }}
                      freqChile={item.freq_chile_percent}
                      explanation={item.explanation}
                      delay={index * 50}
                    />
                  );
                })}
                {!variants.length && (
                  <div className="biometrics-page__error">
                    <p>No encontramos biometrias para tu cuenta.</p>
                    <button onClick={fetchBiometrics}>Reintentar</button>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </main>
    </div>
  );
};

export default Biometrics;
