"use client";
import {
  cloneElement,
  isValidElement,
  useState
} from "react";
import { cn } from "@/lib/utils";
import {
  LegendItemProvider,
  LegendProvider
} from "./legend-context";
export function Legend({
  items,
  hoveredIndex: controlledHoveredIndex,
  onHoverChange,
  title,
  titleClassName = "text-sm font-semibold",
  className = "",
  children
}) {
  const [internalHoveredIndex, setInternalHoveredIndex] = useState(null);
  const isControlled = controlledHoveredIndex !== void 0;
  const hoveredIndex = isControlled ? controlledHoveredIndex : internalHoveredIndex;
  const setHoveredIndex = (index) => {
    if (isControlled) {
      onHoverChange?.(index);
    } else {
      setInternalHoveredIndex(index);
    }
  };
  const contextValue = {
    items,
    hoveredIndex,
    setHoveredIndex
  };
  return <LegendProvider value={contextValue}>
      <div className={cn("legend-container flex flex-col gap-2", className)}>
        {title && <h3 className={cn("mb-1 text-legend-foreground", titleClassName)}>
            {title}
          </h3>}
        {items.map((item, index) => {
    const isHovered = hoveredIndex === index;
    const isFaded = hoveredIndex !== null && hoveredIndex !== index;
    const percentage = item.maxValue ? item.value / item.maxValue * 100 : 0;
    const itemContext = {
      item,
      index,
      isHovered,
      isFaded,
      percentage
    };
    if (isValidElement(children)) {
      return <LegendItemProvider key={item.label} value={itemContext}>
                {cloneElement(children)}
              </LegendItemProvider>;
    }
    return null;
  })}
      </div>
    </LegendProvider>;
}
Legend.displayName = "Legend";
