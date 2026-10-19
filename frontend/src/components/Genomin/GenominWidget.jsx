import { useEffect, useMemo, useState } from "react";
import { Search, X, CornerDownLeft } from "lucide-react";
import { useLocation } from "react-router-dom";
import glossary from "../../constants/genominGlossary.es.json";
import "./GenominWidget.css";
import { useGenomin } from "../../context/GenominContext";
import GenominMascot from "./GenominMascot";
import { pickMascotState } from "./mascotState";

const SLEEP_AFTER_MS = 60000;
const ENTRANCE_MS = 1800;

const QUICK_CHIPS = [
  { label: "Alelo", query: "alelo" },
  { label: "rsID", query: "rsid" },
  { label: "Genotipo", query: "genotipo" },
  { label: "Cromosoma", query: "cromosoma" },
  { label: "Impacto", query: "impacto" },
];

const normalizar = (text = "") => text.toLowerCase().trim();

const searchEntry = (text) => {
  if (!text) return null;
  const q = normalizar(text);

  return (
    glossary.find((item) => {
      const question = normalizar(item.question);
      return question.includes(q) || q.includes(question);
    }) ||
    glossary.find((item) =>
      item.tags.some((tag) => {
        const t = normalizar(tag);
        return t.includes(q) || q.includes(t);
      })
    ) ||
    null
  );
};

export default function GenominWidget() {
  const { open, setOpen, pendingQuery, consumePendingQuery } = useGenomin();
  const [query, setQuery] = useState("");
  const [activeEntry, setActiveEntry] = useState(null);
  const [notFound, setNotFound] = useState(false);
  const [typing, setTyping] = useState(false);
  const [hover, setHover] = useState(false);
  const [entering, setEntering] = useState(true);
  const [sleeping, setSleeping] = useState(false);
  const location = useLocation();

  useEffect(() => {
    const id = setTimeout(() => setEntering(false), ENTRANCE_MS);
    return () => clearTimeout(id);
  }, []);

  // Se duerme tras un minuto sin actividad en la página y despierta con cualquier movimiento
  useEffect(() => {
    let id;
    const wake = () => {
      setSleeping(false);
      clearTimeout(id);
      id = setTimeout(() => setSleeping(true), SLEEP_AFTER_MS);
    };
    const events = ["pointermove", "keydown", "scroll", "touchstart"];
    events.forEach((e) => window.addEventListener(e, wake, { passive: true }));
    wake();
    return () => {
      clearTimeout(id);
      events.forEach((e) => window.removeEventListener(e, wake));
    };
  }, []);

  const mascotState = pickMascotState({
    entering,
    open,
    hover,
    sleeping,
    typing,
    notFound,
    found: Boolean(activeEntry),
  });

  const relatedEntries = useMemo(() => {
    if (!activeEntry?.related?.length) return [];
    return glossary.filter((item) => activeEntry.related.includes(item.id));
  }, [activeEntry]);

  const handleQuery = (text) => {
    const entry = searchEntry(text);
    setActiveEntry(entry);
    setNotFound(!entry);
    setTyping(false);
  };

  const onSubmit = (e) => {
    e.preventDefault();
    handleQuery(query);
  };

  const onChip = (chip) => {
    setQuery(chip.query);
    handleQuery(chip.query);
  };

  const onRelated = (id) => {
    const entry = glossary.find((item) => item.id === id);
    if (entry) {
      setQuery(entry.question);
      setActiveEntry(entry);
      setNotFound(false);
      setTyping(false);
    }
  };

  // Ejecuta consultas externas (askGenomin)
  useEffect(() => {
    if (!pendingQuery) return;
    const q = consumePendingQuery();
    if (q) {
      setQuery(q);
      handleQuery(q);
      setOpen(true);
    }
  }, [pendingQuery, consumePendingQuery, setOpen]);

  // Hide widget on ChatIA page (después de todos los hooks)
  if (location.pathname.includes("/chat-ia")) {
    return null;
  }

  return (
    <div className="genomin-shell" aria-live="polite">
      {!open && (
        <button
          type="button"
          className="genomin-launcher"
          aria-expanded={open}
          onClick={() => {
            setHover(false);
            setOpen(true);
          }}
          onMouseEnter={() => setHover(true)}
          onMouseLeave={() => setHover(false)}
        >
          <GenominMascot state={mascotState} size={96} />
          <span className="genomin-launcher-text">Pregúntale a Genomin</span>
        </button>
      )}

      {open && (
        <div className="genomin-card" role="dialog" aria-label="Pregúntale a Genomin">
          <header className="genomin-header">
            <GenominMascot state={mascotState} size={120} />
            <h2 className="genomin-title">Pregúntale a Genomin</h2>

            <button
              type="button"
              className="genomin-close-btn"
              aria-label="Cerrar Genomin"
              onClick={() => setOpen(false)}
            >
              <X size={18} aria-hidden />
            </button>
          </header>

          <div className="genomin-chips" aria-label="Preguntas rápidas">
            <span className="genomin-chips-label">Preguntas rápidas</span>
            <div className="genomin-chips-row">
              {QUICK_CHIPS.map((chip) => (
                <button
                  key={chip.query}
                  type="button"
                  className="genomin-chip"
                  onClick={() => onChip(chip)}
                >
                  {chip.label}
                </button>
              ))}
            </div>
          </div>

          {notFound || activeEntry ? (
            <div className="genomin-response" aria-live="polite">
              {notFound && (
                <div className="genomin-not-found">
                  No encontré eso. Prueba: alelo, rsID, SNP, genotipo.
                </div>
              )}

              {activeEntry && (
                <article className="genomin-answer">
                  <h3>{activeEntry.question}</h3>
                  <p className="genomin-answer-main">{activeEntry.answer}</p>

                  {activeEntry.details && (
                    <p className="genomin-answer-details">{activeEntry.details}</p>
                  )}

                  {activeEntry.related?.length ? (
                    <div className="genomin-related">
                      <span>Relacionado:</span>
                      <div className="genomin-related-row">
                        {relatedEntries.map((item) => (
                          <button
                            key={item.id}
                            type="button"
                            className="genomin-related-chip"
                            onClick={() => onRelated(item.id)}
                          >
                            {item.question}
                          </button>
                        ))}
                      </div>
                    </div>
                  ) : null}
                </article>
              )}
            </div>
          ) : null}

          <form className="genomin-search genomin-search-bottom" onSubmit={onSubmit}>
            <Search size={16} aria-hidden />
            <input
              type="search"
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setTyping(e.target.value.trim() !== "");
              }}
              placeholder="Escribe tu pregunta..."
              aria-label="Pregunta para Genomin"
            />
            <button type="submit" className="genomin-enter" aria-label="Buscar">
              <CornerDownLeft size={18} aria-hidden />
            </button>
          </form>
        </div>
      )}
    </div>
  );
}
