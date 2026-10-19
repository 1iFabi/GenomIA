import { useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

// the panel takes the tone of the card it sits on: a light layer on a light card, a lighter navy one on the navy card.
// The card's own background decides it, composited over white (the section's ground behind a translucent card).
function toneOf(card) {
  const c = card ? getComputedStyle(card).backgroundColor.match(/[\d.]+/g)?.map(Number) : null;
  if (!c || c.length < 3) return "light";
  const a = c.length > 3 ? c[3] : 1;
  const [r, g, b] = c.slice(0, 3).map((v) => v * a + 255 * (1 - a));
  return 0.299 * r + 0.587 * g + 0.114 * b < 128 ? "dark" : "light";
}

/**
 * The "?" beside a card's title: what the term means, in plain words. It opens on hover and on
 * focus, and a tap opens it on a touch screen.
 *
 * The panel is a material over the card it sits on (its tone comes from toneOf), and it is drawn in
 * the body, fixed, because the cards clip whatever is inside them.
 */
export default function CardHelp({ label, children }) {
  const id = useId();
  const trigger = useRef(null);
  const panel = useRef(null);
  const [open, setOpen] = useState(false);
  const [at, setAt] = useState(null);

  useLayoutEffect(() => {
    if (!open) return undefined;
    const place = () => {
      const r = trigger.current.getBoundingClientRect();
      const width = panel.current?.offsetWidth || 280;
      setAt({
        // centred on the trigger, but never past the window: the ceiling is the panel's own max-width,
        // so the clamp holds even before the first measurement
        left: Math.min(Math.max(8, r.left + r.width / 2 - width / 2), window.innerWidth - 280 - 8),
        top: r.bottom + 8,
        tone: toneOf(trigger.current.closest(".dcard")),
      });
    };
    place();
    const close = () => setOpen(false);
    window.addEventListener("scroll", close, true);
    window.addEventListener("resize", close);
    return () => {
      window.removeEventListener("scroll", close, true);
      window.removeEventListener("resize", close);
    };
  }, [open]);

  useEffect(() => {
    if (!open) return undefined;
    const escape = (e) => { if (e.key === "Escape") setOpen(false); };
    window.addEventListener("keydown", escape);
    return () => window.removeEventListener("keydown", escape);
  }, [open]);

  return (
    <>
      <button
        ref={trigger}
        type="button"
        className="card-help"
        aria-describedby={open ? id : undefined}
        aria-expanded={open}
        onPointerEnter={() => setOpen(true)}
        onPointerLeave={() => setOpen(false)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onClick={() => setOpen(true)}
      >
        <span aria-hidden="true">?</span>
        <span className="card-help__label">Qué significa {label}</span>
      </button>
      {open && at && createPortal(
        <span ref={panel} id={id} role="tooltip" className="card-help__panel" data-tone={at.tone} style={{ left: at.left, top: at.top }}>
          {children}
        </span>,
        document.body,
      )}
    </>
  );
}
