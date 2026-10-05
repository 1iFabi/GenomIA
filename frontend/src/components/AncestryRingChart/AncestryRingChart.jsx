import React, { useEffect, useMemo, useState } from 'react';
import { RingChart } from '../bklit-ring-chart/ring-chart';
import { Ring } from '../bklit-ring-chart/ring';
import './AncestryRingChart.css';

const clampPercentage = (value) => {
  const numericValue = Number(value);
  if (!Number.isFinite(numericValue)) return 0;
  return Math.min(100, Math.max(0, numericValue));
};

const formatPercentage = (value) => `${clampPercentage(value).toFixed(1)}%`;

const usePrefersReducedMotion = () => {
  const [reducedMotion, setReducedMotion] = useState(() => (
    typeof window !== 'undefined'
      && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  ));

  useEffect(() => {
    const mediaQuery = window.matchMedia?.('(prefers-reduced-motion: reduce)');
    if (!mediaQuery) return undefined;
    const updatePreference = (event) => setReducedMotion(event.matches);
    mediaQuery.addEventListener?.('change', updatePreference);
    return () => mediaQuery.removeEventListener?.('change', updatePreference);
  }, []);

  return reducedMotion;
};

const AncestryRingChart = ({
  items = [],
  otherValue = 0,
  selectedCode = null,
  selectedItem = null,
  hoveredCode = null,
  onHoverChange,
  onSelect,
}) => {
  const reducedMotion = usePrefersReducedMotion();
  const ringItems = useMemo(() => [
    ...items.slice(0, 5).map((item) => ({
      ...item,
      label: item.name || 'País',
      value: clampPercentage(item.percentageValue ?? item.percentage),
      maxValue: 100,
      selectable: true,
      country: item,
    })),
    {
      isoCode: 'otros',
      label: 'Otros',
      value: clampPercentage(otherValue),
      maxValue: 100,
      color: '#aebdc3',
      selectable: false,
    },
  ], [items, otherValue]);

  const hoveredIndex = hoveredCode
    ? ringItems.findIndex((item) => item.isoCode === hoveredCode)
    : null;
  const activeItem = ringItems.find((item) => item.isoCode === hoveredCode)
    || ringItems.find((item) => item.isoCode === selectedCode)
    || selectedItem;

  return (
    <div className="ancestry-ring-chart">
      <RingChart
        className="ancestry-ring-chart__rings"
        data={ringItems}
        size={248}
        baseInnerRadius={29}
        strokeWidth={8}
        ringGap={4}
        hoveredIndex={hoveredIndex < 0 ? null : hoveredIndex}
        onHoverChange={(index) => onHoverChange?.(index === null ? null : ringItems[index]?.isoCode)}
        onSelect={onSelect}
        selectedCode={selectedCode}
        reducedMotion={reducedMotion}
      >
        {ringItems.map((item, index) => (
          <Ring key={item.isoCode || item.label} index={index} selectable={item.selectable} />
        ))}
      </RingChart>
      <div className="ancestry-ring-chart__center" aria-live="polite">
        <strong className="ancestry-ring-chart__center-value">
          {activeItem
            ? formatPercentage(activeItem.percentageValue ?? activeItem.value)
            : `${items.length}`}
        </strong>
        <span className="ancestry-ring-chart__center-name">
          {activeItem?.name || activeItem?.label || (items.length ? 'países' : 'Sin datos')}
        </span>
      </div>
      <p className="ancestry-ring-chart__caption">
        Los anillos muestran hasta cinco países y el agregado de los restantes.
      </p>
    </div>
  );
};

export default AncestryRingChart;
