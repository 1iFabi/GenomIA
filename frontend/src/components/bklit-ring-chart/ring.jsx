/*
 * Adapted from Bklit UI's Ring Chart registry component (MIT).
 * Source: https://ui.bklit.com/r/ring-chart.json
 */
import { arc as arcGenerator } from '@visx/shape';
import { motion, useTransform } from 'motion/react';
import { memo, useCallback } from 'react';
import { ringCssVars, useRingHover, useRingStable } from './ring-context';
import { useEnterComplete } from './use-enter-complete';
import { useMountProgress } from './use-mount-progress';

const MotionGroup = motion.g;
const MotionPath = motion.path;

function generateArcPath(innerRadius, outerRadius, startAngle, endAngle, cornerRadius) {
  const generator = arcGenerator({ innerRadius, outerRadius, cornerRadius });
  return generator({ startAngle, endAngle }) || '';
}

function formatRingLabel(ringData) {
  const value = Number(ringData?.value);
  const percentage = Number.isFinite(value) ? `${value.toFixed(1)}%` : 'Sin porcentaje';
  return `${ringData?.label || 'País'}: ${percentage}`;
}

export const Ring = memo(function Ring({
  index,
  color: colorProp,
  animate = true,
  showGlow = false,
  lineCap = 'round',
  selectable,
}) {
  const {
    data,
    getColor,
    getRingRadii,
    startAngle,
    endAngle,
    enterTransition,
    enterStaggerScale,
    animationKey,
    reducedMotion,
    selectedCode,
    onSelect,
  } = useRingStable();
  const { hoveredIndex, setHoveredIndex } = useRingHover();
  const ringData = data[index];
  const isSelectable = selectable ?? ringData?.selectable !== false;

  const expandDelay = index * 0.08 * enterStaggerScale;
  const expandProgress = useMountProgress(enterTransition, expandDelay, `${animationKey}-expand-${index}`);
  const expandComplete = useEnterComplete(expandProgress);
  const progressDelay = (0.6 + index * 0.1) * enterStaggerScale;
  const progressMount = useMountProgress(enterTransition, progressDelay, `${animationKey}-progress-${index}`);
  const progressComplete = useEnterComplete(progressMount);
  const progress = ringData ? Math.max(0, Math.min(1, ringData.value / ringData.maxValue)) : 0;
  const arcRange = endAngle - startAngle;

  const animatedProgressPath = useTransform(progressMount, (value) => {
    if (!ringData) return '';
    const currentEndAngle = startAngle + arcRange * progress * value;
    if (currentEndAngle <= startAngle + 0.01) return '';
    const radii = getRingRadii(index);
    const corner = lineCap === 'round' ? (radii.outerRadius - radii.innerRadius) / 2 : 0;
    return generateArcPath(radii.innerRadius, radii.outerRadius, startAngle, currentEndAngle, corner);
  });
  const enterScale = useTransform(expandProgress, [0, 1], [0, 1]);

  const handleMouseEnter = useCallback(() => setHoveredIndex(index), [index, setHoveredIndex]);
  const handleMouseLeave = useCallback(() => setHoveredIndex(null), [setHoveredIndex]);
  const handleSelect = useCallback((event) => {
    event.stopPropagation();
    if (isSelectable) onSelect?.(ringData?.country || ringData);
  }, [isSelectable, onSelect, ringData]);
  const handleKeyDown = useCallback((event) => {
    if (!isSelectable || (event.key !== 'Enter' && event.key !== ' ')) return;
    event.preventDefault();
    handleSelect(event);
  }, [handleSelect, isSelectable]);

  if (!ringData) return null;

  const { innerRadius, outerRadius } = getRingRadii(index);
  const color = colorProp || ringData.color || getColor(index);
  const isHovered = hoveredIndex === index;
  const isFaded = hoveredIndex !== null && hoveredIndex !== index;
  const isPushedOut = hoveredIndex !== null && hoveredIndex < index;
  const cornerRadius = lineCap === 'round' ? (outerRadius - innerRadius) / 2 : 0;
  const bgPath = generateArcPath(innerRadius, outerRadius, startAngle, endAngle, cornerRadius);
  const progressEndAngle = startAngle + arcRange * progress;
  const progressPath = progressEndAngle <= startAngle + 0.01
    ? ''
    : generateArcPath(innerRadius, outerRadius, startAngle, progressEndAngle, cornerRadius);
  const hoverScale = reducedMotion ? 1 : (isHovered ? 1.025 : (isPushedOut ? 1.015 : 1));
  const role = isSelectable ? 'button' : 'img';
  const selected = isSelectable && ringData.isoCode === selectedCode;
  const groupStyle = {
    cursor: isSelectable ? 'pointer' : 'default',
    transformOrigin: '0px 0px',
    filter: showGlow && isHovered ? `drop-shadow(0 0 8px ${color})` : 'none',
  };
  const enterDone = !animate || reducedMotion || (expandComplete && progressComplete);
  const groupProps = {
    'aria-label': formatRingLabel(ringData),
    'aria-pressed': isSelectable ? selected : undefined,
    'data-ring-index': index,
    onBlur: isSelectable ? handleMouseLeave : undefined,
    onClick: isSelectable ? handleSelect : undefined,
    onFocus: isSelectable ? handleMouseEnter : undefined,
    onKeyDown: isSelectable ? handleKeyDown : undefined,
    onMouseEnter: handleMouseEnter,
    onMouseLeave: handleMouseLeave,
    role,
    tabIndex: isSelectable ? 0 : undefined,
  };

  if (enterDone) {
    return (
      <MotionGroup
        {...groupProps}
        animate={{ scale: hoverScale, opacity: isFaded ? 0.42 : 1 }}
        className="bklit-ring-chart__ring"
        style={groupStyle}
        transition={reducedMotion ? { duration: 0 } : {
          scale: { type: 'spring', stiffness: 400, damping: 25 },
          opacity: { duration: 0.15 },
        }}
      >
        <path d={bgPath} fill={ringCssVars.ringBackground} />
        {progressPath ? <path d={progressPath} fill={color} /> : null}
      </MotionGroup>
    );
  }

  if (!expandComplete) {
    return (
      <MotionGroup
        {...groupProps}
        className="bklit-ring-chart__ring"
        style={{ ...groupStyle, scale: enterScale, opacity: isFaded ? 0.42 : 1 }}
      >
        <path d={bgPath} fill={ringCssVars.ringBackground} />
      </MotionGroup>
    );
  }

  return (
    <MotionGroup
      {...groupProps}
      animate={{ scale: hoverScale, opacity: isFaded ? 0.42 : 1 }}
      className="bklit-ring-chart__ring"
      style={groupStyle}
      transition={reducedMotion ? { duration: 0 } : {
        scale: { type: 'spring', stiffness: 400, damping: 25 },
        opacity: { duration: 0.15 },
      }}
    >
      <path d={bgPath} fill={ringCssVars.ringBackground} />
      <MotionPath d={animatedProgressPath} fill={color} />
    </MotionGroup>
  );
});

Ring.displayName = 'Ring';
export default Ring;
