// src/components/Conoce/Conoce.jsx
import { useEffect, useRef, useState } from "react";
import "./Conoce.css";
import "../../styles/breadcrumb.css";

export default function Conoce() {
  const sectionRef = useRef(null);
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    const observer = new IntersectionObserver(
      ([entry]) => { if (entry.isIntersecting) setIsVisible(true); },
      { threshold: 0.3 }
    );
    if (sectionRef.current) observer.observe(sectionRef.current);
    return () => observer.disconnect();
  }, []);

  const steps = [
    {
      number: "1",
      title: "Realiza tu registro en el sistema",
      description: "Aquí obtendrás tus credenciales para acceder a tus resultados",
      icon: "register",
      delay: "0.2s",
    },
    {
      number: "2",
      title: "Ve al laboratorio a muestrearte",
      description: "Se te tomará una pequeña muestra de saliva para recolectar tu ADN",
      icon: "lab",
      delay: "0.4s",
    },
    {
      number: "3",
      title: "Espera el correo de afirmación",
      description: "Llegará un mensaje de confirmación a tu correo cuando tu test esté listo.",
      icon: "email",
      delay: "0.6s",
    },
    {
      number: "4",
      title: "Revisa en la web tus resultados",
      description: "Inicia sesión y revisa todo lo que tu genética tiene que decirte.",
      icon: "results",
      delay: "0.8s",
    },
  ];

  const renderIcon = (iconType) => {
    const iconProps = {
      width: "60",
      height: "60",
      fill: "none",
      stroke: "currentColor",
      strokeWidth: "1.5",
      strokeLinecap: "round",
      strokeLinejoin: "round",
      "aria-hidden": "true",
    };

    switch (iconType) {
      case "register":
        return (
          <svg {...iconProps} viewBox="0 0 24 24">
            <path d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
        );
      case "lab":
        return (
          <svg {...iconProps} viewBox="0 0 24 24">
            <path d="M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z" />
          </svg>
        );
      case "email":
        return (
          <svg {...iconProps} viewBox="0 0 24 24">
            <path d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
          </svg>
        );
      case "results":
        return (
          <svg {...iconProps} viewBox="0 0 24 24">
            <path d="M15 15l-2 5L9 9l11 4-5 2zm0 0l5 5M7.188 2.239l.777 2.897M5.136 7.965l-2.898-.777M13.95 4.05l-2.122 2.122m-5.657 5.656l-2.12 2.122" />
          </svg>
        );
      default:
        return null;
    }
  };

  return (
    <section
      id="conoce"
      className="conoce-section"
      data-nav-theme="brand"
      ref={sectionRef}
    >
      <div className="conoce-container">
        <div className="conoce-content">
          <div className={`conoce-header ${isVisible ? "animate" : ""}`}>
          <div className="breadcrumb breadcrumb--white">Conoce</div>
            <h2 className="conoce-title">¿Cómo funciona el mapeo?</h2>
            <p className="conoce-subtitle">
              Si quieres realizar un muestreo de tu ADN para conocer tu ancestría y la genómica de
              las enfermedades, rasgos y todo lo que te hace único, sigue lo siguiente:
            </p>
          </div>

          <div className="conoce-steps-grid">
            {steps.map((step, index) => (
              <div
                key={index}
                className={`conoce-step ${isVisible ? "animate" : ""}`}
                style={{ "--delay": step.delay }}
              >
                <div className="conoce-step-icon">{renderIcon(step.icon)}</div>
                <div className="conoce-step-badge">Paso {step.number}</div>
                <h3 className="conoce-step-title">{step.title}</h3>
                <div className="conoce-step-underline"></div>
                <p className="conoce-step-description">{step.description}</p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
