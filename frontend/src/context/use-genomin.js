import { createContext, useContext } from "react";

export const GenominContext = createContext(null);

export function useGenomin() {
  const ctx = useContext(GenominContext);
  if (!ctx) throw new Error("useGenomin debe usarse dentro de GenominProvider");
  return ctx;
}
