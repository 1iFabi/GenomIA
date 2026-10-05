/*
 * Adapted from Bklit UI's Ring Chart registry component (MIT).
 * Source: https://ui.bklit.com/r/ring-chart.json
 */
/* eslint-disable react-refresh/only-export-components */
import { createContext, useContext, useMemo } from 'react';

export const ringCssVars = {
  ringBackground: 'var(--ancestry-ring-track, #e4e9eb)',
  ring1: 'var(--ancestry-ring-1, #9a654d)',
  ring2: 'var(--ancestry-ring-2, #01579b)',
  ring3: 'var(--ancestry-ring-3, #598a9d)',
  ring4: 'var(--ancestry-ring-4, #7b8793)',
  ring5: 'var(--ancestry-ring-5, #a78970)',
};

export const defaultRingColors = [
  ringCssVars.ring1,
  ringCssVars.ring2,
  ringCssVars.ring3,
  ringCssVars.ring4,
  ringCssVars.ring5,
];

const RingStableContext = createContext(null);
const RingHoverContext = createContext(null);

export function RingProvider({ children, value }) {
  const stable = useMemo(() => ({
    data: value.data,
    size: value.size,
    center: value.center,
    strokeWidth: value.strokeWidth,
    ringGap: value.ringGap,
    baseInnerRadius: value.baseInnerRadius,
    animationKey: value.animationKey,
    isLoaded: value.isLoaded,
    enterTransition: value.enterTransition,
    enterStaggerScale: value.enterStaggerScale,
    containerRef: value.containerRef,
    getColor: value.getColor,
    getRingRadii: value.getRingRadii,
    startAngle: value.startAngle,
    endAngle: value.endAngle,
    reducedMotion: value.reducedMotion,
    selectedCode: value.selectedCode,
    onSelect: value.onSelect,
  }), [value]);

  const hover = useMemo(() => ({
    hoveredIndex: value.hoveredIndex,
    setHoveredIndex: value.setHoveredIndex,
    onHoverChange: value.onHoverChange,
  }), [value.hoveredIndex, value.setHoveredIndex, value.onHoverChange]);

  return (
    <RingStableContext.Provider value={stable}>
      <RingHoverContext.Provider value={hover}>{children}</RingHoverContext.Provider>
    </RingStableContext.Provider>
  );
}

export function useRingStable() {
  const context = useContext(RingStableContext);
  if (!context) throw new Error('useRingStable must be used inside RingChart.');
  return context;
}

export function useRingHover() {
  const context = useContext(RingHoverContext);
  if (!context) throw new Error('useRingHover must be used inside RingChart.');
  return context;
}

export function useRing() {
  return { ...useRingStable(), ...useRingHover() };
}
