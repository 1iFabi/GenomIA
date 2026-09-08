import { useEffect, useMemo, useState } from "react";
import { Search, X, CornerDownLeft } from "lucide-react";
import { useLocation } from "react-router-dom";
import glossary from "../../constants/nalaGlossary.es.json";
import "./NalaWidget.css";
import { useNala } from "../../context/NalaContext";

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

export default function NalaWidget() {
  const { open, setOpen, pendingQuery, consumePendingQuery } = useNala();
  const [query, setQuery] = useState("");
  const [activeEntry, setActiveEntry] = useState(null);
  const [notFound, setNotFound] = useState(false);
  const location = useLocation();

  const base = import.meta.env.BASE_URL || "/";
  const nalaImg = `${base}nala.png`;

  const relatedEntries = useMemo(() => {
    if (!activeEntry?.related?.length) return [];
    return glossary.filter((item) => activeEntry.related.includes(item.id));
  }, [activeEntry]);

  const handleQuery = (text) => {
    const entry = searchEntry(text);
    setActiveEntry(entry);
    setNotFound(!entry);
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
    }
  };

  // Ejecuta consultas externas (askNala)
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
    <div className="nala-shell" aria-live="polite">
      {!open && (
        <button
          type="button"
          className="nala-launcher"
          aria-expanded={open}
          onClick={() => setOpen(true)}
        >
          <span
            className="nala-launcher-avatar"
            aria-hidden
            style={{ backgroundImage: `url(${nalaImg})` }}
          />
          <span>Pregúntale a Nala</span>
        </button>
      )}

      {open && (
        <div className="nala-card" role="dialog" aria-label="Pregúntale a Nala">
          <header className="nala-header">
            <div className="nala-title-wrap">
              <div
                className="nala-avatar nala-avatar-img"
                aria-hidden
                style={{ backgroundImage: `url(${nalaImg})` }}
              />
              <div>
                <p className="nala-kicker">¡Pregúntame lo que quieras!</p>
              </div>
            </div>

            <button
              type="button"
              className="nala-close-btn"
              aria-label="Cerrar Nala"
              onClick={() => setOpen(false)}
            >
              <X size={16} aria-hidden />
            </button>
          </header>

          <div className="nala-chips" aria-label="Preguntas rápidas">
            <span className="nala-chips-label">Preguntas rápidas</span>
            <div className="nala-chips-row">
              {QUICK_CHIPS.map((chip) => (
                <button
                  key={chip.query}
                  type="button"
                  className="nala-chip"
                  onClick={() => onChip(chip)}
                >
                  {chip.label}
                </button>
              ))}
            </div>
          </div>

          {/* ✅ Aquí se quitó el contenedor vacío */}
          {notFound || activeEntry ? (
            <div className="nala-response" aria-live="polite">
              {notFound && (
                <div className="nala-not-found">
                  No encontré eso. Prueba: alelo, rsID, SNP, genotipo.
                </div>
              )}

              {activeEntry && (
                <article className="nala-answer">
                  <h3>{activeEntry.question}</h3>
                  <p className="nala-answer-main">{activeEntry.answer}</p>

                  {activeEntry.details && (
                    <p className="nala-answer-details">{activeEntry.details}</p>
                  )}

                  {activeEntry.related?.length ? (
                    <div className="nala-related">
                      <span>Relacionado:</span>
                      <div className="nala-related-row">
                        {relatedEntries.map((item) => (
                          <button
                            key={item.id}
                            type="button"
                            className="nala-related-chip"
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
          ) : (
            <p className="nala-hint"></p>
          )}

          <form className="nala-search nala-search-bottom" onSubmit={onSubmit}>
            <Search size={16} aria-hidden />
            <input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Escribe tu pregunta..."
              aria-label="Pregunta para Nala"
            />
            <button type="submit" className="nala-enter" aria-label="Buscar">
              <CornerDownLeft size={14} />
            </button>
          </form>
        </div>
      )}
    </div>
  );
}
