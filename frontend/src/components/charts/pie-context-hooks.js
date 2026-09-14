import { createContext, useContext } from "react";

export const PieStableContext = createContext(null);
export const PieHoverContext = createContext(null);

export function usePieStable() {
  const context = useContext(PieStableContext);
  if (!context) {
    throw new Error(
      "usePieStable must be used within a PieProvider. " +
        "Make sure your component is wrapped in <PieChart>."
    );
  }
  return context;
}

export function usePieHover() {
  const context = useContext(PieHoverContext);
  if (!context) {
    throw new Error(
      "usePieHover must be used within a PieProvider. " +
        "Make sure your component is wrapped in <PieChart>."
    );
  }
  return context;
}

export function usePie() {
  return { ...usePieStable(), ...usePieHover() };
}
