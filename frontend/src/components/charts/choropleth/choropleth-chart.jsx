"use client";;
import { Mercator } from "@visx/geo";
import { ParentSize } from "@visx/responsive";
import { Zoom, createMatrix } from "@visx/zoom";
import React, { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { cn } from "@/lib/utils";
import {
  ChoroplethInteractionShell,
  ChoroplethStableProvider,
  ChoroplethZoomContext,
  useChoroplethInteraction,
} from "./choropleth-context";
import { ChoroplethFeature as ChoroplethFeatureLayer } from "./choropleth-feature";
import { ChoroplethGraticule as ChoroplethGraticuleLayer } from "./choropleth-graticule";
import { ChoroplethTooltip as ChoroplethTooltipLayer } from "./choropleth-tooltip";

const DEFAULT_MARGIN = { top: 0, right: 0, bottom: 0, left: 0 };

// Known SVG component displayNames
const SVG_COMPONENT_NAMES = new Set([
  "ChoroplethFeature",
  "ChoroplethGraticule",
  "ChoroplethTooltip",
]);

const SVG_COMPONENT_TYPES = new Set([
  ChoroplethFeatureLayer,
  ChoroplethGraticuleLayer,
  ChoroplethTooltipLayer,
]);

function resolveComponentType(type) {
  if (
    typeof type === "object" &&
    type !== null &&
    "type" in type &&
    (type).type
  ) {
    return (type).type;
  }
  return type;
}

function getComponentDisplayName(type) {
  if (typeof type === "function") {
    const fn = type;
    return fn.displayName ?? fn.name ?? null;
  }
  if (typeof type === "object" && type !== null) {
    const wrapped = type;
    if (wrapped.displayName) {
      return wrapped.displayName;
    }
    const inner = wrapped.type;
    if (typeof inner === "function") {
      const innerFn = inner;
      return innerFn.displayName ?? innerFn.name ?? null;
    }
  }
  return null;
}

function isChoroplethSvgChild(type) {
  if (SVG_COMPONENT_TYPES.has(type)) {
    return true;
  }
  const resolved = resolveComponentType(type);
  if (resolved !== type && SVG_COMPONENT_TYPES.has(resolved)) {
    return true;
  }
  const displayName = getComponentDisplayName(type);
  return displayName !== null && SVG_COMPONENT_NAMES.has(displayName);
}

// HTML elements that should render in overlay layer
const HTML_ELEMENTS = new Set(["div", "span", "button", "p", "a"]);

// Separate children into SVG and overlay layers
function separateChildren(children) {
  const childArray = React.Children.toArray(children);
  const svgChildren = [];
  const overlayChildren = [];

  for (const child of childArray) {
    if (!React.isValidElement(child)) {
      svgChildren.push(child);
      continue;
    }

    if (isChoroplethSvgChild(child.type)) {
      svgChildren.push(child);
    } else if (typeof child.type === "string") {
      if (HTML_ELEMENTS.has(child.type)) {
        overlayChildren.push(child);
      } else {
        svgChildren.push(child);
      }
    } else {
      overlayChildren.push(child);
    }
  }

  return { svgChildren, overlayChildren };
}

const DEFAULT_INITIAL_ZOOM = {
  scaleX: 1,
  scaleY: 1,
  translateX: 0,
  translateY: 0,
  skewX: 0,
  skewY: 0,
};
const DEFAULT_ZOOM_TRANSITION_DURATION = 180;

function getTransformMatrixSignature(matrix) {
  return [
    matrix?.scaleX,
    matrix?.scaleY,
    matrix?.translateX,
    matrix?.translateY,
    matrix?.skewX,
    matrix?.skewY,
  ].join("|");
}

function getZoomTargetCenter(target) {
  if (Array.isArray(target?.center)) {
    return target.center;
  }

  if (target?.center && typeof target.center === "object") {
    return [target.center.longitude, target.center.latitude];
  }

  if (target?.longitude !== undefined && target?.latitude !== undefined) {
    return [target.longitude, target.latitude];
  }

  return null;
}

function getZoomTargetSignature(target) {
  if (!target) return "none";

  const center = getZoomTargetCenter(target) ?? [];
  const relativeScale = target.scale ?? target.relativeScale;
  return [center[0], center[1], relativeScale].join("|");
}

function getZoomTargetTransformMatrix({
  height,
  initialZoom,
  mercator,
  target,
  width,
}) {
  if (!target) return initialZoom;

  const center = getZoomTargetCenter(target);
  const relativeScale = Number(target.scale ?? target.relativeScale);
  if (
    !center
    || center.length < 2
    || !Number.isFinite(Number(center[0]))
    || !Number.isFinite(Number(center[1]))
    || !Number.isFinite(relativeScale)
    || relativeScale <= 0
  ) {
    return initialZoom;
  }

  const projectedCenter = mercator.projection([
    Number(center[0]),
    Number(center[1]),
  ]);
  if (
    !projectedCenter
    || !Number.isFinite(projectedCenter[0])
    || !Number.isFinite(projectedCenter[1])
  ) {
    return initialZoom;
  }

  const baseScaleX = Number.isFinite(Number(initialZoom?.scaleX))
    ? Number(initialZoom.scaleX)
    : 1;
  const baseScaleY = Number.isFinite(Number(initialZoom?.scaleY))
    ? Number(initialZoom.scaleY)
    : 1;
  const scaleX = baseScaleX * relativeScale;
  const scaleY = baseScaleY * relativeScale;

  return createMatrix({
    scaleX,
    scaleY,
    translateX: width / 2 - projectedCenter[0] * scaleX,
    translateY: height / 2 - projectedCenter[1] * scaleY,
  });
}

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function getTranslationBounds(viewportSize, scale, padding) {
  const contentSize = viewportSize * scale;
  const availableViewport = viewportSize - (padding * 2);

  if (contentSize <= availableViewport) {
    const centered = (viewportSize - contentSize) / 2;
    return { min: centered, max: centered };
  }

  return {
    min: viewportSize - padding - contentSize,
    max: padding,
  };
}

function constrainZoomTransform(
  transform,
  previousTransform,
  width,
  height,
  zoomMin,
  zoomMax,
  zoomPadding,
) {
  const isScaleOutOfBounds = [transform.scaleX, transform.scaleY].some(
    (scaleValue) => scaleValue < zoomMin || scaleValue > zoomMax,
  );

  // Keep VisX's existing min/max behavior when a wheel or pinch step
  // would cross a configured scale boundary.
  if (isScaleOutOfBounds) return previousTransform;

  const padding = clamp(
    Number.isFinite(Number(zoomPadding)) ? Number(zoomPadding) : 0,
    0,
    Math.min(width, height) / 2,
  );
  const xBounds = getTranslationBounds(width, transform.scaleX, padding);
  const yBounds = getTranslationBounds(height, transform.scaleY, padding);

  // Only translation is constrained; scale and any future matrix fields
  // remain untouched so drag stays smooth and zoom retains its factor.
  return {
    ...transform,
    translateX: clamp(transform.translateX, xBounds.min, xBounds.max),
    translateY: clamp(transform.translateY, yBounds.min, yBounds.max),
  };
}

const ChoroplethSvg = memo(function ChoroplethSvg({
  height,
  width,
  svgChildren,
  zoom,
  zoomTransitionDuration,
  onBackgroundClick,
  onZoomTransitionEnd,
}) {
  const { setHoveredFeatureIndex, setTooltipData } = useChoroplethInteraction();

  const handleTransitionEnd = useCallback((event) => {
    if (event.target !== event.currentTarget || event.propertyName !== "transform") {
      return;
    }
    onZoomTransitionEnd?.(event);
  }, [onZoomTransitionEnd]);

  const handleMouseLeave = useCallback(() => {
    setHoveredFeatureIndex(null);
    setTooltipData(null);
  }, [setHoveredFeatureIndex, setTooltipData]);

  return (
    <svg
      aria-label="Mapa de ascendencia"
      height={height}
      onClick={onBackgroundClick}
      onMouseLeave={handleMouseLeave}
      role="img"
      ref={zoom?.containerRef}
      style={{
        contain: "layout style paint",
        cursor: zoom?.isDragging ? "grabbing" : "grab",
        touchAction: "none",
      }}
      width={width}
    >
      <g
        onTransitionCancel={handleTransitionEnd}
        onTransitionEnd={handleTransitionEnd}
        style={{
          transition: zoom?.isDragging || zoomTransitionDuration <= 0
            ? "none"
            : `transform ${zoomTransitionDuration}ms ease-in-out`,
        }}
        transform={zoom ? zoom.toString() : undefined}
      >
        {svgChildren}
      </g>
    </svg>
  );
});

function ChoroplethZoomController({
  children,
  height,
  initialZoom,
  initialZoomSignature,
  mercator,
  projectionSignature,
  target,
  targetSignature,
  width,
  zoom,
}) {
  const targetRef = useRef(target);
  const initialZoomRef = useRef(initialZoom);
  const mercatorRef = useRef(mercator);
  const setTransformMatrixRef = useRef(zoom?.setTransformMatrix);
  const appliedSignatureRef = useRef(null);

  targetRef.current = target;
  initialZoomRef.current = initialZoom;
  mercatorRef.current = mercator;
  setTransformMatrixRef.current = zoom?.setTransformMatrix;

  const applicationSignature = [
    targetSignature,
    initialZoomSignature,
    projectionSignature,
    width,
    height,
  ].join("::");

  useEffect(() => {
    if (appliedSignatureRef.current === applicationSignature) return;

    const setTransformMatrix = setTransformMatrixRef.current;
    if (!setTransformMatrix) return;

    appliedSignatureRef.current = applicationSignature;
    setTransformMatrix(getZoomTargetTransformMatrix({
      height,
      initialZoom: initialZoomRef.current,
      mercator: mercatorRef.current,
      target: targetRef.current,
      width,
    }));
  }, [applicationSignature, height, width]);

  return children;
}

const ChoroplethMercatorContent = memo(function ChoroplethMercatorContent({
  mercator,
  data,
  width,
  height,
  innerWidth,
  innerHeight,
  margin,
  animationDuration,
  enterTransition,
  revealEpoch,
  isLoaded,
  containerRef,
  svgChildren,
  overlayChildren,
  zoom,
  zoomTransitionDuration,
  onBackgroundClick,
  onZoomTransitionEnd,
}) {
  const featurePaths = useMemo(
    () => data.features.map((feature) => mercator.path(feature) ?? null),
    [data.features, mercator]
  );

  const pathGenerator = useCallback(
    (feature) => mercator.path(feature) ?? undefined,
    [mercator]
  );

  const rawPathGenerator = useCallback(
    // biome-ignore lint/suspicious/noExplicitAny: GeoJSON types are complex
    (geo) => mercator.path(geo),
    [mercator]
  );

  const projectPoint = useCallback(
    coords => {
      const projected = mercator.projection(coords);
      if (!projected) {
        return null;
      }
      return projected;
    },
    [mercator]
  );

  const stableValue = useMemo(
    () => ({
      features: data.features,
      featureCollection: data,
      featurePaths,
      pathGenerator,
      rawPathGenerator,
      projectPoint,
      width,
      height,
      innerWidth,
      innerHeight,
      margin,
      containerRef,
      isLoaded,
      animationDuration,
      enterTransition,
      revealEpoch,
    }),
    [
      animationDuration,
      containerRef,
      data,
      enterTransition,
      featurePaths,
      height,
      innerHeight,
      innerWidth,
      isLoaded,
      margin,
      pathGenerator,
      projectPoint,
      rawPathGenerator,
      revealEpoch,
      width,
    ]
  );

  return (
    <ChoroplethZoomContext.Provider value={{ zoom: zoom ?? null }}>
      <ChoroplethStableProvider value={stableValue}>
        <ChoroplethInteractionShell>
          <div className="relative h-full w-full" ref={containerRef}>
            <ChoroplethSvg
              height={height}
              svgChildren={svgChildren}
              width={width}
              zoom={zoom}
              zoomTransitionDuration={zoomTransitionDuration}
              onBackgroundClick={onBackgroundClick}
              onZoomTransitionEnd={onZoomTransitionEnd}
            />
            {overlayChildren}
          </div>
        </ChoroplethInteractionShell>
      </ChoroplethStableProvider>
    </ChoroplethZoomContext.Provider>
  );
});

function ChoroplethChartInner({
  data,
  width,
  height,
  margin,
  animationDuration,
  enterTransition,
  revealSignature = "",
  scale: scaleProp,
  center,
  translate: translateProp,
  zoomEnabled,
  wheelZoomFactor,
  zoomMin,
  zoomMax,
  zoomPadding,
  initialZoom,
  zoomTarget,
  zoomTransitionDuration,
  children,
  onBackgroundClick,
  onZoomTransitionEnd,
}) {
  const containerRef = useRef(null);
  const [isLoaded, setIsLoaded] = useState(false);
  const [revealEpoch, setRevealEpoch] = useState(0);

  const innerWidth = width - margin.left - margin.right;
  const innerHeight = height - margin.top - margin.bottom;

  const scale = scaleProp ?? (innerWidth / 630) * 100;

  const translate = translateProp ?? [
    innerWidth / 2 + margin.left,
    innerHeight / 2 + margin.top + 50,
  ];

  const zoomTargetSignature = getZoomTargetSignature(zoomTarget);
  const initialZoomSignature = getTransformMatrixSignature(initialZoom);
  const projectionSignature = [
    scale,
    translate?.[0],
    translate?.[1],
    center?.[0],
    center?.[1],
  ].join("|");

  const { svgChildren, overlayChildren } = useMemo(
    () => separateChildren(children),
    [children]
  );

  const constrain = useCallback(
    (transform, previousTransform) => {
      if (transform === initialZoom) return transform;

      return constrainZoomTransform(
        transform,
        previousTransform,
        width,
        height,
        zoomMin,
        zoomMax,
        zoomPadding,
      );
    },
    [height, initialZoom, width, zoomMax, zoomMin, zoomPadding],
  );

  // biome-ignore lint/correctness/useExhaustiveDependencies: revealSignature
  useEffect(() => {
    setRevealEpoch((n) => n + 1);
    setIsLoaded(false);
    const timeout = setTimeout(() => {
      setIsLoaded(true);
    }, animationDuration);
    return () => clearTimeout(timeout);
  }, [animationDuration, revealSignature]);

  if (width < 10 || height < 10) {
    return null;
  }

  const mercatorContentProps = {
    animationDuration,
    onBackgroundClick,
    onZoomTransitionEnd,
    containerRef,
    data,
    enterTransition,
    height,
    zoomTransitionDuration,
    innerHeight,
    innerWidth,
    isLoaded,
    margin,
    overlayChildren,
    revealEpoch,
    svgChildren,
    width,
  };

  return (
    <Mercator
      center={center}
      data={data.features}
      scale={scale}
      translate={translate}
    >
      {(mercator) => {
        const content = (zoom) => {
          const chartContent = (
            <ChoroplethMercatorContent
              {...mercatorContentProps}
              mercator={mercator}
              zoom={zoom}
            />
          );

          if (!zoom) return chartContent;

          return (
            <ChoroplethZoomController
              height={height}
              initialZoom={initialZoom}
              initialZoomSignature={initialZoomSignature}
              mercator={mercator}
              projectionSignature={projectionSignature}
              target={zoomTarget}
              targetSignature={zoomTargetSignature}
              width={width}
              zoom={zoom}
            >
              {chartContent}
            </ChoroplethZoomController>
          );
        };

        if (zoomEnabled) {
          return (
            <Zoom
              height={height}
              initialTransformMatrix={initialZoom}
              scaleXMax={zoomMax}
              scaleXMin={zoomMin}
              scaleYMax={zoomMax}
              scaleYMin={zoomMin}
              constrain={constrain}
              wheelDelta={(event) => {
                const zoomScale = event.deltaY > 0
                      ? 2 - wheelZoomFactor
                      : wheelZoomFactor;
                return { scaleX: zoomScale, scaleY: zoomScale };
              }}
              width={width}>
              {(zoom) => content(zoom)}
            </Zoom>
          );
        }

        return content();
      }}
    </Mercator>
  );
}

export function ChoroplethChart({
  data,
  margin: marginProp,
  animationDuration = 800,
  enterTransition,
  revealSignature,
  aspectRatio = "16 / 9",
  scale,
  center = [0, 20],
  translate,
  zoomEnabled = false,
  wheelZoomFactor = 1.05,
  zoomMin = 0.5,
  zoomMax = 4,
  zoomPadding = 0,
  initialZoom = DEFAULT_INITIAL_ZOOM,
  zoomTarget,
  zoomTransitionDuration = 180,
  className = "",
  children,
  onBackgroundClick,
  onZoomTransitionEnd,
  fadedOpacity = 0.4,
  fill,
  stroke,
  strokeWidth,
  getFeatureColor,
  getFeaturePattern,
  getFeatureProps,
  getFeatureStyle,
  getFeatureGroupKey,
  getFeatureGroupProps,
  isFeatureVisible,
  isFeatureInteractive,
  onFeatureClick,
  onFeatureHover,
  onFeatureLeave,
  patterns
}) {
  const margin = { ...DEFAULT_MARGIN, ...marginProp };
  const featureLayer = children || (
    <ChoroplethFeatureLayer
      fadedOpacity={fadedOpacity}
      fill={fill}
      getFeatureColor={getFeatureColor}
      getFeatureGroupKey={getFeatureGroupKey}
      getFeatureGroupProps={getFeatureGroupProps}
      getFeaturePattern={getFeaturePattern}
      getFeatureProps={getFeatureProps}
      getFeatureStyle={getFeatureStyle}
      isFeatureVisible={isFeatureVisible}
      isFeatureInteractive={isFeatureInteractive}
      onFeatureClick={onFeatureClick}
      onFeatureHover={onFeatureHover}
      onFeatureLeave={onFeatureLeave}
      patterns={patterns}
      stroke={stroke}
      strokeWidth={strokeWidth}
    />
  );

  if (!data) {
    return (
      <div
        className={cn("relative w-full", className)}
        data-state="loading"
        style={{ aspectRatio }}
      />
    );
  }

  return (
    <div className={cn("relative w-full", className)} style={{ aspectRatio }}>
      <ParentSize debounceTime={10}>
        {({ width, height }) =>
          width > 0 && height > 0 ? (
            <ChoroplethChartInner
              animationDuration={animationDuration}
              center={center}
              data={data}
              enterTransition={enterTransition}
              height={height}
              initialZoom={initialZoom}
              zoomTarget={zoomTarget}
              zoomTransitionDuration={zoomTransitionDuration}
              onZoomTransitionEnd={onZoomTransitionEnd}
              margin={margin}
              revealSignature={revealSignature}
              scale={scale}
              translate={translate}
              width={width}
              wheelZoomFactor={wheelZoomFactor}
              zoomEnabled={zoomEnabled}
              zoomMax={zoomMax}
              zoomMin={zoomMin}
              zoomPadding={zoomPadding}
              onBackgroundClick={onBackgroundClick}
            >
              {featureLayer}
            </ChoroplethChartInner>
          ) : null
        }
      </ParentSize>
    </div>
  );
}

ChoroplethChart.displayName = "ChoroplethChart";

export default ChoroplethChart;
