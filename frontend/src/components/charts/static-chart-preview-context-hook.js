import { createContext, useContext } from "react";

export const StaticChartPreviewContext = createContext(false);

export function useStaticChartPreview() {
  return useContext(StaticChartPreviewContext);
}
