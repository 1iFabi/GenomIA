// Single source of truth for genetic risk → color/label mappings and impact levels.

// Risk level key → brand risk color.
export const RISK_COLORS = {
  alto: '#ef4444',
  medio: '#f59e0b',
  bajo: '#10b981',
};

// Mirrors Biometrics-style impact keys (high/medium/low) onto the level keys.
const IMPACT_KEY_TO_LEVEL = { high: 'alto', medium: 'medio', low: 'bajo' };

// Unified impact thresholds used by Farmacogenetica and SunburstChart.
export const getImpactLevel = (magnitud) => {
  if (magnitud >= 2.5) return 'alto';
  if (magnitud >= 1.5) return 'medio';
  return 'bajo';
};

export const getImpactLabel = (magnitud) => {
  const level = getImpactLevel(magnitud);
  if (level === 'alto') return 'Alto Impacto';
  if (level === 'medio') return 'Impacto Medio';
  return 'Bajo Impacto';
};

export const getImpactColor = (magnitud) => RISK_COLORS[getImpactLevel(magnitud)];

// Map an impact key ('high' | 'medium' | 'low') to its risk color.
export const impactColor = (impactKey) =>
  RISK_COLORS[IMPACT_KEY_TO_LEVEL[impactKey] || 'bajo'];
