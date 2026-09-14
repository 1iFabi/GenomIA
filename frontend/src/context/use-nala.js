import { createContext, useContext } from "react";

export const NalaContext = createContext(null);

export function useNala() {
  const ctx = useContext(NalaContext);
  if (!ctx) throw new Error("useNala debe usarse dentro de NalaProvider");
  return ctx;
}
