import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { clearToken, API_ENDPOINTS, apiRequest } from "../../config/api";
import "./NoPurchased.css";
import logo from "/cNormal.png";

export default function NoPurchased() {
  const [user, setUser] = useState(null);
  const navigate = useNavigate();

  useEffect(() => {
    let mounted = true;
    (async () => {
      const response = await apiRequest(API_ENDPOINTS.ME, { method: 'GET' });
      if (!mounted) return;
      if (response.ok) {
        setUser(response.data.user ?? response.data);
      }
    })();
    return () => { mounted = false; };
  }, []);

  const handleLogout = () => {
    clearToken();
    navigate("/login", { replace: true });
  };

  const steps = [
    { number: "01", label: "Dirección del laboratorio", value: "Av. Libertador Bernardo O'Higgins 611, Rancagua" },
    { number: "02", label: "Horario de atención", value: "08:30 – 16:30 hrs" },
    { number: "03", label: "Para el procedimiento", value: "Preséntate con tu Sample ID (Está en tu correo)" },
  ];

  return (
    <div className="no-purchased-page">
      <div className="split">
        {/* Panel de marca */}
        <aside className="split-brand">
          <button
            type="button"
            className="split-logo-button"
            onClick={() => navigate("/")}
            aria-label="Ir al inicio"
          >
            <img src={logo} alt="GenomIA Logo" className="split-logo" draggable="false" />
          </button>

          <div className="split-status">
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="9" />
              <path d="M12 8h.01M11 12h1v4h1" />
            </svg>
            <span>Servicio no adquirido</span>
          </div>

          <div className="split-brand-copy">
            <h1 className="split-title">
              ¡Bienvenido a <span className="brand-name">GenomIA</span>!
            </h1>
            {user && (
              <p className="split-greeting">Hola, {user.first_name || user.email}</p>
            )}
          </div>

          <button className="logout-button" onClick={handleLogout}>
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4m7 14 5-5-5-5m5 5H9" />
            </svg>
            Cerrar sesión
          </button>
        </aside>

        {/* Panel informativo */}
        <section className="split-content">
          <h2 className="content-title">¿Cómo realizar tu examen?</h2>

          <ol className="steps-list">
            {steps.map((step) => (
              <li key={step.number} className="step">
                <span className="step-number" aria-hidden="true">{step.number}</span>
                <div className="step-body">
                  <span className="step-label">{step.label}</span>
                  <span className="step-value">{step.value}</span>
                </div>
              </li>
            ))}
          </ol>

          <div className="contact-section">
            <span className="contact-text">¿Tienes dudas? Contáctanos:</span>
            <a className="contact-chip" href="mailto:seqgenomia@gmail.com">
              <span className="contact-chip__icon" aria-hidden="true">
                <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="3" y="5" width="18" height="14" rx="2" />
                  <path d="m3 7 8.06 5.26a2 2 0 0 0 1.88 0L21 7" />
                </svg>
              </span>
              <span className="contact-chip__text">
                <span className="contact-chip__label">Correo</span>
                <span className="contact-chip__value">seqgenomia@gmail.com</span>
              </span>
            </a>
          </div>
        </section>
      </div>
    </div>
  );
}
