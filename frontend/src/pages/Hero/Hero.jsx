// src/components/Hero/Hero.jsx
import { useEffect, useRef } from "react";
import "./Hero.css";

export default function Hero() {
  const videoRef = useRef(null);
  const base = import.meta.env.BASE_URL;

  useEffect(() => {
    const mql = window.matchMedia("(prefers-reduced-motion: reduce)");
    if (mql.matches && videoRef.current) videoRef.current.pause();
  }, []);

  return (
    <section className="hero" data-nav-theme="dark" id="inicio">
      <div className="hero-media">
        <video
          ref={videoRef}
          className="hero-video"
          autoPlay
          muted
          loop
          playsInline
          preload="metadata"
          poster={`${base}HelixDNA-poster.webp`}
          src={`${base}HelixDNA.webm`}
        ></video>
        <div className="hero-overlay" />
      </div>
      
      {/* The .hero-rail div is no longer here */}

      <div className="hero-bl">

        <h1 className="hero-title">
          Descubre la historia que tu<br />ADN tiene para contarte.
        </h1>
      </div>

      <div className="hero-br">
        <p className="hero-kicker">Explora tu mapa genético de manera clara, confiable e interactiva.</p>
        <a href="login" className="cta">Ingresa Aquí <span aria-hidden></span></a>
      </div>
    </section>
  );
}