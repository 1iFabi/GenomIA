// src/components/Navbar/Navbar.jsx
import "./Navbar.css";
import { useEffect, useRef, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import SpinningCoin from "../SpinningCoin/SpinningCoin.jsx";
import AccountMenu from "./AccountMenu.jsx";
import { useSession } from "../../hooks/useSession";


const base = import.meta.env.BASE_URL;

const Navbar = ({ theme: forcedTheme }) => {
  const [isOpen, setIsOpen] = useState(false);
  const [autoTheme, setAutoTheme] = useState(forcedTheme || "dark");
  const { user, isLoggedIn, loading } = useSession();

  const drawerRef = useRef(null);
  const btnRef = useRef(null);
  const navRef = useRef(null);
  const location = useLocation();


  const activeTheme = forcedTheme || autoTheme;
  const isLight = activeTheme === "light";
  const logoSrc = isLight ? `${base}cNormal.png` : `${base}cSolido.png`;

  // Bloquear scroll cuando el drawer está abierto
  useEffect(() => {
    const html = document.documentElement;
    const prev = html.style.overflow;
    html.style.overflow = isOpen ? "hidden" : prev || "";
    return () => {
      html.style.overflow = prev || "";
    };
  }, [isOpen]);

  // Cerrar con ESC y clic fuera del drawer
  useEffect(() => {
    if (!isOpen) return;
    const onKey = (e) => e.key === "Escape" && setIsOpen(false);
    const onClickOutside = (e) => {
      if (drawerRef.current && !drawerRef.current.contains(e.target)) {
        if (btnRef.current && btnRef.current.contains(e.target)) return; // si el click viene del botón, ignorar
        setIsOpen(false);
      }
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("click", onClickOutside);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("click", onClickOutside);
    };
  }, [isOpen]);

  // ===== Autodetección del tema (solo si NO hay forcedTheme) =====
  useEffect(() => {
    if (forcedTheme) return;

    // Fuera de "/", deja light por defecto
    if (location.pathname !== "/") {
      setAutoTheme("light");
      return;
    }

    const parseRGB = (str) => {
      const m = str?.match(
        /rgba?\(\s*(\d+)[,\s]+(\d+)[,\s]+(\d+)(?:[,\s]+([\d.]+))?\s*\)/
      );
      if (!m) return null;
      return {
        r: +m[1],
        g: +m[2],
        b: +m[3],
        a: m[4] ? parseFloat(m[4]) : 1,
      };
    };

    const getNonTransparentBG = (el) => {
      // Sube por el árbol buscando fondo no transparente
      let node = el;
      while (node && node !== document.documentElement) {
        const cs = getComputedStyle(node);
        const bg = parseRGB(cs.backgroundColor || "rgba(0,0,0,0)");
        if (bg && bg.a > 0) return bg;
        if (cs.backgroundImage && cs.backgroundImage !== "none") {
          // Con imagen asumimos claro (evita falsos oscuros por transparencias)
          return { r: 255, g: 255, b: 255, a: 1 };
        }
        node = node.parentElement;
      }
      // fallback oscuro
      return { r: 0, g: 0, b: 0, a: 1 };
    };

    const isLightBG = (rgb) => {
      const L =
        0.2126 * (rgb.r / 255) +
        0.7152 * (rgb.g / 255) +
        0.0722 * (rgb.b / 255);
      return L > 0.6;
    };

    const pickTheme = () => {
      // Y = justo debajo de la navbar (usamos bottom real)
      const navRect = navRef.current?.getBoundingClientRect();
      const navBottom = Math.round(navRect?.bottom ?? 0);
      const Y = Math.min(window.innerHeight - 2, navBottom + 1);

      // 1) Prioriza secciones con data-nav-theme que contengan ese Y
      let foundTheme = null;
      const sections = document.querySelectorAll("[data-nav-theme]");
      sections.forEach((el) => {
        const r = el.getBoundingClientRect();
        if (r.top <= Y && r.bottom > Y) {
          const t = el.getAttribute("data-nav-theme") || "dark";
          // aceptamos "light", "dark" o "brand" si decides usarlo
          if (t === "light" || t === "dark" || t === "brand") {
            foundTheme = t;
          }
        }
      });

      // 2) Fallback por brillo: hacemos hit-test ignorando la navbar
      if (!foundTheme) {
        const nav = navRef.current;
        const prevPE = nav?.style.pointerEvents;
        if (nav) nav.style.pointerEvents = "none"; // para que elementFromPoint no devuelva la navbar

        const xs = [
          16,
          Math.floor(window.innerWidth / 2),
          Math.max(16, window.innerWidth - 16),
        ];
        let lights = 0,
          darks = 0;
        xs.forEach((x) => {
          const target = document.elementFromPoint(x, Y) || document.body;
          const bg = getNonTransparentBG(target);
          isLightBG(bg) ? lights++ : darks++;
        });

        if (nav) nav.style.pointerEvents = prevPE ?? "";
        foundTheme = lights >= darks ? "light" : "dark";
      }

      setAutoTheme((prev) =>
        foundTheme && foundTheme !== prev ? foundTheme : prev
      );
    };

    let ticking = false;
    let rafId = 0;
    const onScroll = () => {
      if (!ticking) {
        rafId = window.requestAnimationFrame(() => {
          pickTheme();
          ticking = false;
        });
        ticking = true;
      }
    };

    pickTheme();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => {
      cancelAnimationFrame(rafId);
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
    };
  }, [forcedTheme, location.pathname]);

  const closeAnd = (fn) => () => {
    setIsOpen(false);
    if (typeof fn === "function") fn();
  };

  return (
    <>
      <nav
        ref={navRef}
        className={`navbar navbar--${activeTheme}`}
        aria-label="Principal"
      >
        {/* izquierda: links desktop */}
        <div className="nav-left nav-desktop">
          <a href="/#inicio">
            Inicio
          </a>
          <a href="/#learn-more">
            Descubre
          </a>
          <a href="/#conoce">
            Conoce
          </a>
          <a href="/#obten">
            Obtén el Tuyo
          </a>
        </div>

        {/* centro (logo) */}
        <div className="nav-logo" aria-label="Genomia logo">
          <button 
            onClick={() => window.location.href = '/'} 
            className="logo-link"
            style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}
          >
            <SpinningCoin src={logoSrc} size={60} speed="8s" />
          </button>
        </div>

        {/* derecha: links desktop */}
        <div className="nav-right nav-desktop">
          <a href="/#preguntas">Preguntas</a>
          <a href="/#equipo">Equipo</a>
          <a href="/#contacto">Contacto</a>
          {loading ? (
            <span className="nav-account-loading" aria-hidden="true" />
          ) : isLoggedIn ? (
            <AccountMenu user={user} theme={activeTheme} />
          ) : (
            <Link to="/login" className="login-btn">Inicia Sesión</Link>
          )}
        </div>

        {/* botón burger (solo mobile) */}
        <button
          ref={btnRef}
          className="nav-toggle"
          aria-label={isOpen ? "Cerrar menú" : "Abrir menú"}
          aria-expanded={isOpen}
          aria-controls="mobile-drawer"
          onClick={() => setIsOpen((v) => !v)}
        >
          {!isOpen ? (
            // burger
            <svg viewBox="0 0 24 24" width="26" height="26" aria-hidden="true">
              <path
                d="M3 6h18M3 12h18M3 18h18"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
              />
            </svg>
          ) : (
            // close
            <svg viewBox="0 0 24 24" width="26" height="26" aria-hidden="true">
              <path
                d="M6 6l12 12M18 6l-12 12"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
              />
            </svg>
          )}
        </button>
      </nav>

      {/* overlay + drawer mobile */}
      <div
        className={`drawer-overlay ${isOpen ? "is-open" : ""}`}
        aria-hidden={!isOpen}
      >
        <aside
          id="mobile-drawer"
          ref={drawerRef}
          className={`mobile-drawer navbar--${activeTheme}`}
          role="dialog"
          aria-label="Menú"
        >
          <div className="drawer-header">
            <button 
              onClick={() => window.location.href = '/'} 
              className="logo-link"
              style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}
            >
              <img src={logoSrc} alt="Genomia logo" />
            </button>
            <button
              className="drawer-close"
              aria-label="Cerrar menú"
              onClick={() => setIsOpen(false)}
            >
              <svg viewBox="0 0 24 24" width="26" height="26" aria-hidden="true">
                <path
                  d="M6 6l12 12M18 6l-12 12"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                />
              </svg>
            </button>
          </div>

          <nav className="drawer-links">
            <a href="/#inicio" onClick={closeAnd()}>
              Inicio
            </a>
            <a href="/#learn-more" onClick={closeAnd()}>
              Descubre
            </a>
            <a href="/#conoce" onClick={closeAnd()}>
              Conoce
            </a>
            <a href="/#obten" onClick={closeAnd()}>
              Obtén el Tuyo
            </a>

            <div className="drawer-sep" />

            <a href="/#preguntas" onClick={closeAnd()}>
              Preguntas
            </a>
            <a href="/#equipo" onClick={closeAnd()}>
              Equipo
            </a>
            <a href="/#contacto" onClick={closeAnd()}>
              Contacto
            </a>

            {loading ? (
              <span className="nav-account-loading" aria-hidden="true" />
            ) : isLoggedIn ? (
              <AccountMenu user={user} onNavigate={closeAnd} theme={activeTheme} />
            ) : (
              <Link to="/login" className="login-btn" onClick={closeAnd()}>
                Inicia Sesión
              </Link>
            )}
          </nav>
        </aside>
      </div>
    </>
  );
};

export default Navbar;
