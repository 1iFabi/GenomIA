"use client";
import { motion as Motion, useTransform } from "motion/react";
import { memo, useMemo } from "react";
import { applyHoverGrow, arcPath, transitionGeometry } from "./sunburst-utils";
import {
  sunburstCssVars,
  useSunburstHover,
  useSunburstStable
} from "./sunburst-context";
import { useEnterComplete } from "./use-enter-complete";
import { useMountProgress } from "./use-mount-progress";
const HOVER_DIM_TRANSITION = { duration: 0.16, ease: "easeOut" };
export const SunburstSegment = memo(function SunburstSegment2({
  index,
  color: colorProp,
  fill: fillProp,
  fillOpacity: fillOpacityProp,
  onClick: onSegmentClick
}) {
  const {
    arcs,
    focus,
    prevFocus,
    maxDepth,
    radius,
    zoomT,
    enterTiming,
    enterTransition,
    playKey,
    skipEnterAnimation,
    growAmountForArc,
    getFill,
    getFillOpacity,
    isRelated,
    maxExpandedThickness,
    zoomTo
  } = useSunburstStable();
  const { setHoveredArc, setHoveredArcIndex } = useSunburstHover();
  const arc = arcs[index];
  const segmentDelay = (arc ? enterTiming.segmentDelays.get(arc.id)?.delay : void 0) ?? 0;
  const replayId = arc?.id ?? `missing-${index}`;
  const base = useMemo(() => {
    if (!arc) {
      return null;
    }
    return transitionGeometry(arc, prevFocus, focus, maxDepth, radius, zoomT);
  }, [arc, prevFocus, focus, maxDepth, radius, zoomT]);
  const visualGeometry = useMemo(() => {
    if (!(arc && base)) {
      return null;
    }
    return applyHoverGrow(base, arc.id, growAmountForArc, maxExpandedThickness);
  }, [arc, base, growAmountForArc, maxExpandedThickness]);
  const enterProgress = useMountProgress(
    enterTransition,
    segmentDelay,
    `${playKey}-enter-${replayId}`
  );
  const enterComplete = useEnterComplete(enterProgress);
  const enterScale = useTransform(enterProgress, [0, 1], [0, 1]);
  const animatedHitPath = useTransform(
    enterProgress,
    (value) => base ? arcPath(base, value, 1) ?? "" : ""
  );
  const animatedVisualPath = useTransform(
    enterProgress,
    (value) => visualGeometry ? arcPath(visualGeometry, value, 1) ?? "" : ""
  );
  if (!arc) {
    return null;
  }
  if (!base) {
    return null;
  }
  const showStatic = skipEnterAnimation || enterComplete;
  const fullHitPath = arcPath(base, 1, 1);
  const fullVisualPath = visualGeometry ? arcPath(visualGeometry, 1, 1) : null;
  if (!(fullHitPath && fullVisualPath)) {
    return null;
  }
  const relativeDepth = arc.depth - focus.depth;
  const segmentFill = getFill(index, fillProp, colorProp);
  const fillOpacity = fillOpacityProp ?? getFillOpacity(relativeDepth);
  const related = isRelated(arc);
  const layerOpacity = related ? 1 : 0.25;
  const isInteractive = arc.depth > 0;
  const segmentLabel = arc.variantKey
    ? `Abrir detalle de variante ${arc.name}`
    : arc.hasChildren
      ? `Explorar ${arc.name}`
      : `Seleccionar ${arc.name}`;
  const groupStyle = {
    cursor: isInteractive ? "pointer" : "default",
    transformOrigin: "0px 0px"
  };
  const accessibilityProps = isInteractive ? {
    "aria-label": segmentLabel,
    "data-interactive": "true",
    "data-variant-key": arc.variantKey,
    focusable: "true",
    role: "button",
    tabIndex: 0
  } : {};
  const hitHandlers = {
    onClick: () => {
      onSegmentClick?.(arc);
      if (arc.hasChildren) {
        zoomTo(arc.id);
      }
    },
    onKeyDown: (event) => {
      if (event.key !== "Enter" && event.key !== " ") return;
      event.preventDefault();
      hitHandlers.onClick();
    },
    onFocus: () => {
      setHoveredArc(arc);
      setHoveredArcIndex(index);
    },
    onBlur: () => {
      setHoveredArc(null);
      setHoveredArcIndex(null);
    },
    onPointerEnter: () => {
      setHoveredArc(arc);
      setHoveredArcIndex(index);
    }
  };
  const visualPathProps = {
    fill: segmentFill,
    fillOpacity,
    pointerEvents: "none",
    stroke: sunburstCssVars.ring,
    strokeLinejoin: "round",
    strokeWidth: 1
  };
  if (showStatic) {
    return <Motion.g
      {...accessibilityProps}
      animate={{ opacity: layerOpacity }}
      initial={false}
      onBlur={hitHandlers.onBlur}
      onClick={hitHandlers.onClick}
      onFocus={hitHandlers.onFocus}
      onKeyDown={hitHandlers.onKeyDown}
      onPointerEnter={hitHandlers.onPointerEnter}
      style={groupStyle}
      transition={{ opacity: HOVER_DIM_TRANSITION }}
    >
        <path d={fullHitPath} fill="transparent" />
        <path d={fullVisualPath} {...visualPathProps} />
      </Motion.g>;
  }
  return <Motion.g
    {...accessibilityProps}
    animate={{ opacity: layerOpacity }}
    initial={false}
    onBlur={hitHandlers.onBlur}
    onClick={hitHandlers.onClick}
    onFocus={hitHandlers.onFocus}
    onKeyDown={hitHandlers.onKeyDown}
    onPointerEnter={hitHandlers.onPointerEnter}
    style={{
      ...groupStyle,
      scale: enterScale
    }}
    transition={{ opacity: HOVER_DIM_TRANSITION }}
  >
      <Motion.path d={animatedHitPath} fill="transparent" />
      <Motion.path d={animatedVisualPath} {...visualPathProps} />
    </Motion.g>;
});
SunburstSegment.displayName = "SunburstSegment";
