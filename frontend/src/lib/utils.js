import { clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs) {
  return twMerge(clsx(inputs));
}

export function formatFrequency(value, emptyLabel = 'N/D') {
  if (value === null || value === undefined || value === '') return emptyLabel;
  const parsed = Number(value);
  if (Number.isNaN(parsed)) return emptyLabel;
  const percent = parsed <= 1 ? parsed * 100 : parsed;
  return `${percent.toFixed(2)}%`;
}
