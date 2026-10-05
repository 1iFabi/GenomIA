/*
 * Adapted from Bklit UI's Ring Chart registry component (MIT).
 * Source: https://ui.bklit.com/r/ring-chart.json
 */
import { Group } from '@visx/group';
import { memo, useCallback, useMemo, useRef, useState } from 'react';
import { cn } from '@/lib/utils';
import { DEFAULT_CHART_ENTER_TRANSITION } from './animation';
import { defaultRingColors, RingProvider } from './ring-context';

function RingChartInner({
  data,
  size,
  strokeWidthProp,
  ringGapProp,
  baseInnerRadiusProp,
  children,
  containerRef,
  hoveredIndexProp,
  onHoverChange,
  startAngle,
  endAngle,
  enterTransition,
  enterStaggerScale,
  reducedMotion,
  selectedCode,
  onSelect,
}) {
  const [internalHoveredIndex, setInternalHoveredIndex] = useState(null);
  const hoveredIndex = hoveredIndexProp === undefined ? internalHoveredIndex : hoveredIndexProp;
  const setHoveredIndex = useCallback((index) => {
    onHoverChange?.(index);
    if (hoveredIndexProp === undefined) setInternalHoveredIndex(index);
  }, [hoveredIndexProp, onHoverChange]);

  const center = size / 2;
  const availableRadius = center - 8;
  const designOuterRadius = baseInnerRadiusProp
    + (data.length - 1) * (strokeWidthProp + ringGapProp)
    + strokeWidthProp;
  const scale = Math.min(1, availableRadius / designOuterRadius);
  const strokeWidth = strokeWidthProp * scale;
  const ringGap = ringGapProp * scale;
  const baseInnerRadius = baseInnerRadiusProp * scale;

  const getColor = useCallback((index) => (
    data[index]?.color || defaultRingColors[index % defaultRingColors.length]
  ), [data]);
  const getRingRadii = useCallback((index) => {
    const innerRadius = baseInnerRadius + index * (strokeWidth + ringGap);
    return { innerRadius, outerRadius: innerRadius + strokeWidth };
  }, [baseInnerRadius, strokeWidth, ringGap]);
  const contextValue = useMemo(() => ({
    data,
    size,
    center,
    strokeWidth,
    ringGap,
    baseInnerRadius,
    hoveredIndex,
    setHoveredIndex,
    animationKey: 0,
    isLoaded: true,
    enterTransition: reducedMotion ? { duration: 0 } : (enterTransition || DEFAULT_CHART_ENTER_TRANSITION),
    enterStaggerScale,
    containerRef,
    getColor,
    getRingRadii,
    startAngle,
    endAngle,
    reducedMotion,
    selectedCode,
    onSelect,
    onHoverChange,
  }), [
    data, size, center, strokeWidth, ringGap, baseInnerRadius, hoveredIndex,
    setHoveredIndex, enterTransition, enterStaggerScale, containerRef,
    getColor, getRingRadii, startAngle, endAngle, reducedMotion,
    selectedCode, onSelect, onHoverChange,
  ]);

  return (
    <RingProvider value={contextValue}>
      <svg
        className="bklit-ring-chart__svg"
        width={size}
        height={size}
        viewBox={`0 0 ${size} ${size}`}
        role="group"
        aria-label="Porcentajes de ancestría por país"
      >
        <title>Porcentajes de ancestría por país</title>
        <Group left={center} top={center}>{children}</Group>
      </svg>
    </RingProvider>
  );
}

export function RingChart({
  data,
  size = 240,
  strokeWidth = 8,
  ringGap = 5,
  baseInnerRadius = 27,
  className = '',
  hoveredIndex,
  onHoverChange,
  startAngle = -Math.PI / 2,
  endAngle = (3 * Math.PI) / 2,
  enterTransition,
  enterStaggerScale = 1,
  reducedMotion = false,
  selectedCode = null,
  onSelect,
  children,
}) {
  const containerRef = useRef(null);
  return (
    <div
      className={cn('bklit-ring-chart', className)}
      ref={containerRef}
      style={{ width: size, height: size }}
    >
      <RingChartInner
        baseInnerRadiusProp={baseInnerRadius}
        containerRef={containerRef}
        data={data}
        endAngle={endAngle}
        enterStaggerScale={enterStaggerScale}
        enterTransition={enterTransition}
        hoveredIndexProp={hoveredIndex}
        onHoverChange={onHoverChange}
        onSelect={onSelect}
        reducedMotion={reducedMotion}
        ringGapProp={ringGap}
        selectedCode={selectedCode}
        size={size}
        startAngle={startAngle}
        strokeWidthProp={strokeWidth}
      >
        {children}
      </RingChartInner>
    </div>
  );
}

export default memo(RingChart);
