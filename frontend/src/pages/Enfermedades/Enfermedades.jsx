import React, { useEffect, useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Menu,
  X,
  TestTube,
  AlertCircle,
  TrendingUp,
  BarChart3,
  Dna
} from 'lucide-react';
import ReactECharts from 'echarts-for-react';
import { API_ENDPOINTS, apiRequest, clearToken } from '../../config/api';
import Sidebar from '../../components/Sidebar/Sidebar';
import PriorityCard from '../../components/PriorityCard/PriorityCard';
import SectionHeader from '../../components/SectionHeader/SectionHeader';
import '../../styles/cards.css';
import './Enfermedades.css';
import CircularProgress from '../../components/CircularProgress/CircularProgress';
import GlossaryCarousel from '../../components/GlossaryCarousel/GlossaryCarousel';

function DonutChart({ data, isMobile }) {
  const total = data.reduce((a, b) => a + b.value, 0);
  const totalForPercentage = total || 1;

  const option = {
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    legend: { show: false },
    series: [
      {
        name: 'Enfermedades',
        type: 'pie',
        radius: ['70%', '85%'],
        padAngle: 3,
        avoidLabelOverlap: false,
        itemStyle: { borderRadius: 10, borderColor: '#fff', borderWidth: 2 },
        label: { show: false },
        emphasis: {
          label: { show: false },
          itemStyle: { shadowBlur: 10, shadowOffsetX: 0, shadowColor: 'rgba(0,0,0,0.3)' }
        },
        labelLine: { show: false },
        data: data.map(d => ({
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
        top: '32%',
        style: {
          text: total.toString(),
          fontSize: 30,
          fontWeight: 'bold',
          fill: '#111827'
        }
      },
      {
        type: 'text',
        left: 'center',
        top: '56%',
        style: {
          text: 'Enfermedades',
          fontSize: 12,
          fill: '#6B7280'
        }
      }
    ]
  };

  return (
    <div className="card-pro card-large-pro">
      <div className="card-pro__header">
        <div>
          <h3>Tus enfermedades</h3>
          <p className="card-pro__subtitle">Distribución por nivel de prioridad clínica</p>
        </div>
      </div>

      <ReactECharts
        option={option}
        style={{ height: isMobile ? '240px' : '280px', marginTop: '5px' }}
        opts={{ renderer: 'svg' }}
      />

      <div className="legend-pro">
        {data.map((item, i) => {
          const percentage = Math.round((item.value / totalForPercentage) * 100);
          return (
            <div className="legend-pro__item" key={i}>
              <div className="legend-pro__left">
                <span className="legend-pro__dot" style={{ background: item.color }} />
                <span className="legend-pro__label">{item.label}</span>
              </div>
              <span className="legend-pro__value">{percentage}%</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function KPICard({ title, value, subtitle, iconComponent, iconColor, tooltip }) {
  const [showTooltip, setShowTooltip] = useState(false);
  const tooltipRef = React.useRef(null);
  const triggerRef = React.useRef(null);

  const handleMouseEnter = () => {
    setShowTooltip(true);
    if (triggerRef.current && tooltipRef.current) {
      setTimeout(() => {
        const rect = triggerRef.current.getBoundingClientRect();
        const tooltipHeight = tooltipRef.current.offsetHeight;
        tooltipRef.current.style.position = 'fixed';
        tooltipRef.current.style.top =
          rect.top + rect.height / 2 - tooltipHeight / 2 + 'px';
        tooltipRef.current.style.left = rect.right + 16 + 'px';
        tooltipRef.current.style.zIndex = '9999';
      }, 0);
    }
  };

  const handleMouseLeave = () => setShowTooltip(false);

  return (
    <div className="card-pro card-small-pro kpi-card-modern">
      <div className="kpi-pro">
        <div className="kpi-pro__content">
          <div className="kpi-header-tooltip">
            <h3>{title}</h3>
            {tooltip && (
              <div className="kpi-tooltip-wrapper">
                <button
                  ref={triggerRef}
                  className="kpi-tooltip-trigger"
                  onMouseEnter={handleMouseEnter}
                  onMouseLeave={handleMouseLeave}
                  onClick={e => e.preventDefault()}
                >
                  ?
                </button>
                {showTooltip && (
                  <div
                    ref={tooltipRef}
                    className="kpi-tooltip"
                    style={{ position: 'fixed', display: 'block' }}
                  >
                    {tooltip}
                  </div>
                )}
              </div>
            )}
          </div>
          <div className="kpi-pro__value">{value}</div>
          <p className="kpi-pro__subtitle">{subtitle}</p>
        </div>
        <div className="kpi-pro__icon" style={{ background: iconColor }}>
          {iconComponent}
        </div>
      </div>
    </div>
  );
}

function QuickKPICard() {
  const [isHovered, setIsHovered] = useState(false);
  return (
    <div
      className="info-card-modern"
      style={{
        background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
        color: 'white',
        borderRadius: 20,
        padding: 18,
        boxShadow: isHovered ? '0 8px 24px rgba(102, 126, 234, 0.4)' : '0 4px 20px rgba(102,126,234,0.25)',
        border: '1px solid rgba(255,255,255,0.2)',
        display: 'flex',
        flexDirection: 'column',
        gap: 16,
        transition: 'all 0.3s ease',
        transform: isHovered ? 'translateY(-2px)' : 'translateY(0)',
        position: 'relative',
        overflow: 'hidden'
      }}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      <div
        style={{
          position: 'absolute',
          top: '-50%',
          right: '-30%',
          width: '100%',
          height: '150%',
          background:
            'radial-gradient(circle, rgba(255,255,255,0.1) 0%, transparent 70%)',
          pointerEvents: 'none'
        }}
      />
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 12,
          position: 'relative',
          zIndex: 1
        }}
      >
        <div
          style={{
            width: 40,
            height: 40,
            borderRadius: 10,
            background: 'rgba(255,255,255,0.2)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            backdropFilter: 'blur(10px)'
          }}
        >
          <AlertCircle size={22} color="white" strokeWidth={2.5} />
        </div>
        <h3
          style={{
            margin: 0,
            fontSize: 16,
            fontWeight: 700,
            color: 'white',
            letterSpacing: '-0.02em'
          }}
        >
          Información Importante
        </h3>
      </div>
      <div
        style={{
          position: 'relative',
          zIndex: 1,
          padding: '14px 16px',
          background: 'rgba(255,255,255,0.15)',
          borderRadius: 12,
          border: '1px solid rgba(255,255,255,0.2)',
          backdropFilter: 'blur(10px)'
        }}
      >
        <p
          style={{
            margin: 0,
            fontSize: 13,
            lineHeight: 1.6,
            color: 'rgba(255,255,255,0.95)',
            fontWeight: 500
          }}
        >
          Este perfil genético es{' '}
          <strong style={{ fontWeight: 700, color: 'white' }}>informativo</strong>{' '}
          y no constituye diagnóstico clínico. Consulta siempre con un
          especialista.
        </p>
      </div>
    </div>
  );
}

/* ===========================
   Glosario Carousel
=========================== */
const glossaryData = [
  {
    term: 'RSID',
    description:
      'Código único (ej: rs1234567) que identifica una variante específica en bases de datos científicas.'
  },
  {
    term: 'Magnitud',
    description:
      'Medida interna del impacto de una variante, basada en cuánto aumenta o disminuye el riesgo relativo frente a la población general.'
  },
  {
    term: 'Alelo',
    description:
      'Cada variante posible de un gen. Heredas una de cada progenitor.'
  },
  {
    term: 'Fenotipo',
    description:
      'Características observables (p.ej., color de ojos). Surge de genes + ambiente.'
  },
  {
    term: 'Genotipo',
    description: 'Tu composición genética heredada de ambos progenitores.'
  },
  {
    term: 'Gen',
    description: 'Segmento de ADN con instrucciones para una proteína.'
  }
];

/* ===========================
   Página Enfermedades (con Sidebar)
=========================== */
const Enfermedades = () => {
  const [snps, setSnps] = useState({ alta: [], media: [], baja: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [user, setUser] = useState(null);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [isMobile, setIsMobile] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    fetchUser();
    fetchDiseases();
  }, []);

  useEffect(() => {
    const checkMobile = () => {
      const mobile = window.innerWidth <= 1024;
      setIsMobile(mobile);
      if (!mobile) setIsMobileMenuOpen(false);
    };
    checkMobile();
    window.addEventListener('resize', checkMobile);
    return () => window.removeEventListener('resize', checkMobile);
  }, []);

  const fetchUser = async () => {
    const response = await apiRequest(API_ENDPOINTS.ME, { method: 'GET' });
    if (response.ok && response.data)
      setUser(response.data.user || response.data);
  };

  const fetchDiseases = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await apiRequest(API_ENDPOINTS.DISEASES, {
        method: 'GET'
      });

      if (!response.ok) {
        setError('No se pudieron cargar las enfermedades');
        setLoading(false);
        return;
      }

      let snpsData =
        response.data?.data || response.data?.snps || response.data;

      if (snpsData) {
        if (Array.isArray(snpsData)) {
          const processed = { alta: [], media: [], baja: [] };
          snpsData.forEach(item => {
            const priority =
              item.prioridad || item.priority || item.nivel || 'baja';
            if (
              priority === 'alta' ||
              priority === 'high' ||
              priority === 1
            ) {
              processed.alta.push(item);
            } else if (
              priority === 'media' ||
              priority === 'medium' ||
              priority === 2
            ) {
              processed.media.push(item);
            } else {
              processed.baja.push(item);
            }
          });
          setSnps(processed);
        } else if (typeof snpsData === 'object') {
          setSnps({
            alta: snpsData.alta || [],
            media: snpsData.media || [],
            baja: snpsData.baja || []
          });
        }
      }
    } catch (e) {
      setError('Ocurrió un error al cargar las enfermedades');
    } finally {
      setLoading(false);
    }
  };

  const handleLogout = async () => {
    try {
      await apiRequest(API_ENDPOINTS.LOGOUT, { method: 'POST' });
    } catch (_) {}
    clearToken();
    navigate('/');
  };

  const sidebarItems = useMemo(
    () => [
      { label: 'Ancestría', href: '/dashboard/ancestria' },
      { label: 'Rasgos', href: '/dashboard/rasgos' },
      { label: 'Farmacogenética', href: '/dashboard/farmacogenetica' },
      { label: 'Biomarcadores', href: '/dashboard/biomarcadores' },
      { label: 'Biométricas', href: '/dashboard/biometricas' },
      { label: 'Enfermedades', href: '/dashboard/enfermedades' }
    ],
    []
  );

  const donutData = useMemo(
    () => [
      { label: 'Alta prioridad', value: snps.alta.length, color: '#8b5cf6' },
      { label: 'Media prioridad', value: snps.media.length, color: '#06b6d4' },
      { label: 'Baja prioridad', value: snps.baja.length, color: '#f59e0b' }
    ],
    [snps]
  );

  const avgMagnitude = useMemo(() => {
    const allSnps = [...snps.alta, ...snps.media, ...snps.baja];
    let total = 0;
    let count = 0;
    allSnps.forEach(s => {
      const mag =
        parseFloat(s.magnitud_efecto) ||
        parseFloat(s.magnitude) ||
        parseFloat(s.effect_size) ||
        0;
      if (!Number.isNaN(mag) && mag > 0) {
        total += mag;
        count++;
      }
    });
    return count > 0 ? Number(total / count).toFixed(2) : '0.00';
  }, [snps]);

  const pathogenicGenes = useMemo(() => {
    const allSnps = [...snps.alta, ...snps.media, ...snps.baja];
    return allSnps.filter(s => {
      const mag =
        parseFloat(s.magnitud_efecto) ||
        parseFloat(s.magnitude) ||
        parseFloat(s.effect_size);
      if (!Number.isNaN(mag) && mag >= 3.0) return true;
      const priority = s.prioridad || s.priority || s.nivel;
      if (priority === 'alta' || priority === 'high' || priority === 1)
        return true;
      return false;
    }).length;
  }, [snps]);

  const geneticScore = useMemo(() => {
    const alta = snps.alta.length;
    const media = snps.media.length;
    const baja = snps.baja.length;
    const total = alta + media + baja;

    if (total === 0) return 0;

    const pesoAlta = 3;
    const pesoMedia = 2;
    const pesoBaja = 1;

    const raw = alta * pesoAlta + media * pesoMedia + baja * pesoBaja;
    const maxRaw = total * pesoAlta;

    return Math.round((raw / maxRaw) * 100);
  }, [snps]);

  const getPrioritiesData = () => {
    const mapPriority = priority => {
      const priorityMap = { alta: 'high', media: 'medium', baja: 'low' };
      const titleMap = {
        alta: 'Prioridad Alta',
        media: 'Prioridad Media',
        baja: 'Prioridad Baja'
      };
      return { level: priorityMap[priority], title: titleMap[priority] };
    };

    return ['alta', 'media', 'baja'].map(priority => {
      const { level, title } = mapPriority(priority);
      const diseases = (snps[priority] || []).map((snp, idx) => ({
        ...snp,
        id: `${snp.rsid || snp.rs_id || snp.id || 'rs'}-${idx}`,
        title:
          snp.fenotipo ||
          snp.phenotype ||
          snp.disease ||
          snp.enfermedad ||
          'Fenotipo no especificado',
        rsId: snp.rsid || snp.rs_id || snp.rsID,
        genotype: snp.genotipo || snp.genotype || snp.gt,
        cromosoma: snp.cromosoma,
        posicion: snp.posicion || snp.position,
        description:
          snp.phenotype_description ||
          snp.fenotipo ||
          snp.phenotype ||
          snp.description ||
          snp.disease ||
          'Sin descripción disponible',
        freq_chile_percent: snp.freq_chile_percent,
      }));
      return { level, title, diseases };
    });
  };

  const MainGrid = () => {
    const hasDiseases = snps.alta.length > 0 || snps.media.length > 0 || snps.baja.length > 0;
    
    return (
      <div className="enfermedades-page__content">
        <div className="dashboard-pro-3col">
          <DonutChart data={donutData} isMobile={isMobile} />

          <div className="kpis-stack">
            <GlossaryCarousel terms={glossaryData} />
            <QuickKPICard />
          </div>

          <CircularProgress score={geneticScore} />
        </div>

        {hasDiseases ? (
          <div className="enfermedades-page__priorities-container">
            {getPrioritiesData().map(priority => (
              <PriorityCard
                key={priority.level}
                level={priority.level}
                title={priority.title}
                diseases={priority.diseases}
              />
            ))}
          </div>
        ) : (
          <div className="enfermedades-page__empty">
            <p>
              No se encontraron predisposiciones genéticas a enfermedades en tu
              perfil.
            </p>
          </div>
        )}
      </div>
    );
  }

  if (loading || error) {
    return (
      <div className="enfermedades-layout">
        {isMobile && (
          <button
            className="enfermedades-layout__burger"
            onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
            aria-label={isMobileMenuOpen ? 'Cerrar menú' : 'Abrir menú'}
            aria-expanded={isMobileMenuOpen}
          >
            {isMobileMenuOpen ? (
              <X size={24} strokeWidth={2.5} />
            ) : (
              <Menu size={24} strokeWidth={2.5} />
            )}
          </button>
        )}

        <aside className="enfermedades-layout__sidebar">
          <Sidebar
            items={sidebarItems}
            onLogout={handleLogout}
            user={user}
            isMobileMenuOpen={isMobileMenuOpen}
            setIsMobileMenuOpen={setIsMobileMenuOpen}
          />
        </aside>

        <main className="enfermedades-layout__main">
          <div className="enfermedades-page">
            <SectionHeader
              title="Enfermedades"
              subtitle="Aquí podrás explorar tu predisposición genética a distintas enfermedades. Descubre qué mutaciones y variantes están presentes en tu ADN y cómo pueden influir en tu salud."
              icon={TestTube}
            />
            {loading ? (
              <div className="enfermedades-page__loading">
                <div className="spinner" />
                <p>Cargando información genética...</p>
              </div>
            ) : (
              <div className="enfermedades-page__error">
                <p>{error}</p>
                <button onClick={fetchDiseases}>Reintentar</button>
              </div>
            )}
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className="enfermedades-layout">
      {isMobile && (
        <button
          className="enfermedades-layout__burger"
          onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
          aria-label={isMobileMenuOpen ? 'Cerrar menú' : 'Abrir menú'}
          aria-expanded={isMobileMenuOpen}
        >
          {isMobileMenuOpen ? (
            <X size={24} strokeWidth={2.5} />
          ) : (
            <Menu size={24} strokeWidth={2.5} />
          )}
        </button>
      )}

      <aside className="enfermedades-layout__sidebar">
        <Sidebar
          items={sidebarItems}
          onLogout={handleLogout}
          user={user}
          isMobileMenuOpen={isMobileMenuOpen}
          setIsMobileMenuOpen={setIsMobileMenuOpen}
        />
      </aside>

      <main className="enfermedades-layout__main">
        <div className="enfermedades-page">
          <SectionHeader
            title="Enfermedades"
            subtitle="Aquí podrás explorar tu predisposición genética a distintas enfermedades. Descubre qué mutaciones y variantes están presentes en tu ADN y cómo pueden influir en tu salud."
            icon={TestTube}
          />
          <MainGrid />
        </div>
      </main>
    </div>
  );
};

export default Enfermedades;
