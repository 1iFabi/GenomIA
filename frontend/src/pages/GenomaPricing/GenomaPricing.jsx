import React from 'react';
import { useNavigate } from 'react-router-dom';
import './GenomaPricing.css';
import '../../styles/breadcrumb.css';
import TiltedCard from '../../components/TiltedCard/TiltedCard';

// Íconos para bullets
const GlobeIcon = (props) => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true" {...props}>
    <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.8"/>
    <path d="M3 12h18" stroke="currentColor" strokeWidth="1.8"/>
    <path d="M12 3c3 3 3 15 0 18c-3-3-3-15 0-18Z" stroke="currentColor" strokeWidth="1.8"/>
  </svg>
);
const HealthIcon = (props) => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true" {...props}>
    <path d="M12 21s-7-4.5-9-8.2C1.3 10.2 3 6 7 6c2 0 3.3 1.2 5 3c1.7-1.8 3-3 5-3c4 0 5.7 4.2 4 6.8C19 16.5 12 21 12 21z" stroke="currentColor" strokeWidth="1.5" fill="none"/>
  </svg>
);
const BioIcon = (props) => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true" {...props}>
    <path d="M8 3v7l-4 7a2 2 0 0 0 1.7 3h12.6A2 2 0 0 0 20 17l-4-7V3" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M8 10h8M7 16h10" stroke="currentColor" strokeWidth="1.8"/>
  </svg>
);
const PillDnaIcon = (props) => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true" {...props}>
    <rect x="3" y="8" width="9" height="8" rx="4" stroke="currentColor" strokeWidth="1.8"/>
    <rect x="12" y="8" width="9" height="8" rx="4" stroke="currentColor" strokeWidth="1.8"/>
    <path d="M5 10c1.5 1 3 2 4 4M19 10c-1.5 1-3 2-4 4" stroke="currentColor" strokeWidth="1.4"/>
  </svg>
);

const GenomaPricing = () => {
  const navigate = useNavigate();
  const goRegister = () => navigate('/register');

  // Cambiamos a una lista de "¿Qué incluye tu paquete?" estilo tickets
  const includes = [
    { title: 'Descubre completo', desc: 'Ancestría, Enfermedades, Biométricas y Farmacogenética.' },
    { title: 'Acceso al panel en línea', desc: 'Consulta y seguimiento desde tu cuenta.' },
    { title: 'Actualizaciones futuras', desc: 'Nuevos insights y mejoras sin costo extra.' },
    { title: 'Acompañamiento del equipo', desc: 'Soporte por correo ante cualquier duda.' }
  ];

  const TicketCheck = (props) => (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true" {...props}>
      <circle cx="12" cy="12" r="11" stroke="#108AC2" strokeWidth="2" fill="#E6F4FE" />
      <path d="M7 12.5l3.2 3L17 9" stroke="#108AC2" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );

  return (
    <section id="obten" className="gp" data-nav-theme="light" aria-label="Precio de tu Genoma">
      <div className="gp-container">
        {/* Izquierda: título, texto y bullets */}
        <div className="gp-left">
          <div className="breadcrumb breadcrumb--blue">Obtén el Tuyo</div>

          <h2 className="gp-title">El precio de tu Genoma</h2>
          <p className="gp-lead">
            Accede a un plan completo con toda tu información genética, diseñado para ofrecerte un análisis detallado de tus rasgos, predisposiciones y bienestar.
          </p>

          <h3 className="gp-includes-heading">¿Qué incluye tu paquete?</h3>
          <ul className="gp-tickets" aria-label="Incluye">
            {includes.map(({ title, desc }, i) => (
              <li key={i} className="gp-ticket">
                <span className="gp-ticket-ico" aria-hidden="true"><TicketCheck /></span>
                <div className="gp-ticket-body">
                  <span className="gp-ticket-title">{title}</span>
                  <span className="gp-ticket-desc">{desc}</span>
                </div>
                <span className="gp-ticket-edge" aria-hidden="true" />
              </li>
            ))}
          </ul>

          <button className="gp-cta-main" onClick={goRegister}>
            Regístrate aquí
          </button>
        </div>

        {/* Derecha: card inclinada según mock */}
        <aside className="gp-right" aria-hidden="false">
          <div className="gp-right-tilt">
            <TiltedCard
              // Reemplaza la ruta por tu imagen de la card (ej: /assets/pricing-card.png)
              imageSrc={'/CardPricing.png'}
              altText="Plan GenomIA"
              captionText=""
              containerHeight="500px"
              containerWidth="380px"
              imageHeight="500px"
              imageWidth="380px"
              rotateAmplitude={12}
              scaleOnHover={1.03}
              showMobileWarning={false}
              showTooltip={false}
              displayOverlayContent={false}
            />
          </div>
        </aside>
      </div>
    </section>
  );
};

export default GenomaPricing;
