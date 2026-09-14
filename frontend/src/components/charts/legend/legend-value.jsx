"use client";
import { cn } from "@/lib/utils";
import { intFmt } from "../chart-formatters";
import { useLegendItem } from "./legend-context";
export function LegendValue({
  className = "text-sm tabular-nums",
  showPercentage = false,
  percentageClassName = "text-xs tabular-nums",
  formatValue = intFmt,
  formatPercentage = (p) => `${p.toFixed(0)}%`
}) {
  const { item, percentage } = useLegendItem();
  return <span
    className={cn(
      "flex items-center gap-2 text-legend-muted-foreground",
      className
    )}
  >
      <span>{formatValue(item.value)}</span>
      {showPercentage && item.maxValue && <span className={percentageClassName}>
          {formatPercentage(percentage)}
        </span>}
    </span>;
}
LegendValue.displayName = "LegendValue";
