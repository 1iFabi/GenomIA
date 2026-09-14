"use client";

import { useMemo } from "react";
import {
  PieHoverContext,
  PieStableContext,
} from "./pie-context-hooks";

export {
  defaultPieColors,
  pieCssVars,
} from "./pie-context-constants";
export {
  usePie,
  usePieHover,
  usePieStable,
} from "./pie-context-hooks";

export function PieProvider({
  children,
  value
}) {
  const stable = useMemo(() => ({
    data: value.data,
    arcs: value.arcs,
    size: value.size,
    center: value.center,
    outerRadius: value.outerRadius,
    innerRadius: value.innerRadius,
    padAngle: value.padAngle,
    cornerRadius: value.cornerRadius,
    hoverOffset: value.hoverOffset,
    animationKey: value.animationKey,
    isLoaded: value.isLoaded,
    enterTransition: value.enterTransition,
    enterStaggerScale: value.enterStaggerScale,
    containerRef: value.containerRef,
    totalValue: value.totalValue,
    getColor: value.getColor,
    getFill: value.getFill,
    geometryScrubbing: value.geometryScrubbing,
    scrubSlicePaths: value.scrubSlicePaths,
  }), [
    value.data,
    value.arcs,
    value.size,
    value.center,
    value.outerRadius,
    value.innerRadius,
    value.padAngle,
    value.cornerRadius,
    value.hoverOffset,
    value.animationKey,
    value.isLoaded,
    value.enterTransition,
    value.enterStaggerScale,
    value.containerRef,
    value.totalValue,
    value.getColor,
    value.getFill,
    value.geometryScrubbing,
    value.scrubSlicePaths,
  ]);

  const hover = useMemo(() => ({
    hoveredIndex: value.hoveredIndex,
    setHoveredIndex: value.setHoveredIndex,
  }), [value.hoveredIndex, value.setHoveredIndex]);

  return (
    <PieStableContext.Provider value={stable}>
      <PieHoverContext.Provider value={hover}>
        {children}
      </PieHoverContext.Provider>
    </PieStableContext.Provider>
  );
}

export { PieStableContext as default } from "./pie-context-hooks";
