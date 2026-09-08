import { createContext, useCallback, useContext, useState } from "react";

const NalaContext = createContext(null);

export function NalaProvider({ children }) {
  const [open, setOpen] = useState(false);
  const [pendingQuery, setPendingQuery] = useState("");

  const openNala = useCallback(() => setOpen(true), []);

  const askNala = useCallback((queryString) => {
    setPendingQuery(queryString || "");
    setOpen(true);
  }, []);

  const consumePendingQuery = useCallback(() => {
    const q = pendingQuery;
    setPendingQuery("");
    return q;
  }, [pendingQuery]);

  return (
    <NalaContext.Provider
      value={{
        open,
        setOpen,
        pendingQuery,
        consumePendingQuery,
        openNala,
        askNala,
      }}
    >
      {children}
    </NalaContext.Provider>
  );
}

export function useNala() {
  const ctx = useContext(NalaContext);
  if (!ctx) throw new Error("useNala debe usarse dentro de NalaProvider");
  return ctx;
}
