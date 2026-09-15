"use client";;
import { intFmt } from "../chart-formatters";
import { TooltipBox } from "../tooltip/tooltip-box";
import { TooltipContent } from "../tooltip/tooltip-content";
import { useChoroplethInteraction, useChoroplethStable, useChoroplethZoom } from "./choropleth-context";

export function ChoroplethTooltip({
  content,
  formatValue = intFmt,
  getFeatureName,
  getFeatureValue,
  valueLabel = "Value",
  className = "",
  panelStyle,
  backgroundColor
}) {
  const { containerRef, width, height, features } = useChoroplethStable();
  const { tooltipData } = useChoroplethInteraction();
  const { zoom } = useChoroplethZoom();

  if (!tooltipData) {
    return null;
  }

  // Apply zoom transform to centroid position
  let x = tooltipData.x;
  let y = tooltipData.y;

  if (zoom) {
    // Apply the zoom transform matrix to the tooltip position
    const transformed = zoom.applyToPoint({ x, y });
    x = transformed.x;
    y = transformed.y;
  }

  const feature = features[tooltipData.featureIndex];
  if (!feature) {
    return null;
  }

  // Get feature name
  const featureName = getFeatureName
    ? getFeatureName(feature, tooltipData.featureIndex)
    : (feature.properties?.name ?? `Feature ${tooltipData.featureIndex}`);

  // Custom content
  if (content) {
    return (
      <TooltipBox
        backgroundColor={backgroundColor}
        className={className}
        containerHeight={height}
        containerRef={containerRef}
        containerWidth={width}
        panelStyle={panelStyle}
        visible
        x={x}
        y={y}
      >
        {content({ feature, index: tooltipData.featureIndex })}
      </TooltipBox>
    );
  }

  // Default tooltip with optional value
  const value = getFeatureValue?.(feature, tooltipData.featureIndex);
  const rows =
    value === undefined
      ? []
      : [
          {
            color: "var(--chart-1)",
            label: valueLabel,
            value: formatValue(value),
          },
        ];

  return (
    <TooltipBox
      backgroundColor={backgroundColor}
      className={className}
      containerHeight={height}
      containerRef={containerRef}
      containerWidth={width}
      panelStyle={panelStyle}
      visible
      x={x}
      y={y}
    >
      <TooltipContent rows={rows} title={featureName} />
    </TooltipBox>
  );
}

ChoroplethTooltip.displayName = "ChoroplethTooltip";

export default ChoroplethTooltip;
