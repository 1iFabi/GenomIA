import { useState } from 'react';
import { ChevronDown, AlertCircle, AlertTriangle, Info } from 'lucide-react';
import { cn } from '../../lib/utils';
import GeneticTraitBar from '../GeneticTraitBar/GeneticTraitBar';
import './PriorityCard.css';

const priorityConfig = {
  high: {
    icon: AlertCircle,
  },
  medium: {
    icon: AlertTriangle,
  },
  low: {
    icon: Info,
  },
};

const impactColors = {
  high: '#8b5cf6',
  medium: '#06b6d4',
  low: '#f59e0b',
};

const impactLabels = {
  high: 'Alto',
  medium: 'Medio',
  low: 'Bajo',
};

const PriorityCard = ({ level, title, diseases, defaultExpanded = false }) => {
  const [isExpanded, setIsExpanded] = useState(defaultExpanded);
  const config = priorityConfig[level];
  const Icon = config.icon;
  const toggleId = `priority-card-${level}-toggle`;
  const bodyId = `priority-card-${level}-body`;

  return (
    <section
      className={cn('priority-card', `priority-card--${level}`)}
      aria-labelledby={toggleId}
    >
      <div className="priority-card__rail" aria-hidden="true" />
      <button
        type="button"
        id={toggleId}
        className="priority-card__toggle"
        onClick={() => setIsExpanded(!isExpanded)}
        aria-expanded={isExpanded}
        aria-controls={bodyId}
      >
        <span className="priority-card__summary">
          <span className="priority-card__icon" aria-hidden="true">
            <Icon className="priority-card__icon-glyph" />
          </span>
          <span className="priority-card__heading">
            <span className="priority-card__title">{title}</span>
            <span className="priority-card__count">
              {diseases.length}{' '}
              {diseases.length === 1 ? 'enfermedad' : 'enfermedades'}
            </span>
          </span>
        </span>
        <span className="priority-card__chevron" aria-hidden="true">
          <ChevronDown />
        </span>
      </button>

      {isExpanded && (
        <div
          id={bodyId}
          className="priority-card__body"
          role="region"
          aria-labelledby={toggleId}
        >
          <div className="priority-card__list">
            {diseases.length > 0 ? (
              diseases.map((disease, index) => {
                const magnitude = Number(disease.magnitud_efecto);
                const hasMagnitude = Number.isFinite(magnitude) && magnitude > 0;
                const percentage = hasMagnitude
                  ? Math.min(100, Math.round((magnitude / 5) * 100))
                  : level === 'high'
                    ? 80
                    : level === 'medium'
                      ? 55
                      : 30;
                return (
                  <GeneticTraitBar
                    key={disease.id}
                    title={disease.title}
                    rsid={disease.rsId || disease.rsid}
                    genotype={disease.genotype}
                    percentage={percentage}
                    impactLabel={impactLabels[level] || 'Bajo'}
                    impactColor={impactColors[level] || '#64748b'}
                    details={{
                      cromosoma: disease.cromosoma || 'N/A',
                      posicion: disease.posicion || 'N/A',
                      categoria: 'Enfermedades',
                      magnitud: hasMagnitude ? magnitude.toFixed(2) : 'N/A',
                    }}
                    freqChile={disease.freq_chile_percent}
                    explanation={disease.description || 'Sin descripcion disponible.'}
                    delay={index * 50}
                  />
                );
              })
            ) : (
              <p className="priority-card__empty">No hay enfermedades en esta categoría</p>
            )}
          </div>
        </div>
      )}
    </section>
  );
};

export default PriorityCard;
