// src/components/Descubre/Descubre.jsx
import { useEffect, useRef, useState } from "react";
import TextType from "../../components/TextType/TextType";
import "./Descubre.css";
import "../../styles/breadcrumb.css";

const Descubre = () => {
  const sectionRef = useRef(null);
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) setIsVisible(true);
      },
      { threshold: 0.3 }
    );
    if (sectionRef.current) observer.observe(sectionRef.current);
    return () => observer.disconnect();
  }, []);

  return (
    <section
      ref={sectionRef}
      className="descubre"
      data-nav-theme="light"
      id="learn-more"
      aria-label="Sección Descubre"
    >
      <div className="descubre-container">
        <div className="descubre-content">
          {/* Header */}
          <div className={`descubre-header ${isVisible ? "animate" : ""}`}>
<div className="breadcrumb breadcrumb--blue">Descubre</div>

            <h2 className="descubre-title">
              Descubre tus{" "}
              <TextType
                text={[
                  "Enfermedades",
                  "Ancestros",
                  "Biométricas",
                  "Rasgos Genéticos",
                  "Biomarcadores",
                ]}
                typingSpeed={75}
                pauseDuration={1500}
                showCursor={true}
                cursorCharacter="|"
                className="text-type-spacing"
              />
            </h2>

            <p className="descubre-subtitle">
              Transformamos tu ADN en reportes claros que revelan tu salud,
              rasgos, biometría y ancestría
            </p>
          </div>

          {/* GRID */}
          <div className={`features-grid ${isVisible ? "animate" : ""}`}>
            {/* 1. Farmacogenética */}
            <article className="feature-card">
              <div className="card-content">
                <h3 className="card-title">Farmacogenética</h3>
                <p className="card-description">
                  Optimiza tratamientos según tu genética para mayor eficacia y
                  menor riesgo de efectos adversos.
                </p>
              </div>
              <div className="card-image">
                <img src="/Descubree/Farmacogen.png" alt="Farmacogenética" />
              </div>
            </article>

            {/* 2. Enfermedades */}
            <article className="feature-card">
              <div className="card-content">
                <h3 className="card-title">Enfermedades</h3>
                <p className="card-description">
                  Reportes claros de predisposición genética para apoyar la
                  prevención y el cuidado personal.
                </p>
              </div>
              <div className="card-image">
                <img src="/Descubree/Enfermedades.png" alt="Farmacogenética" />
              </div>
            </article>

            {/* 3. Explora tus Orígenes (alta, span 2 filas) */}
            <article className="feature-card card-origenes">
              <header className="origenes-head">
                <h3 className="card-title">Explora tus Orígenes</h3>
                <p className="card-description">
                  Traza tus orígenes y la diversidad genética que compone tu historia familiar.
                </p>
              </header>

              {/* Imagen compuesta (pills + globo) */}
              <div className="origenes-art">
                <img
                  src="/Descubree/Ancestry.png"  /* usa tu ruta real */
                  alt="Distribución de ancestría"
                  loading="lazy"
                />
              </div>
            </article>

            {/* 4. Biométricas */}
            <article className="feature-card">
              <div className="card-content">
                <h3 className="card-title">Biométricas</h3>
                <p className="card-description">
                  Indicadores corporales influenciados por tus genes: metabolismo,
                  peso, altura y más.
                </p>
              </div>
              <div className="card-image">
                <img src="/Descubree/Biometric.png" alt="Farmacogenética" />
              </div>
            </article>

            {/* 5. Rasgos */}
            <article className="feature-card">
              <div className="card-content">
                <h3 className="card-title">Rasgos</h3>
                <p className="card-description">
                  Características determinadas por tu ADN: sueño, sabores,
                  energía y otros rasgos.
                </p>
              </div>
              <div className="card-image">
                <img src="/Descubree/Rasgos.png" alt="Farmacogenética" />
              </div>
            </article>
          </div>
        </div>
      </div>
    </section>
  );
};

export default Descubre;
