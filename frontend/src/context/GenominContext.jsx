import { useCallback, useState } from "react";
import { GenominContext } from "./use-genomin";

export { useGenomin } from "./use-genomin";

export function GenominProvider({ children }) {
  const [open, setOpen] = useState(false);
  const [pendingQuery, setPendingQuery] = useState("");

  const openGenomin = useCallback(() => setOpen(true), []);

  const askGenomin = useCallback((queryString) => {
    setPendingQuery(queryString || "");
    setOpen(true);
  }, []);

  const consumePendingQuery = useCallback(() => {
    const q = pendingQuery;
    setPendingQuery("");
    return q;
  }, [pendingQuery]);

  return (
    <GenominContext.Provider
      value={{
        open,
        setOpen,
        pendingQuery,
        consumePendingQuery,
        openGenomin,
        askGenomin,
      }}
    >
      {children}
    </GenominContext.Provider>
  );
}
