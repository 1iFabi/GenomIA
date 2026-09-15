"use client";

import { geoCentroid } from "d3-geo";
import { motion as Motion } from "motion/react";
import { memo, useCallback, useEffect, useMemo } from "react";
import { useEnterComplete } from "../use-enter-complete";
import { useMountProgress } from "../use-mount-progress";
import {
  defaultChoroplethColors,
  useChoroplethInteraction,
  useChoroplethStable,
} from "./choropleth-context";

function resolveFeatureFill(feature, index, fill, getFeatureColor, getFeaturePattern) {
  const patternId = getFeaturePattern?.(feature, index);
  if (patternId) return `url(#${patternId})`;
  if (fill) return fill;
  if (getFeatureColor) return getFeatureColor(feature, index);
  return (
    defaultChoroplethColors[index % defaultChoroplethColors.length] ??
    "var(--chart-1)"
  );
}

function groupRecordsByKey(records, getFeatureGroupKey) {
  const groups = new Map();

  records.forEach((record) => {
    const key = getFeatureGroupKey(record.feature, record.index) ?? "default";
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(record);
  });

  return Array.from(groups.entries());
}

function getFeatureKey(feature, index) {
  const value = feature?.id ?? feature?.properties?.id ?? feature?.properties?.name;
  return value === undefined || value === null ? `feature-${index}` : String(value);
}

const StaticFeatureLayer = memo(function StaticFeatureLayer({
  groups,
  stroke,
  strokeWidth,
  baseOpacity,
  dimOpacity,
  hoveredIndex,
  getFeatureGroupProps,
  getFeatureProps,
  getFeatureStyle,
  onFeatureEnter,
  onFeatureLeave,
  onFeatureFocus,
  onFeatureClick,
}) {
  const renderFeature = (record) => {
    const { feature, index, isInteractive = true } = record;
    const customProps =
      getFeatureProps?.({
        feature,
        index,
        isHovered: hoveredIndex === index,
      }) || {};
    const {
      style: customPathStyle,
      onMouseEnter: customOnMouseEnter,
      onMouseLeave: customOnMouseLeave,
      onFocus: customOnFocus,
      onBlur: customOnBlur,
      onClick: customOnClick,
      onKeyDown: customOnKeyDown,
      ...restFeatureProps
    } = customProps;
    const featureStyle = getFeatureStyle?.({ feature, index }) || {};
    const featureLabel =
      restFeatureProps["aria-label"] || feature.properties?.name || "Región geográfica";
    const isFocusable = isInteractive && Number(restFeatureProps.tabIndex) >= 0;

    const handleClick = (event) => {
      event.stopPropagation();
      if (!isInteractive) return;
      customOnClick?.(event);
      onFeatureClick?.(feature, event, index);
    };

    const handleKeyDown = (event) => {
      if (!isInteractive) return;
      customOnKeyDown?.(event);
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        event.stopPropagation();
        customOnClick?.(event);
        onFeatureClick?.(feature, event, index);
      }
    };

    return (
      <path
        key={getFeatureKey(feature, index)}
        d={record.path}
        {...restFeatureProps}
        {...featureStyle}
        fill={featureStyle.fill ?? record.fill}
        stroke={featureStyle.stroke ?? stroke}
        strokeWidth={featureStyle.strokeWidth ?? strokeWidth}
        role={restFeatureProps.role || (isFocusable ? "button" : undefined)}
        aria-label={featureLabel}
        tabIndex={isInteractive ? restFeatureProps.tabIndex : -1}
        style={{
          outline: "none",
          cursor: isFocusable ? "pointer" : "default",
          ...customPathStyle,
        }}
        onMouseEnter={isInteractive ? (event) => {
          onFeatureEnter(record, event);
          customOnMouseEnter?.(event);
        } : undefined}
        onMouseLeave={isInteractive ? (event) => {
          onFeatureLeave(record, event);
          customOnMouseLeave?.(event);
        } : undefined}
        onFocus={isInteractive ? (event) => {
          onFeatureFocus(record, event);
          customOnFocus?.(event);
        } : undefined}
        onBlur={isInteractive ? (event) => {
          onFeatureLeave(record, event);
          customOnBlur?.(event);
        } : undefined}
        onClick={handleClick}
        onKeyDown={handleKeyDown}
      />
    );
  };

  const renderGroups = (highlightedIndex = null) => (
    <>
      {groups.map(([groupKey, records]) => {
        const groupProps = getFeatureGroupProps?.(groupKey, records) || {};
        const { style: groupStyle, ...restGroupProps } = groupProps;
        const visibleRecords =
          highlightedIndex === null
            ? records
            : records.filter((record) => record.index !== highlightedIndex);

        return (
          <g
            key={String(groupKey)}
            {...restGroupProps}
            style={{
              transformOrigin: "center",
              transformBox: "fill-box",
              ...groupStyle,
            }}
          >
            {visibleRecords.map(renderFeature)}
          </g>
        );
      })}
    </>
  );

  if (hoveredIndex === null) {
    return <g opacity={baseOpacity}>{renderGroups()}</g>;
  }

  const highlightedRecord = groups
    .flatMap(([, records]) => records)
    .find((record) => record.index === hoveredIndex);

  return (
    <>
      <g opacity={dimOpacity} style={{ transition: "opacity 0.18s ease-out" }}>
        {renderGroups(hoveredIndex)}
      </g>
      {highlightedRecord && (
        <g>
          {groups.map(([groupKey, records]) => {
            if (!records.some((record) => record.index === hoveredIndex)) return null;
            const groupProps = getFeatureGroupProps?.(groupKey, records) || {};
            const { style: groupStyle, ...restGroupProps } = groupProps;
            return (
              <g
                key={`highlight-${String(groupKey)}`}
                {...restGroupProps}
                style={{
                  transformOrigin: "center",
                  transformBox: "fill-box",
                  ...groupStyle,
                }}
              >
                {renderFeature(highlightedRecord)}
              </g>
            );
          })}
        </g>
      )}
    </>
  );
});

const EnterFeatureLayer = memo(function EnterFeatureLayer({
  groups,
  stroke,
  strokeWidth,
  baseOpacity,
  dimOpacity,
  hoveredIndex,
  getFeatureGroupProps,
  getFeatureProps,
  getFeatureStyle,
  onFeatureEnter,
  onFeatureLeave,
  onFeatureFocus,
  onFeatureClick,
  revealEpoch,
}) {
  const { enterTransition, animationDuration } = useChoroplethStable();
  const mountProgress = useMountProgress(
    enterTransition,
    0,
    `choropleth-layer-${revealEpoch}`,
  );
  const enterComplete = useEnterComplete(mountProgress);

  const layerProps = {
    dimOpacity,
    getFeatureGroupProps,
    getFeatureProps,
    getFeatureStyle,
    groups,
    hoveredIndex,
    onFeatureClick,
    onFeatureEnter,
    onFeatureFocus,
    onFeatureLeave,
    stroke,
    strokeWidth,
  };

  if (enterComplete) {
    return <StaticFeatureLayer {...layerProps} baseOpacity={baseOpacity} />;
  }

  return (
    <Motion.g
      key={`enter-${revealEpoch}`}
      initial={{ opacity: 0 }}
      animate={{ opacity: baseOpacity }}
      transition={{ duration: animationDuration / 1000, ease: "easeOut" }}
    >
      <StaticFeatureLayer {...layerProps} baseOpacity={1} />
    </Motion.g>
  );
});

export const ChoroplethFeature = memo(function ChoroplethFeature({
  fill,
  stroke = "var(--background)",
  strokeWidth = 0.5,
  fadedOpacity = 0.4,
  getFeatureColor,
  patterns,
  getFeaturePattern,
  getFeatureProps,
  getFeatureStyle,
  getFeatureGroupKey = () => "default",
  getFeatureGroupProps,
  isFeatureVisible = () => true,
  isFeatureInteractive = () => true,
  onFeatureClick,
  onFeatureHover,
  onFeatureLeave: onFeatureLeaveProp,
}) {
  const {
    features,
    featurePaths,
    pathGenerator,
    projectPoint,
    isLoaded,
    revealEpoch,
    animationDuration,
    width,
    height,
  } = useChoroplethStable();
  const { hoveredFeatureIndex, setHoveredFeatureIndex, setTooltipData } =
    useChoroplethInteraction();

  const featureCentroids = useMemo(
    () =>
      features.map((feature) => {
        try {
          const centroid = geoCentroid(feature);
          if (
            centroid &&
            !Number.isNaN(centroid[0]) &&
            !Number.isNaN(centroid[1])
          ) {
            const projected = projectPoint(centroid);
            if (projected) {
              const padding = 60;
              return {
                x: Math.max(padding, Math.min(width - padding, projected[0])),
                y: Math.max(padding, Math.min(height - padding, projected[1])),
              };
            }
          }
        } catch {
          // Some geometries may not have valid centroids.
        }
        return null;
      }),
    [features, height, projectPoint, width],
  );

  const records = useMemo(() => {
    const items = [];
    for (let index = 0; index < features.length; index += 1) {
      const feature = features[index];
      if (!feature || !isFeatureVisible(feature, index)) continue;

      const path = featurePaths[index] ?? pathGenerator(feature);
      if (!path) continue;

      items.push({
        index,
        path,
        fill: resolveFeatureFill(
          feature,
          index,
          fill,
          getFeatureColor,
          getFeaturePattern,
        ),
        feature,
        isInteractive: isFeatureInteractive(feature, index),
        centroid: featureCentroids[index] ?? null,
      });
    }
    return items;
  }, [
    featureCentroids,
    featurePaths,
    features,
    fill,
    getFeatureColor,
    getFeaturePattern,
    isFeatureInteractive,
    isFeatureVisible,
    pathGenerator,
  ]);

  const groups = useMemo(
    () => groupRecordsByKey(records, getFeatureGroupKey),
    [getFeatureGroupKey, records],
  );

  useEffect(() => {
    const hoveredRecord = records.find((record) => record.index === hoveredFeatureIndex);
    if (hoveredRecord && !hoveredRecord.isInteractive) {
      setHoveredFeatureIndex(null);
      setTooltipData(null);
    }
  }, [hoveredFeatureIndex, records, setHoveredFeatureIndex, setTooltipData]);

  const handleFeatureEnter = useCallback(
    (record, event) => {
      setHoveredFeatureIndex(record.index);
      setTooltipData({
        featureIndex: record.index,
        x: record.centroid?.x ?? width / 2,
        y: record.centroid?.y ?? height / 2,
        feature: record.feature,
      });
      onFeatureHover?.(record.feature, record.index, event);
    },
    [height, onFeatureHover, setHoveredFeatureIndex, setTooltipData, width],
  );

  const handleFeatureLeave = useCallback(
    (record, event) => {
      setHoveredFeatureIndex(null);
      setTooltipData(null);
      onFeatureLeaveProp?.(record.feature, record.index, event);
    },
    [onFeatureLeaveProp, setHoveredFeatureIndex, setTooltipData],
  );

  const handleFeatureFocus = useCallback(
    (record, event) => {
      handleFeatureEnter(record, event);
    },
    [handleFeatureEnter],
  );

  const layerProps = {
    dimOpacity: fadedOpacity,
    getFeatureGroupProps,
    getFeatureProps,
    getFeatureStyle,
    groups,
    hoveredIndex: hoveredFeatureIndex,
    onFeatureClick,
    onFeatureEnter: handleFeatureEnter,
    onFeatureFocus: handleFeatureFocus,
    onFeatureLeave: handleFeatureLeave,
    stroke,
    strokeWidth,
  };

  return (
    <g className="choropleth-features">
      {patterns ? <defs>{patterns}</defs> : null}
      {isLoaded || animationDuration <= 0 ? (
        <StaticFeatureLayer {...layerProps} baseOpacity={0.85} />
      ) : (
        <EnterFeatureLayer {...layerProps} baseOpacity={0.85} revealEpoch={revealEpoch} />
      )}
    </g>
  );
});

ChoroplethFeature.displayName = "ChoroplethFeature";

export default ChoroplethFeature;
