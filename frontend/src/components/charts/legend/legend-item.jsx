"use client";
import { cn } from "@/lib/utils";
import { useLegend, useLegendItem } from "./legend-context";
export function LegendItem({ className = "", children }) {
  const { setHoveredIndex } = useLegend();
  const { index, isHovered } = useLegendItem();
  return (
    // biome-ignore lint/a11y/noNoninteractiveElementInteractions: Legend item hover interaction
    // biome-ignore lint/a11y/noStaticElementInteractions: Legend item hover interaction
    <div
      className={cn(
        "cursor-pointer rounded-lg px-2 py-1.5 transition-all duration-150 ease-out",
        isHovered && "bg-legend-muted",
        className
      )}
      data-hovered={isHovered ? "" : void 0}
      onMouseEnter={() => setHoveredIndex(index)}
      onMouseLeave={() => setHoveredIndex(null)}
    >
      {children}
    </div>
  );
}
LegendItem.displayName = "LegendItem";
