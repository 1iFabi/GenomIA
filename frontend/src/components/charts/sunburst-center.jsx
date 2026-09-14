"use client";
import { memo } from "react";
import { ringOptions } from "./sunburst-utils";
import { sunburstCssVars, useSunburstStable } from "./sunburst-context";

const CENTER_DISC_SCALE = 0.27;
const MIN_ROOT_CENTER_RADIUS = 26;
const MAX_ROOT_CENTER_RADIUS = 48;

export const SunburstCenter = memo(function SunburstCenter2({
  className,
  label,
  value
}) {
  const { focus, prevFocus, maxDepth, radius, zoomT, zoomTo } = useSunburstStable();
  const { centerR, ringWidth } = ringOptions(focus.depth, maxDepth, radius);
  const previousCenterR = ringOptions(prevFocus.depth, maxDepth, radius).centerR;
  const liveCenterR = centerR * zoomT + previousCenterR * (1 - zoomT);
  const rootCenterRadius = Math.min(
    MAX_ROOT_CENTER_RADIUS,
    radius * CENTER_DISC_SCALE,
    Math.max(MIN_ROOT_CENTER_RADIUS, ringWidth * 0.52),
  );
  const discRadius = Math.max(rootCenterRadius, liveCenterR - 2);
  const canZoomOut = Boolean(focus.parentId);
  const hasSummary = label != null || value != null;
  const summaryText = [label, value].filter((item) => item != null && String(item).trim() !== '').join(': ');
  const centerClassName = ['sunburst-center', className].filter(Boolean).join(' ');

  const handleCenterKeyDown = (event) => {
    if (!canZoomOut || (event.key !== "Enter" && event.key !== " ")) return;
    event.preventDefault();
    zoomTo(focus.parentId);
  };

  return (
    /* biome-ignore lint/a11y/noStaticElementInteractions: Center zoom-out control is keyboard accessible when a parent exists. */
    <g
      aria-label={summaryText || undefined}
      className={centerClassName}
      focusable={canZoomOut ? "true" : undefined}
      onClick={() => canZoomOut && zoomTo(focus.parentId)}
      onKeyDown={handleCenterKeyDown}
      role={canZoomOut ? "button" : "group"}
      tabIndex={canZoomOut ? 0 : undefined}
    >
      <circle
        className={['sunburst-center__disc', className].filter(Boolean).join(' ')}
        cx={0}
        cy={0}
        fill={sunburstCssVars.background}
        pointerEvents={canZoomOut ? "auto" : "none"}
        r={Math.max(discRadius, 0)}
        stroke={sunburstCssVars.ring}
        strokeWidth={1}
        style={{ cursor: canZoomOut ? "pointer" : "default" }}
      />
      {hasSummary && (
        <>
          <text
            aria-hidden="true"
            className="sunburst-center__label"
            dominantBaseline="middle"
            fill={sunburstCssVars.foregroundMuted}
            pointerEvents="none"
            textAnchor="middle"
            x={0}
            y={-7}
          >
            {label}
          </text>
          <text
            aria-hidden="true"
            className="sunburst-center__value"
            dominantBaseline="middle"
            fill={sunburstCssVars.foreground}
            pointerEvents="none"
            textAnchor="middle"
            x={0}
            y={8}
          >
            {value}
          </text>
        </>
      )}
    </g>
  );
});
SunburstCenter.displayName = "SunburstCenter";
