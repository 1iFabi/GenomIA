"use client";
import { cn } from "@/lib/utils";
import { useLegendItem } from "./legend-context";
export function LegendLabel({
  className = "text-sm font-medium"
}) {
  const { item } = useLegendItem();
  return <span className={cn("text-legend-foreground", className)}>
      {item.label}
    </span>;
}
LegendLabel.displayName = "LegendLabel";
