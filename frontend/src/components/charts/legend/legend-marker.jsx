"use client";
import { cn } from "@/lib/utils";
import { useLegendItem } from "./legend-context";
export function LegendMarker({ className = "h-2.5 w-2.5" }) {
  const { item } = useLegendItem();
  return <div
    className={cn("shrink-0 rounded-full", className)}
    style={{ backgroundColor: item.color }}
  />;
}
LegendMarker.displayName = "LegendMarker";
