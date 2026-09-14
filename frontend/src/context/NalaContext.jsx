import { useCallback, useState } from "react";
import { NalaContext } from "./use-nala";

export { useNala } from "./use-nala";

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
