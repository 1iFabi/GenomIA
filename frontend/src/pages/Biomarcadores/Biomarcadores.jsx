import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AnimatePresence, motion as Motion, useReducedMotion } from 'motion/react';
import { useNavigate } from 'react-router-dom';
import { ChevronRight, Info, Menu, X } from 'lucide-react';
import { Legend, LegendItem, LegendLabel, LegendMarker, useLegendItem } from '../../components/charts/legend';
import { SunburstCenter } from '../../components/charts/sunburst-center';
import { SunburstChart } from '../../components/charts/sunburst-chart';
import { SunburstHint } from '../../components/charts/sunburst-hint';
import { SunburstLabels } from '../../components/charts/sunburst-labels';
import { SunburstSegment } from '../../components/charts/sunburst-segment';
import { buildArcs } from '../../components/charts/sunburst-utils';
import { API_ENDPOINTS, apiRequest, clearToken } from '../../config/api';
import Sidebar from '../../components/Sidebar/Sidebar';
import { RISK_COLORS } from '../../constants/geneticRisk';
import './Biomarcadores.css';

const EMPTY_VALUE = 'No disponible';
const MISSING_VALUE_LABELS = {
  '': 'Vacío',
  'n/d': 'n/d',
  'n.d.': 'n.d.',
  'n.a.': 'n.a.',
  'n/a': 'n/a',
  na: 'na',
  '-': '-',
};

const RISK_LABELS = {
  alto: 'Riesgo alto',
  medio: 'Riesgo medio',
  bajo: 'Riesgo bajo',
};



const RISK_TEXT_COLORS = {
  alto: '#9f2f2f',
  medio: '#855d08',
  bajo: '#12613c',
  unknown: '#465256',
};

const RISK_GROUP_ORDER = ['alto', 'medio', 'bajo'];
const RISK_ALIASES = {
  alto: 'alto',
  high: 'alto',
  'high risk': 'alto',
  'riesgo alto': 'alto',
  medio: 'medio',
  medium: 'medio',
  'medium risk': 'medio',
  'riesgo medio': 'medio',
  bajo: 'bajo',
  low: 'bajo',
  'low risk': 'bajo',
  'riesgo bajo': 'bajo',
};

const hasValue = (value) => {
  if (value === null || value === undefined) return false;
  if (typeof value !== 'string') return true;
  const normalizedValue = value.trim().toLowerCase();
  return normalizedValue !== '' && !Object.prototype.hasOwnProperty.call(MISSING_VALUE_LABELS, normalizedValue);
};

const displayValue = (value, fallback = EMPTY_VALUE) => {
  if (value === null || value === undefined) return fallback;
  if (typeof value === 'string') {
    const trimmedValue = value.trim();
    if (Object.prototype.hasOwnProperty.call(MISSING_VALUE_LABELS, trimmedValue.toLowerCase())) {
      return fallback;
    }
    return trimmedValue || fallback;
  }
  if (typeof value === 'object') {
    try {
      return JSON.stringify(value) || fallback;
    } catch {
      return fallback;
    }
  }
  return String(value);
};

const firstAvailable = (...values) => values.find((value) => hasValue(value));

const formatFrequency = (value, emptyLabel = EMPTY_VALUE) => {
  if (!hasValue(value)) return emptyLabel;
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return emptyLabel;
  const percent = parsed <= 1 ? parsed * 100 : parsed;
  return `${percent.toFixed(2)}%`;
};

const formatFrequencyValue = (value) => {
  if (!hasValue(value)) return EMPTY_VALUE;
  const isNumeric = typeof value === 'number'
    || (typeof value === 'string' && value.trim() !== '' && Number.isFinite(Number(value)));
  return isNumeric ? formatFrequency(value) : displayValue(value);
};

const getUserResult = (biomarker) => biomarker?.userResult || biomarker?.user_result || {};

const getRiskKey = (risk) => {
  const normalizedRisk = String(risk || '').trim().toLowerCase();
  return RISK_ALIASES[normalizedRisk] || 'unknown';
};

const getRiskLabel = (risk) => RISK_LABELS[getRiskKey(risk)] || 'Riesgo no determinado';
const getRiskTextColor = (risk) => RISK_TEXT_COLORS[getRiskKey(risk)];
const formatRecordCount = (count) => `${count} ${Number(count) === 1 ? 'registro' : 'registros'}`;

const getMagnitudeLabel = (magnitude) => {
  if (!hasValue(magnitude)) return EMPTY_VALUE;

  const normalizedMagnitude = String(magnitude).trim().toLowerCase();
  if (normalizedMagnitude.includes('muy alto') || normalizedMagnitude.includes('muy alta')) return 'Muy alta';
  if (normalizedMagnitude.includes('alto') || normalizedMagnitude.includes('alta')) return 'Alta';
  if (normalizedMagnitude.includes('medio') || normalizedMagnitude.includes('media')) return 'Media';
  if (normalizedMagnitude.includes('bajo') || normalizedMagnitude.includes('baja')) return 'Baja';

  const parsedMagnitude = Number(magnitude);
  if (!Number.isNaN(parsedMagnitude)) {
    if (parsedMagnitude <= 0) return 'Sin magnitud';
    if (parsedMagnitude < 1.5) return 'Baja';
    if (parsedMagnitude < 2.5) return 'Media';
    if (parsedMagnitude < 4) return 'Alta';
    return 'Muy alta';
  }

  return displayValue(magnitude);
};

const getCurrentGenotype = (biomarker) => {
  const result = getUserResult(biomarker);
  return firstAvailable(result.genotype, biomarker?.userGenotype);
};

const getAlleleData = (alleles) => {
  if (Array.isArray(alleles)) {
    return { reference: alleles[0], alternate: alleles[1] };
  }

  if (alleles && typeof alleles === 'object') {
    return {
      reference: firstAvailable(alleles.ref, alleles.reference, alleles.reference_allele, alleles.ref_allele),
      alternate: firstAvailable(alleles.alt, alleles.alternate, alleles.alternate_allele, alleles.alt_allele),
    };
  }

  if (hasValue(alleles)) {
    const alleleParts = String(alleles).split(/\s*(?:\/|\||>|->|,)\s*/).filter(Boolean);
    return { reference: alleleParts[0], alternate: alleleParts[1] };
  }

  return { reference: null, alternate: null };
};

const getEntityKey = (entity, index, fallback) => {
  const entityValue = firstAvailable(entity?.id, entity?.rsid, entity?.name);
  return `${entityValue === undefined ? fallback : String(entityValue)}-${index}`;
};

function RiskBadge({ risk }) {
  return (
    <span
      className="biomarker-console__risk-badge"
      style={{ '--risk-text-color': getRiskTextColor(risk) }}
    >
      {getRiskLabel(risk)}
    </span>
  );
}

function DetailField({ label, value }) {
  return (
    <div className="biomarker-console__field">
      <dt className="biomarker-console__field-label">{label}</dt>
      <dd className="biomarker-console__field-value">{value}</dd>
    </div>
  );
}

function LoadingSkeleton() {
  return (
    <div className="biomarker-console__loading" role="status" aria-live="polite">
      <p>Cargando biomarcadores...</p>
      <div className="biomarker-console__loading-panel" aria-hidden="true">
        <span className="biomarker-console__skeleton-line biomarker-console__skeleton-line--eyebrow" />
        <span className="biomarker-console__skeleton-line biomarker-console__skeleton-line--title" />
        <span className="biomarker-console__skeleton-line biomarker-console__skeleton-line--chart" />
      </div>
    </div>
  );
}

function Breadcrumbs({ view, risk, record, onOverview, onRisk }) {
  const isOverview = view === 'overview';
  const riskLabel = RISK_LABELS[risk] || 'Riesgo no determinado';

  return (
    <nav className="biomarker-console__breadcrumbs" aria-label="Ruta de biomarcadores">
      <ol>
        <li>
          {isOverview ? (
            <span aria-current="page">Biomarcadores</span>
          ) : (
            <button type="button" onClick={onOverview}>Biomarcadores</button>
          )}
        </li>
        {!isOverview && <li aria-hidden="true"><ChevronRight size={14} /></li>}
        {view === 'risk' && <li aria-current="page">{riskLabel}</li>}
        {view === 'detail' && (
          <>
            <li><button type="button" onClick={onRisk}>{riskLabel}</button></li>
            <li aria-hidden="true"><ChevronRight size={14} /></li>
            <li aria-current="page">{displayValue(record?.rsid)}</li>
          </>
        )}
      </ol>
    </nav>
  );
}

function RiskLegendButton({ onSelectRisk, onHoverChange }) {
  const { item, index, isHovered } = useLegendItem();
  const riskKey = item.riskKey;
  const stateClasses = [
    'biomarker-console__risk-legend-item',
    isHovered && 'biomarker-console__risk-legend-item--hovered',
  ].filter(Boolean).join(' ');

  return (
    <button
      type="button"
      className={stateClasses}
      onClick={() => onSelectRisk(riskKey)}
      onFocus={() => onHoverChange(index)}
      onBlur={() => onHoverChange(null)}
      aria-describedby="biomarker-risk-chart-status"
      aria-label={`Ver ${item.label}`}
    >
      <LegendMarker className="biomarker-console__risk-legend-marker" />
      <LegendLabel className="biomarker-console__risk-legend-label" />
    </button>
  );
}

function RiskOverview({ chartData, riskGroups, records, knownCount, unknownCount, headingRef, onSelectRisk, onSelectRecord, shouldReduceMotion }) {
  const chartDescription = `Distribución de ${knownCount} ${knownCount === 1 ? 'registro' : 'registros'} clasificados por riesgo, con variantes anidadas para explorar cada resultado.`;
  const chartArcs = useMemo(() => buildArcs(chartData).arcs, [chartData]);
  const [hoveredChartIndex, setHoveredChartIndex] = useState(null);
  const legendItems = useMemo(() => riskGroups.map((group) => ({
    label: group.label,
    color: RISK_COLORS[group.key],
    riskKey: group.key,
  })), [riskGroups]);
  const riskArcIndexByKey = useMemo(() => new Map(
    chartArcs
      .filter((arc) => arc.depth === 1)
      .map((arc) => [getRiskKey(arc.name), arc.arcIndex]),
  ), [chartArcs]);
  const hoveredArc = hoveredChartIndex == null ? null : chartArcs[hoveredChartIndex] || null;
  const hoveredRiskKey = hoveredArc
    ? getRiskKey(hoveredArc.depth === 1 ? hoveredArc.name : hoveredArc.trail?.[1])
    : null;
  const hoveredLegendCandidate = hoveredRiskKey
    ? riskGroups.findIndex((group) => group.key === hoveredRiskKey)
    : -1;
  const hoveredLegendIndex = hoveredLegendCandidate >= 0 ? hoveredLegendCandidate : null;
  const centerSummary = hoveredArc
    ? hoveredArc.depth === 1
      ? { label: getRiskLabel(hoveredArc.name), value: formatRecordCount(hoveredArc.value) }
      : { label: hoveredArc.name, value: formatRecordCount(hoveredArc.value) }
    : { label: 'Biomarcadores', value: formatRecordCount(knownCount) };
  const hoveredStatus = hoveredArc
    ? hoveredArc.depth === 1
      ? `${getRiskLabel(hoveredArc.name)}: ${formatRecordCount(hoveredArc.value)}`
      : `${getRiskLabel(hoveredArc.trail?.[1])}: Variante ${hoveredArc.name} (${formatRecordCount(hoveredArc.value)})`
    : 'Resumen por nivel de riesgo';

  const handleChartHoverChange = (index) => {
    setHoveredChartIndex(index == null ? null : index);
  };

  const handleLegendHoverChange = (index) => {
    if (index == null) {
      setHoveredChartIndex(null);
      return;
    }
    const riskGroup = riskGroups[index];
    setHoveredChartIndex(riskGroup ? riskArcIndexByKey.get(riskGroup.key) ?? null : null);
  };

  const handleSegmentClick = (arc) => {
    if (arc.depth > 1 && arc.variantKey) {
      const record = records.find((candidate) => candidate.key === arc.variantKey);
      if (record) onSelectRecord(record);
      return;
    }
    if (arc.depth !== 1) return;
    const riskKey = getRiskKey(arc.name);
    if (RISK_GROUP_ORDER.includes(riskKey)) onSelectRisk(riskKey);
  };

  return (
    <section className="biomarker-console__panel biomarker-console__risk-overview" aria-labelledby="risk-overview-title">
      <div className="biomarker-console__panel-heading">
        <div>
          <p className="biomarker-console__panel-label">Resumen de riesgo</p>
          <h2 id="risk-overview-title" ref={headingRef} tabIndex="-1">Riesgo en tus biomarcadores</h2>
        </div>
        <span className="biomarker-console__panel-count">
          {knownCount} {knownCount === 1 ? 'registro clasificado' : 'registros clasificados'}
        </span>
      </div>
      <p className="biomarker-console__risk-overview-description">
        Selecciona un nivel para revisar únicamente sus resultados.
      </p>
      <div className="biomarker-console__risk-overview-body">
        <div className="biomarker-console__risk-chart">
          <div
            id="biomarker-risk-chart-status"
            className="biomarker-console__risk-chart-status biomarker-console__sr-only"
            role="status"
            aria-live="polite"
            aria-atomic="true"
          >
            <span className="biomarker-console__risk-chart-status-label">Ubicación en el gráfico</span>
            <strong>{hoveredStatus}</strong>
          </div>
          {knownCount > 0 ? (
            <div
              className="biomarker-console__risk-chart-visual"
              role="img"
              aria-label={chartDescription}
              aria-describedby="biomarker-risk-chart-status"
            >
              <SunburstChart
                className="biomarker-console__sunburst"
                data={chartData}
                hoveredIndex={hoveredChartIndex}
                onHoverChange={handleChartHoverChange}
                size={380}
                padding={8}
              >
                {chartArcs.map((arc) => (
                  <SunburstSegment
                    key={arc.id}
                    index={arc.arcIndex}
                    onClick={handleSegmentClick}
                  />
                ))}
                <SunburstCenter
                  className="biomarker-console__sunburst-center"
                  label={centerSummary.label}
                  value={centerSummary.value}
                />
                <SunburstLabels fill="transparent" stroke="none" strokeWidth={0} />
                <SunburstHint className="biomarker-console__sunburst-hint">
                  {({ hoveredArc: hintHoveredArc, focus }) => {
                    const feedbackKey = hintHoveredArc?.depth === 1
                      ? `risk-${getRiskKey(hintHoveredArc.name)}`
                      : hintHoveredArc?.depth > 1
                        ? `variant-${hintHoveredArc.variantKey ?? hintHoveredArc.id ?? hintHoveredArc.name}`
                        : 'idle';
                    let feedbackContent;

                    if (hintHoveredArc?.depth === 1) {
                      const riskKey = getRiskKey(hintHoveredArc.name);
                      feedbackContent = (
                        <div className="biomarker-console__sunburst-feedback-heading">
                          <span className="biomarker-console__sunburst-feedback-kicker">Riesgo</span>
                          <strong>{getRiskLabel(riskKey)}</strong>
                          <span className="biomarker-console__sunburst-feedback-count">
                            {formatRecordCount(hintHoveredArc.value)}
                          </span>
                        </div>
                      );
                    } else if (hintHoveredArc?.depth > 1) {
                      const hoveredRecord = records.find(
                        (record) => record.key === hintHoveredArc.variantKey,
                      );
                      const riskKey = getRiskKey(
                        hintHoveredArc.riskKey || hintHoveredArc.trail?.[1],
                      );
                      const genotype = hoveredRecord?.genotype;
                      const phenotype = hoveredRecord?.phenotype;

                      feedbackContent = (
                        <>
                          <div className="biomarker-console__sunburst-feedback-heading">
                            <span className="biomarker-console__sunburst-feedback-kicker">Variante</span>
                            <strong className="biomarker-console__sunburst-feedback-name">
                              {hintHoveredArc.name}
                            </strong>
                            <span className="biomarker-console__sunburst-feedback-count">
                              {formatRecordCount(hintHoveredArc.value)}
                            </span>
                          </div>
                          <div className="biomarker-console__sunburst-feedback-meta">
                            <span>
                              <strong>Riesgo</strong> {getRiskLabel(riskKey)}
                            </span>
                            {hasValue(genotype) && (
                              <span>
                                <strong>Genotipo</strong> {displayValue(genotype)}
                              </span>
                            )}
                            {hasValue(phenotype) && (
                              <span>
                                <strong>Fenotipo</strong> {displayValue(phenotype)}
                              </span>
                            )}
                          </div>
                          <p className="biomarker-console__sunburst-feedback-instruction">
                            Haz clic en la variante para abrir el detalle.
                          </p>
                        </>
                      );
                    } else {
                      feedbackContent = (
                        <span className="biomarker-console__sunburst-feedback-prompt">
                          {focus.depth > 0
                            ? 'Selecciona el centro para volver.'
                            : 'Selecciona un segmento para explorar.'}
                        </span>
                      );
                    }

                    return (
                      <div className="biomarker-console__sunburst-feedback-reserve">
                        <AnimatePresence initial={false} mode="wait">
                          <Motion.div
                            key={feedbackKey}
                            className="biomarker-console__sunburst-feedback"
                            initial={{ opacity: 0, y: shouldReduceMotion ? 0 : 4 }}
                            animate={{ opacity: 1, y: 0 }}
                            exit={{ opacity: 0, y: shouldReduceMotion ? 0 : -4 }}
                            transition={{
                              duration: shouldReduceMotion ? 0.12 : 0.18,
                              ease: [0.22, 1, 0.36, 1],
                            }}
                          >
                            {feedbackContent}
                          </Motion.div>
                        </AnimatePresence>
                      </div>
                    );
                  }}
                </SunburstHint>
              </SunburstChart>
            </div>
          ) : (
            <p className="biomarker-console__risk-chart-empty">
              Aún no hay registros con un nivel de riesgo disponible.
            </p>
          )}
        </div>
        <Legend
          items={legendItems}
          hoveredIndex={hoveredLegendIndex}
          onHoverChange={handleLegendHoverChange}
          className="biomarker-console__risk-legend"
        >
          <LegendItem className="biomarker-console__risk-legend-row">
            <RiskLegendButton
              onSelectRisk={onSelectRisk}
              onHoverChange={handleLegendHoverChange}
            />
          </LegendItem>
        </Legend>
      </div>
      {unknownCount > 0 && (
        <p className="biomarker-console__risk-note" role="status">
          <Info size={16} aria-hidden="true" />
          <span>{unknownCount} {unknownCount === 1 ? 'registro no tiene' : 'registros no tienen'} un nivel de riesgo reconocido y no se incluye en el gráfico.</span>
        </p>
      )}
    </section>
  );
}

function RiskTable({ risk, records, headingRef, onSelectRecord }) {
  const riskRecords = records.filter((record) => record.riskKey === risk);
  const riskLabel = RISK_LABELS[risk] || 'Riesgo no determinado';

  const handleRowKeyDown = (event, record) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      onSelectRecord(record);
    }
  };

  return (
    <section className="biomarker-console__panel biomarker-console__risk-table-panel" aria-labelledby="risk-table-title">
      <div className="biomarker-console__panel-heading">
        <div>
          <p className="biomarker-console__panel-label">Resultados filtrados</p>
          <h2 id="risk-table-title" ref={headingRef} tabIndex="-1">{riskLabel}</h2>
        </div>
        <span className="biomarker-console__panel-count">
          {riskRecords.length} {riskRecords.length === 1 ? 'registro' : 'registros'}
        </span>
      </div>
      {riskRecords.length > 0 ? (
        <div className="biomarker-console__table-wrap">
          <table className="biomarker-console__risk-table">
            <caption className="biomarker-console__sr-only">Resultados clasificados como {riskLabel.toLowerCase()}</caption>
            <thead>
              <tr>
                <th scope="col">rsID</th>
                <th scope="col">Fenotipo</th>
                <th scope="col">Genotipo</th>
              </tr>
            </thead>
            <tbody>
              {riskRecords.map((record) => (
                <tr
                  key={record.key}
                  tabIndex="0"
                  role="button"
                  aria-label={`Abrir detalle de ${displayValue(record.rsid)}`}
                  onClick={() => onSelectRecord(record)}
                  onKeyDown={(event) => handleRowKeyDown(event, record)}
                >
                  <td>{displayValue(record.rsid)}</td>
                  <td>{displayValue(record.phenotype, 'Fenotipo no disponible')}</td>
                  <td>{displayValue(record.genotype, 'Genotipo no disponible')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="biomarker-console__empty">No hay registros disponibles para este nivel de riesgo.</p>
      )}
    </section>
  );
}

function DetailView({ record, headingRef }) {
  const alleleData = getAlleleData(record?.alleles);
  const referenceAllele = firstAvailable(alleleData.reference, record?.referenceAllele);
  const alternateAllele = firstAvailable(alleleData.alternate, record?.alternateAllele);

  return (
    <section className="biomarker-console__panel biomarker-console__detail-panel" aria-labelledby="biomarker-detail-title">
      <div className="biomarker-console__panel-heading biomarker-console__detail-heading">
        <div>
          <p className="biomarker-console__panel-label">Detalle del resultado</p>
          <h2 id="biomarker-detail-title" ref={headingRef} tabIndex="-1">{displayValue(record?.rsid)}</h2>
        </div>
        <RiskBadge risk={record?.risk} />
      </div>
      <dl className="biomarker-console__detail-grid">
        <DetailField label="Cromosoma" value={displayValue(record?.chromosome)} />
        <DetailField label="Posición" value={displayValue(record?.position)} />
        <DetailField label="Alelo de referencia" value={displayValue(referenceAllele)} />
        <DetailField label="Alelo alternativo" value={displayValue(alternateAllele)} />
        <DetailField label="Frecuencia Chile" value={formatFrequencyValue(record?.chileFrequency)} />
        <DetailField label="Magnitud" value={getMagnitudeLabel(record?.magnitude)} />
        <DetailField label="Continente" value={displayValue(record?.continent)} />
        <DetailField label="País" value={displayValue(record?.country)} />
      </dl>
    </section>
  );
}

const Biomarcadores = () => {
  const [user, setUser] = useState(null);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [isMobile, setIsMobile] = useState(false);
  const [biomarkers, setBiomarkers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [view, setView] = useState('overview');
  const [selectedRisk, setSelectedRisk] = useState(null);
  const [selectedRecord, setSelectedRecord] = useState(null);
  const headingRef = useRef(null);
  const navigate = useNavigate();
  const shouldReduceMotion = useReducedMotion() === true;
  const activeViewKey = view === 'overview'
    ? 'overview'
    : view === 'risk'
      ? `risk-${selectedRisk ?? 'unknown'}`
      : `detail-${selectedRecord?.key ?? 'unknown'}`;
  const activeViewKeyRef = useRef(activeViewKey);
  const previousViewKeyRef = useRef(null);
  const shouldFocusHeadingRef = useRef(false);
  activeViewKeyRef.current = activeViewKey;

  const fetchBiomarkers = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await apiRequest(API_ENDPOINTS.BIOMARKERS, { method: 'GET' });
      if (response.ok && response.data) {
        setBiomarkers(Array.isArray(response.data.biomarkers) ? response.data.biomarkers : []);
      } else {
        setError('No pudimos cargar tus biomarcadores.');
      }
    } catch {
      setError('Error de conexión al cargar biomarcadores.');
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchUser = useCallback(async () => {
    try {
      const response = await apiRequest(API_ENDPOINTS.ME, { method: 'GET' });
      if (response.ok && response.data) {
        setUser(response.data.user || response.data);
      }
    } catch {
      // The dashboard can still render its biomarker results without the profile response.
    }
  }, []);

  useEffect(() => {
    fetchUser();
    fetchBiomarkers();
  }, [fetchBiomarkers, fetchUser]);

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

  useEffect(() => {
    if (previousViewKeyRef.current === null) {
      previousViewKeyRef.current = activeViewKey;
      return;
    }

    if (previousViewKeyRef.current !== activeViewKey) {
      previousViewKeyRef.current = activeViewKey;
      shouldFocusHeadingRef.current = true;
    }
  }, [activeViewKey]);

  const handleViewAnimationComplete = (completedViewKey) => {
    if (!shouldFocusHeadingRef.current || activeViewKeyRef.current !== completedViewKey) return;
    shouldFocusHeadingRef.current = false;
    headingRef.current?.focus();
  };

  const handleLogout = async () => {
    try {
      await apiRequest(API_ENDPOINTS.LOGOUT, { method: 'POST' });
    } catch (logoutError) {
      console.error('Error al cerrar sesión', logoutError);
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

  const normalizedRecords = useMemo(() => biomarkers.map((biomarker, sourceIndex) => {
    const result = getUserResult(biomarker);
    const alleleData = getAlleleData(biomarker?.alleles);

    return {
      key: getEntityKey(biomarker, sourceIndex, 'biomarcador'),
      biomarker,
      rsid: firstAvailable(biomarker?.rsid, biomarker?.id),
      phenotype: firstAvailable(result.phenotype, biomarker?.phenotype),
      genotype: getCurrentGenotype(biomarker),
      risk: result.risk,
      riskKey: getRiskKey(result.risk),
      magnitude: firstAvailable(result.magnitude, biomarker?.magnitude),
      chileFrequency: firstAvailable(biomarker?.freq_chile_percent, result.frequency),
      continent: firstAvailable(result.continent, biomarker?.continent),
      country: firstAvailable(result.country, biomarker?.country),
      chromosome: firstAvailable(biomarker?.chromosome, biomarker?.cromosoma),
      position: firstAvailable(biomarker?.position, biomarker?.posicion),
      alleles: biomarker?.alleles,
      referenceAllele: firstAvailable(alleleData.reference, biomarker?.reference_allele),
      alternateAllele: firstAvailable(alleleData.alternate, biomarker?.alternate_allele),
    };
  }), [biomarkers]);

  const riskGroups = useMemo(() => RISK_GROUP_ORDER.map((key) => ({
    key,
    label: RISK_LABELS[key],
    count: normalizedRecords.filter((record) => record.riskKey === key).length,
  })), [normalizedRecords]);

  const knownCount = useMemo(
    () => riskGroups.reduce((total, group) => total + group.count, 0),
    [riskGroups],
  );

  const unknownCount = normalizedRecords.length - knownCount;

  const chartData = useMemo(() => ({
    name: 'Biomarcadores',
    value: knownCount,
    chartNodeType: 'root',
    children: riskGroups.map((group) => {
      const variants = normalizedRecords
        .filter((record) => record.riskKey === group.key)
        .map((record) => ({
          name: displayValue(record.rsid, record.key),
          value: 1,
          fill: RISK_COLORS[group.key],
          riskKey: group.key,
          chartNodeType: 'variant',
          variantKey: record.key,
          rsid: record.rsid,
          phenotype: record.phenotype,
          genotype: record.genotype,
          magnitude: record.magnitude,
          chileFrequency: record.chileFrequency,
        }));

      return {
        name: group.label,
        value: variants.length,
        fill: RISK_COLORS[group.key],
        riskKey: group.key,
        chartNodeType: 'risk',
        children: variants,
      };
    }),
  }), [knownCount, normalizedRecords, riskGroups]);

  const openRisk = (risk) => {
    if (!RISK_GROUP_ORDER.includes(risk)) return;
    setSelectedRisk(risk);
    setSelectedRecord(null);
    setView('risk');
  };

  const openRecord = (record) => {
    if (RISK_GROUP_ORDER.includes(record?.riskKey)) setSelectedRisk(record.riskKey);
    setSelectedRecord(record);
    setView('detail');
  };

  const openOverview = () => {
    setView('overview');
    setSelectedRisk(null);
    setSelectedRecord(null);
  };

  const openSelectedRisk = () => {
    if (!selectedRisk) return;
    setSelectedRecord(null);
    setView('risk');
  };

  return (
    <div className="dashboard biomarker-dashboard">
      {isMobile && (
        <button
          type="button"
          className="dashboard__burger"
          onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
          aria-label={isMobileMenuOpen ? 'Cerrar menú de navegación' : 'Abrir menú de navegación'}
          aria-expanded={isMobileMenuOpen}
        >
          {isMobileMenuOpen ? <X size={22} aria-hidden="true" /> : <Menu size={22} aria-hidden="true" />}
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

      <main className="dashboard__main" aria-busy={loading}>
        <div className="biomarker-console">
          <header className="biomarker-console__header">
            <h1 className="biomarker-console__title">
              <span className="biomarker-console__title-bio">Bio</span><span className="biomarker-console__title-rest">marcadores</span>
            </h1>
            <p>Revisa los registros genéticos asociados a tu perfil y explóralos por nivel de riesgo.</p>
          </header>

          {view !== 'overview' && (
            <Breadcrumbs
              view={view}
              risk={selectedRisk}
              record={selectedRecord}
              onOverview={openOverview}
              onRisk={openSelectedRisk}
            />
          )}

          {loading && <LoadingSkeleton />}

          {!loading && error && (
            <div className="biomarker-console__state biomarker-console__state--error" role="alert" aria-live="assertive">
              <p>{error}</p>
              <button type="button" onClick={fetchBiomarkers}>Reintentar</button>
            </div>
          )}

          {!loading && !error && (
            <AnimatePresence initial={false} mode="wait">
              <Motion.div
                key={activeViewKey}
                className="biomarker-console__view-transition"
                initial={{ opacity: 0, y: shouldReduceMotion ? 0 : 6 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: shouldReduceMotion ? 0 : -6 }}
                transition={{
                  duration: shouldReduceMotion ? 0.16 : 0.22,
                  ease: [0.22, 1, 0.36, 1],
                }}
                onAnimationComplete={() => handleViewAnimationComplete(activeViewKey)}
              >
                {view === 'overview' && (
                  <RiskOverview
                    chartData={chartData}
                    riskGroups={riskGroups}
                    records={normalizedRecords}
                    knownCount={knownCount}
                    unknownCount={unknownCount}
                    headingRef={headingRef}
                    onSelectRisk={openRisk}
                    onSelectRecord={openRecord}
                    shouldReduceMotion={shouldReduceMotion}
                  />
                )}

                {!loading && !error && view === 'risk' && selectedRisk && (
                  <RiskTable
                    risk={selectedRisk}
                    records={normalizedRecords}
                    headingRef={headingRef}
                    onSelectRecord={openRecord}
                  />
                )}

                {!loading && !error && view === 'detail' && selectedRecord && (
                  <DetailView record={selectedRecord} headingRef={headingRef} />
                )}
              </Motion.div>
            </AnimatePresence>
          )}
        </div>
      </main>
    </div>
  );
};

export default Biomarcadores;
