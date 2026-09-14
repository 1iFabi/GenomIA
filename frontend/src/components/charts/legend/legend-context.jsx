"use client";
/* eslint-disable react-refresh/only-export-components */
import { createContext, useContext } from "react";
export const legendCssVars = {
  background: "var(--legend)",
  foreground: "var(--legend-foreground)",
  muted: "var(--legend-muted)",
  mutedForeground: "var(--legend-muted-foreground)",
  track: "var(--legend-track)"
};
const LegendContext = createContext(null);
const LegendItemContext = createContext(null);
export function LegendProvider({
  children,
  value
}) {
  return <LegendContext.Provider value={value}>{children}</LegendContext.Provider>;
}
export function LegendItemProvider({
  children,
  value
}) {
  return <LegendItemContext.Provider value={value}>
      {children}
    </LegendItemContext.Provider>;
}
export function useLegend() {
  const context = useContext(LegendContext);
  if (!context) {
    throw new Error("useLegend must be used within a <Legend> component.");
  }
  return context;
}
export function useLegendItem() {
  const context = useContext(LegendItemContext);
  if (!context) {
    throw new Error(
      "useLegendItem must be used within a <LegendItem> component."
    );
  }
  return context;
}
