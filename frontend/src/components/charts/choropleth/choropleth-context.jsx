"use client";;
/* eslint react-refresh/only-export-components: ["error", { "allowExportNames": ["ChoroplethZoomContext", "useChoroplethZoom", "useChoroplethStable", "useChoroplethInteraction", "useChoropleth", "choroplethCssVars", "defaultChoroplethColors"] }] */
import { createContext, useContext, useMemo, useState } from "react";

export const ChoroplethZoomContext = createContext({
  zoom: null,
});

export function useChoroplethZoom() {
  return useContext(ChoroplethZoomContext);
}

const ChoroplethStableContext =
  createContext(null);
const ChoroplethInteractionContext =
  createContext(null);

export function ChoroplethStableProvider({
  children,
  value
}) {
  return (
    <ChoroplethStableContext.Provider value={value}>
      {children}
    </ChoroplethStableContext.Provider>
  );
}

export function ChoroplethInteractionShell({
  children
}) {
  const [hoveredFeatureIndex, setHoveredFeatureIndex] = useState(null);
  const [tooltipData, setTooltipData] = useState(null);

  const interaction = useMemo(() => ({
    hoveredFeatureIndex,
    setHoveredFeatureIndex,
    tooltipData,
    setTooltipData,
  }), [hoveredFeatureIndex, tooltipData]);

  return (
    <ChoroplethInteractionContext.Provider value={interaction}>
      {children}
    </ChoroplethInteractionContext.Provider>
  );
}

export function ChoroplethProvider({
  children,
  value
}) {
  const stable = useMemo(() => ({
    features: value.features,
    featureCollection: value.featureCollection,
    featurePaths: value.featurePaths,
    pathGenerator: value.pathGenerator,
    rawPathGenerator: value.rawPathGenerator,
    projectPoint: value.projectPoint,
    width: value.width,
    height: value.height,
    innerWidth: value.innerWidth,
    innerHeight: value.innerHeight,
    margin: value.margin,
    containerRef: value.containerRef,
    isLoaded: value.isLoaded,
    animationDuration: value.animationDuration,
    enterTransition: value.enterTransition,
    revealEpoch: value.revealEpoch,
  }), [
    value.features,
    value.featureCollection,
    value.featurePaths,
    value.pathGenerator,
    value.rawPathGenerator,
    value.projectPoint,
    value.width,
    value.height,
    value.innerWidth,
    value.innerHeight,
    value.margin,
    value.containerRef,
    value.isLoaded,
    value.animationDuration,
    value.enterTransition,
    value.revealEpoch,
  ]);

  const interaction = useMemo(() => ({
    hoveredFeatureIndex: value.hoveredFeatureIndex,
    setHoveredFeatureIndex: value.setHoveredFeatureIndex,
    tooltipData: value.tooltipData,
    setTooltipData: value.setTooltipData,
  }), [
    value.hoveredFeatureIndex,
    value.setHoveredFeatureIndex,
    value.tooltipData,
    value.setTooltipData,
  ]);

  return (
    <ChoroplethStableProvider value={stable}>
      <ChoroplethInteractionContext.Provider value={interaction}>
        {children}
      </ChoroplethInteractionContext.Provider>
    </ChoroplethStableProvider>
  );
}

export function useChoroplethStable() {
  const context = useContext(ChoroplethStableContext);
  if (!context) {
    throw new Error(
      "useChoroplethStable must be used within a ChoroplethProvider"
    );
  }
  return context;
}

export function useChoroplethInteraction() {
  const context = useContext(ChoroplethInteractionContext);
  if (!context) {
    throw new Error(
      "useChoroplethInteraction must be used within a ChoroplethProvider"
    );
  }
  return context;
}

export function useChoropleth() {
  return { ...useChoroplethStable(), ...useChoroplethInteraction() };
}

import { CHART_SCALE_VARS, chartScaleCssVars } from "../chart-scale";

// CSS variables for choropleth theming
export const choroplethCssVars = {
  scale01: chartScaleCssVars.scale01,
  scale02: chartScaleCssVars.scale02,
  scale03: chartScaleCssVars.scale03,
  scale04: chartScaleCssVars.scale04,
  scale05: chartScaleCssVars.scale05,
  patternColor: chartScaleCssVars.patternColor,
  stroke: "var(--chart-grid)",
  background: "var(--background)",
};

// Default colors array for cycling through features
export const defaultChoroplethColors = [...CHART_SCALE_VARS];
