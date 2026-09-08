import React, { useEffect, useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { Menu, X, Info, Activity, TrendingUp, MapPin, Globe, ChevronDown, ChevronUp } from 'lucide-react';
import { API_ENDPOINTS, apiRequest, clearToken } from '../../config/api';
import Sidebar from '../../components/Sidebar/Sidebar';
import SectionHeader from '../../components/SectionHeader/SectionHeader';
import SemiGauge from '../../components/SemiGauge/SemiGauge';
import BiomarkerStats from '../../components/BioMarkerStats/BiomarkerStats';
import { formatFrequency } from '../../lib/utils';
import { RISK_COLORS } from '../../constants/geneticRisk';
import '../../styles/cards.css';
import './Biomarcadores.css';

const Biomarcadores = () => {
  const [expandedCard, setExpandedCard] = useState(null);
  const [user, setUser] = useState(null);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [isMobile, setIsMobile] = useState(false);
  const [totalBiomarcadores, setTotalBiomarcadores] = useState(0);
  const [globalTotal, setGlobalTotal] = useState(0);
  const [biomarkers, setBiomarkers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const navigate = useNavigate();

  useEffect(() => {
    fetchUser();
    fetchBiomarkers();
  }, []);

  const fetchBiomarkers = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await apiRequest(API_ENDPOINTS.BIOMARKERS, { method: 'GET' });
      if (response.ok && response.data) {
        setBiomarkers(response.data.biomarkers || []);
        setTotalBiomarcadores(response.data.total || 0);
        setGlobalTotal(response.data.global_total || response.data.total || 0);
      } else {
        setError('No pudimos cargar tus biomarcadores.');
      }
    } catch (err) {
      setError('Error de conexion al cargar biomarcadores.');
    }
    setLoading(false);
  };

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

  const handleLogout = async () => {
    try {
      await apiRequest(API_ENDPOINTS.LOGOUT, { method: 'POST' });
    } catch (error) {
      console.error('Error al cerrar sesion', error);
    }
    clearToken();
    navigate('/');
  };

  const sidebarItems = useMemo(() => [
    { label: 'Ancestría', href: '/dashboard/ancestria' },
    { label: 'Rasgos', href: '/dashboard/rasgos' },
    { label: 'Farmacogenética', href: '/dashboard/farmacogenetica' },
    { label: 'Biomarcadores', href: '/dashboard/biomarcadores' },
    { label: 'Biométricas', href: '/dashboard/biometricas' },
    { label: 'Enfermedades', href: '/dashboard/enfermedades' },
  ], []);

  const riskDistribution = useMemo(() => {
    const counts = { bajo: 0, medio: 0, alto: 0 };
    biomarkers.forEach((bio) => {
      const risk = bio?.userResult?.risk;
      if (counts[risk] !== undefined) {
        counts[risk] += 1;
      }
    });
    return counts;
  }, [biomarkers]);

  const getRiskClass = (risk) => {
    const classes = { bajo: 'risk-bajo', medio: 'risk-medio', alto: 'risk-alto' };
    return classes[risk] || 'risk-default';
  };

  const biomarkerRiskConfig = {
    alto: { color: RISK_COLORS.alto }, // Rojo
    medio: { color: RISK_COLORS.medio }, // Ámbar/Amarillo
    bajo: { color: RISK_COLORS.bajo }, // Verde
  };

  return (
    <div className="dashboard">
      {isMobile && (
        <button
          className="dashboard__burger"
          onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
          aria-label={isMobileMenuOpen ? "Cerrar menu" : "Abrir menu"}
          aria-expanded={isMobileMenuOpen}
        >
          {isMobileMenuOpen ? <X size={24} strokeWidth={2.5} /> : <Menu size={24} strokeWidth={2.5} />}
        </button>
      )}

      <aside className="dashboard__sidebar">
        <Sidebar
          items={sidebarItems}
          onLogout={handleLogout}
          user={user}
          isMobileMenuOpen={isMobileMenuOpen}
          setIsMobileMenuOpen={setIsMobileMenuOpen}
        />
      </aside>

      <main className="dashboard__main">
        <div className="biomarcador-container">
          <div className="biomarcador-wrapper">
            <SectionHeader
              title="Biomarcadores"
              subtitle="Resultados personalizados de tu análisis genético"
              icon={Globe}
            />

            {loading && (
              <div className="biomarkers-loading">
                <div className="spinner" />
                <p>Cargando biomarcadores...</p>
              </div>
            )}

            {!loading && error && (
              <div className="biomarkers-error">
                <p>{error}</p>
                <button onClick={fetchBiomarkers}>Reintentar</button>
              </div>
            )}

            {!loading && !error && (
              <>
                <div className="biomarkers-summary-grid">
                  <div className="summary-card">
                    <h3 className="summary-card__title">Perfil de Impacto</h3>
                    <div className="summary-card__content">
                      <SemiGauge data={riskDistribution} riskConfig={biomarkerRiskConfig} />
                    </div>
                  </div>

                  <div className="summary-card">
                    <h3 className="summary-card__title">Resumen de Análisis</h3>
                    <div className="summary-card__content">
                      <BiomarkerStats 
                        data={riskDistribution} 
                        total={globalTotal} 
                      />
                    </div>
                  </div>

                  <div className="summary-card info-card">
                    <h3 className="summary-card__title">Información de Resultados</h3>
                    <div className="summary-card__content">
                      <p className="info-card__text">
                        Este análisis revela variantes genéticas asociadas a indicadores biológicos clave.
                      </p>
                      <p className="info-card__text">
                        Los niveles de impacto reflejan cómo tu composición genética influye en cada biomarcador, permitiendo una visión profunda de tu bienestar fisiológico.
                      </p>
                      <div className="info-card__footer">
                        <Info size={16} />
                        <span>Datos basados en tu perfil genético único.</span>
                      </div>
                    </div>
                  </div>
                </div>

                <div className="cards-container">
                  {biomarkers.map((bio) => (
                    <div
                      key={bio.id}
                      className={`biomarker-card ${getRiskClass(bio.userResult?.risk)}`}
                    >
                      <div className="card-content">
                        <div className="card-header">
                          <div className="card-info">
                            <div className="title-row">
                              <h2 className="card-title">{bio.name}</h2>
                            </div>
                            <p className="card-id">{bio.id} — {bio.gene}</p>
                            <p className="card-location">
                              Cromosoma {bio.chromosome || '-'} | Posición: {bio.position || '-'}
                            </p>
                          </div>
                          <div className={`result-badge ${getRiskClass(bio.userResult?.risk)}`}>
                            TU RESULTADO: {bio.userGenotype || bio.userResult?.genotype || '-'}
                          </div>
                        </div>

                        <div className="gauge-container">
                          <div className="gauge-labels">
                            <span>Baja</span>
                            <span>Normal</span>
                            <span>Alta</span>
                          </div>
                          <div className="gauge-bar">
                            <div className="gauge-indicator"></div>
                          </div>
                        </div>

                        <div className="stats-grid">
                          <div className="stat-box">
                            <div className="stat-header">
                              <TrendingUp size={16} className="stat-icon" />
                              <span className="stat-label">MAGNITUD</span>
                            </div>
                            <div className="magnitude-bars">
                              {[...Array(5)].map((_, i) => (
                                <div
                                  key={i}
                                  className={`magnitude-bar ${i < (bio.userResult?.magnitude || 0) ? 'active' : ''}`}
                                ></div>
                              ))}
                            </div>
                          </div>
                          <div className="stat-box">
                            <div className="stat-header">
                              <MapPin size={16} className="stat-icon" />
                              <span className="stat-label">FRECUENCIA CHILE</span>
                            </div>
                            <div className="stat-value">
                              {formatFrequency(bio.userResult?.frequency ?? bio.freq_chile_percent, 'N/A')}
                            </div>
                            <div className="stat-note">Frecuencia estimada en poblacion chilena.</div>
                          </div>
                        </div>

                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            setExpandedCard(expandedCard === bio.id ? null : bio.id);
                          }}
                          className={`expand-button ${getRiskClass(bio.userResult?.risk)}`}
                        >
                          {expandedCard === bio.id ? (
                            <>
                              <ChevronUp size={20} />
                              Ocultar todos los genotipos
                            </>
                          ) : (
                            <>
                              <ChevronDown size={20} />
                              Ver tu genotipo detectado
                            </>
                          )}
                        </button>
                      </div>

                      {expandedCard === bio.id && (
                        <div className="expanded-table">
                          <div className="table-wrapper">
                            <table className="genotypes-table">
                              <thead>
                                <tr>
                                  <th>Genotipo</th>
                                  <th>Fenotipo</th>
                                  <th>Nivel de Riesgo</th>
                                  <th>Frecuencia</th>
                                  <th>Tu Resultado</th>
                                </tr>
                              </thead>
                              <tbody>
                                {(bio.allGenotypes || []).map((gen) => (
                                  <tr
                                    key={gen.genotype}
                                    className={gen.genotype === (bio.userGenotype || bio.userResult?.genotype) ? 'user-row' : ''}
                                  >
                                    <td><span className="genotype-code">{gen.genotype}</span></td>
                                    <td><span className="phenotype-desc">{gen.phenotype}</span></td>
                                    <td>
                                      <span className={`risk-badge ${getRiskClass(gen.risk)}`}>
                                        {(gen.risk || '').toUpperCase()}
                                      </span>
                                    </td>
                                    <td>
                                      <span className="frequency-value">
                                        {formatFrequency(gen.frequency, 'N/A')}
                                      </span>
                                    </td>
                                    <td>
                                      {gen.genotype === (bio.userGenotype || bio.userResult?.genotype) && (
                                        <span className="checkmark">✓</span>
                                      )}
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>
        </div>
      </main>
    </div>
  );
};

export default Biomarcadores;
