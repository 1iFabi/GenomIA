import React, { useEffect, useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { Menu, X, ChevronDown, AlertCircle, AlertTriangle, Info, Zap, Activity, HelpCircle, FilterX } from 'lucide-react';
import { API_ENDPOINTS, apiRequest, clearToken } from '../../config/api';
import Sidebar from '../../components/Sidebar/Sidebar';
import SectionHeader from '../../components/SectionHeader/SectionHeader';
import GeneticTraitBar from '../../components/GeneticTraitBar/GeneticTraitBar';
import SunburstChart from '../../components/SunburstChart/SunburstChart';
import Tooltip from '../../components/Tooltip/Tooltip';
import { cn } from '../../lib/utils';
import { getImpactLevel, getImpactLabel } from '../../constants/geneticRisk';
import "./Farmacogenetica.css";

const hexToRgba = (hex, alpha) => {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
};

const farmacoPriorityConfig = {
  alto: { icon: AlertCircle, accentColor: "#ef4444", label: "Precaución Alta", sub: "Requieren supervisión" },
  medio: { icon: AlertTriangle, accentColor: "#f59e0b", label: "Precaución Media", sub: "Posible ajuste de dosis" },
  bajo: { icon: Info, accentColor: "#10b981", label: "Uso Estándar", sub: "Respuesta típica esperada" },
};

const ImpactSummaryCard = ({ level, count, onClick, isActive }) => {
  const config = farmacoPriorityConfig[level];
  const Icon = config.icon;
  return (
    <div 
      className={cn(
        `impact-summary-card-minimal impact-summary-card-minimal--${level}`,
        isActive && "impact-card-active"
      )}
      onClick={onClick}
      style={{ cursor: 'pointer' }}
    >
      <div className="impact-minimal-header">
        <Icon size={20} color={config.accentColor} />
        <span className="impact-minimal-count" style={{ color: config.accentColor }}>{count}</span>
      </div>
      <div className="impact-minimal-content">
        <span className="impact-minimal-label">{config.label}</span>
        <span className="impact-minimal-sub">{config.sub}</span>
      </div>
    </div>
  );
};

const Farmacogenetica = () => {
  const [user, setUser] = useState(null);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [isMobile, setIsMobile] = useState(false);
  const navigate = useNavigate();
  const [expandedGroups, setExpandedGroups] = useState({});
  const [pharmaData, setPharmaData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedRiskFilter, setSelectedRiskFilter] = useState('all');

  const systemColors = {
    cardiologia: '#3b82f6',
    'salud mental y neurologia': '#8b5cf6',
    gastroenterologia: '#10b981',
    'salud osea y reumatologia': '#f59e0b',
    oncologia: '#ef4444',
    otros: '#607d8b',
    // Claves con tilde por si el backend las envía acentuadas
    'cardiología': '#3b82f6',
    'salud mental y neurología': '#8b5cf6',
    'gastroenterología': '#10b981',
    'salud ósea y reumatología': '#f59e0b',
    'oncología': '#ef4444',
    'otros (sin sistema asignado)': '#607d8b',
  };

  const fallbackPalette = ['#0ea5e9', '#f97316', '#22c55e', '#a855f7', '#6366f1', '#14b8a6', '#f43f5e', '#f59e0b'];

  const normalizeName = (str = '') => (
    str
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .toLowerCase()
      .replace(/\s+/g, ' ')
      .trim()
  );

  const toggleGroup = (groupName) => {
    setExpandedGroups(prev => ({ ...prev, [groupName]: !prev[groupName] }));
  };

  useEffect(() => {
    const fetchAll = async () => {
      const uResp = await apiRequest(API_ENDPOINTS.ME, { method: 'GET' });
      if (uResp.ok) setUser(uResp.data.user || uResp.data);
      
      const hashString = (str) => {
        let hash = 0;
        for (let i = 0; i < str.length; i++) {
          hash = ((hash << 5) - hash) + str.charCodeAt(i);
          hash |= 0; // Convert to 32bit int
        }
        return Math.abs(hash);
      };

      const pResp = await apiRequest(API_ENDPOINTS.PHARMACOGENETICS, { method: 'GET' });
      if (pResp.ok && pResp.data && pResp.data.data) {
        setPharmaData(pResp.data.data.map(sys => {
          const key = normalizeName(sys.name || sys.system_name || '');
          const apiColor = sys.color || sys.system_color || sys.system?.color;
          const paletteColor = systemColors[key];
          const hashedColor = fallbackPalette[hashString(key) % fallbackPalette.length];
          const color = apiColor || paletteColor || hashedColor || '#64748b';
          return { ...sys, color };
        }));
      }
      setLoading(false);
    };
    fetchAll();
  }, []);

  useEffect(() => {
    const checkMobile = () => { setIsMobile(window.innerWidth <= 1024); if (window.innerWidth > 1024) setIsMobileMenuOpen(false); };
    checkMobile(); window.addEventListener('resize', checkMobile); return () => window.removeEventListener('resize', checkMobile);
  }, []);

  const riskSummary = useMemo(() => {
    let alto = 0, medio = 0, bajo = 0;
    pharmaData.forEach(sys => { sys.drugs.forEach(drug => {
      const level = getImpactLevel(drug.magnitud);
      if (level === 'alto') alto++; else if (level === 'medio') medio++; else bajo++;
    }); });
    return { alto, medio, bajo };
  }, [pharmaData]);

  const filteredData = useMemo(() => {
    if (selectedRiskFilter === 'all') return pharmaData;

    return pharmaData.map(system => {
      const filteredDrugs = system.drugs.filter(drug => getImpactLevel(drug.magnitud) === selectedRiskFilter);
      if (filteredDrugs.length === 0) return null;
      return { ...system, drugs: filteredDrugs };
    }).filter(Boolean);
  }, [pharmaData, selectedRiskFilter]);

  return (
    <div className="farmacogenetica-layout-new">
      {isMobile && (
        <button className="farmaco-burger" onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}>
          {isMobileMenuOpen ? <X size={24} color="white" /> : <Menu size={24} color="white" />}
        </button>
      )}

      <aside className="farmaco-sidebar-area">
        <Sidebar items={useMemo(() => [
          { label: 'Ancestría', href: '/dashboard/ancestria' },
          { label: 'Rasgos', href: '/dashboard/rasgos' },
          { label: 'Farmacogenética', href: '/dashboard/farmacogenetica' },
          { label: 'Biomarcadores', href: '/dashboard/biomarcadores' },
          { label: 'Biométricas', href: '/dashboard/biometricas' },
          { label: 'Enfermedades', href: '/dashboard/enfermedades' },
        ], [])} onLogout={async () => { await apiRequest(API_ENDPOINTS.LOGOUT, { method: 'POST' }); clearToken(); navigate('/'); }} user={user} isMobileMenuOpen={isMobileMenuOpen} setIsMobileMenuOpen={setIsMobileMenuOpen} />
      </aside>

      <main className="farmaco-main-content">
        <div className="farmaco-page-container">
          <SectionHeader title="Farmacogenética" subtitle="Impacto de tu genética en la respuesta a tratamientos médicos por sistema." icon={Zap} />

          <div className="farmaco-grid-wrapper">
            {loading ? (
              <div className="loading-state"><div className="spinner-blue"></div></div>
            ) : (
              <>
                <section className="farmaco-list-section">
                  <div className="filter-header">
                    <Tooltip content="Haz clic en las tarjetas para filtrar los resultados por nivel de riesgo.">
                      <div className="filter-help-trigger">
                        <Info size={14} />
                        <span>Filtros interactivos</span>
                      </div>
                    </Tooltip>
                    {selectedRiskFilter !== 'all' && (
                      <button className="filter-reset-btn" onClick={() => setSelectedRiskFilter('all')}>
                        <FilterX size={14} />
                        Mostrar todos
                      </button>
                    )}
                  </div>
                  <div className="impact-summary-row">
                    <ImpactSummaryCard 
                      level="alto" 
                      count={riskSummary.alto} 
                      onClick={() => setSelectedRiskFilter(selectedRiskFilter === 'alto' ? 'all' : 'alto')}
                      isActive={selectedRiskFilter === 'alto'}
                    />
                    <ImpactSummaryCard 
                      level="medio" 
                      count={riskSummary.medio} 
                      onClick={() => setSelectedRiskFilter(selectedRiskFilter === 'medio' ? 'all' : 'medio')}
                      isActive={selectedRiskFilter === 'medio'}
                    />
                    <ImpactSummaryCard 
                      level="bajo" 
                      count={riskSummary.bajo} 
                      onClick={() => setSelectedRiskFilter(selectedRiskFilter === 'bajo' ? 'all' : 'bajo')}
                      isActive={selectedRiskFilter === 'bajo'}
                    />
                  </div>

                  <div className="systems-stack">
                    {filteredData.length > 0 ? (
                      filteredData.map((system, idx) => (
                        <div key={idx} className="system-card-new" style={{ '--accent': system.color }}>
                          <div className="system-card-header" onClick={() => toggleGroup(system.name)}>
                            <div className="system-card-title-group">
                              <div className="system-dot" />
                              <h3>{system.name}</h3>
                            </div>
                            <div className="system-card-meta">
                              <span
                                className="drug-count-badge"
                                style={{ color: system.color, backgroundColor: hexToRgba(system.color, 0.1) }}
                              >
                                <strong style={{ fontWeight: 800 }}>{system.drugs.length}</strong>
                                <span style={{ opacity: 0.85 }}>fármacos</span>
                              </span>

                              <span className="system-toggle-icon" aria-hidden="true">
                                <ChevronDown className={cn("chevron-icon", expandedGroups[system.name] && "open")} />
                              </span>
                            </div>
                          </div>
                          {expandedGroups[system.name] && (
                            <div className="system-drug-list">
                              {system.drugs.map((drug, dIdx) => (
                                <GeneticTraitBar 
                                  key={dIdx} 
                                  title={drug.name}
                                  rsid={drug.rsid}
                                  genotype={drug.genotipo}
                                  percentage={drug.percentage}
                                  impactLabel={getImpactLabel(drug.magnitud)}
                                  impactColor={system.color}
                                  details={{
                                      cromosoma: drug.cromosoma,
                                      posicion: drug.posicion,
                                      categoria: system.name,
                                      magnitud: drug.magnitud
                                  }}
                                  freqChile={drug.freq_chile_percent}
                                  explanation={drug.phenotype_description || drug.fenotipo || "Sin descripción adicional."}
                                  delay={dIdx * 50}
                                />
                              ))}
                            </div>
                          )}
                        </div>
                      ))
                    ) : (
                      <div className="no-results-message">
                        <p>No se encontraron resultados para el filtro seleccionado.</p>
                      </div>
                    )}
                  </div>
                </section>

                <aside className="farmaco-chart-section">
                  <div className="chart-sticky-box">
                    <div className="chart-header-minimal">
                      <h4>Resumen Visual</h4>
                      <Tooltip content={
                        <div className="chart-tooltip-content">
                          <p><strong>Guía del Gráfico:</strong></p>
                          <ul className="text-xs space-y-1 mt-1">
                            <li>• <strong>Anillo Interior:</strong> Sistemas del cuerpo.</li>
                            <li>• <strong>Anillo Exterior:</strong> Fármacos individuales (al pasar el cursor).</li>
                            <li>• <strong>Colores:</strong> <span className="text-green-500">Bajo</span>, <span className="text-yellow-500">Medio</span>, <span className="text-red-500">Alto</span> riesgo.</li>
                          </ul>
                        </div>
                      }>
                        <HelpCircle size={16} className="help-icon-minimal" />
                      </Tooltip>
                    </div>
                    <SunburstChart data={pharmaData} />
                  </div>
                </aside>
              </>
            )}
          </div>
        </div>
      </main>
    </div>
  );
};

export default Farmacogenetica;
