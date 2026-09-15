"use client";;
import { Graticule } from "@visx/geo";
import { memo } from "react";
import { useChoroplethStable } from "./choropleth-context";

export const ChoroplethGraticule = memo(function ChoroplethGraticule({
  stroke = "rgba(255,255,255,0.1)",
  strokeWidth = 0.5,
  step
}) {
  const { rawPathGenerator } = useChoroplethStable();

  return (
    <Graticule
      graticule={(g) => rawPathGenerator(g) || ""}
      step={step}
      stroke={stroke}
      strokeWidth={strokeWidth}
    />
  );
});

ChoroplethGraticule.displayName = "ChoroplethGraticule";

export default ChoroplethGraticule;
