// SobreNosotros.jsx
import React from 'react';
import './SobreNosotros.css';
import '../../styles/breadcrumb.css';

// Iconos específicos para cada tarjeta
// Icono alternativo: documento con estrella (más claro/bonito)
const DocStarIcon = (props) => (
  <svg width="28" height="28" viewBox="0 0 24 24" fill="none" aria-hidden="true" {...props}>
    <g stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M8 4h5l3 3v11a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2Z"/>
      <path d="M13 4v3h3"/>
      <path d="M12 12l.9 1.8 2 .3-1.45 1.4.34 2-1.79-.95-1.79.95.34-2L9.1 14.1l2-.3L12 12Z"/>
    </g>
  </svg>
);

const LockIcon = (props) => (
  <svg width="28" height="28" viewBox="0 0 24 24" fill="none" aria-hidden="true" {...props}>
    <rect x="5" y="10" width="14" height="10" rx="2" stroke="currentColor" strokeWidth="1.8"/>
    <path d="M8 10V8a4 4 0 0 1 8 0v2" stroke="currentColor" strokeWidth="1.8"/>
    <circle cx="12" cy="15" r="1.6" fill="currentColor"/>
  </svg>
);

const LabIcon = (props) => (
  <svg width="28" height="28" viewBox="0 0 24 24" fill="none" aria-hidden="true" {...props}>
    <path d="M9 3v6l-5 9a2 2 0 0 0 1.7 3h12.6a2 2 0 0 0 1.7-3l-5-9V3" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M9 9h6" stroke="currentColor" strokeWidth="1.8"/>
    <path d="M7 16h10" stroke="currentColor" strokeWidth="1.8" opacity=".7"/>
  </svg>
);

const SobreNosotros = () => {
  const equipoMiembros = [
    { id: 'jonathan', nombre: 'Jonathan Canan', cargo: 'Encargado HPC-UOH', imagen: 'jonathan', imagenNum: '4', linkedin: 'https://www.linkedin.com/in/jonathan-canan-469896238' },
    { id: 'carol', nombre: 'Dra. Carol Moraga', cargo: 'Subdirectora SeqUOH', imagen: 'carol', imagenNum: '1', linkedin: 'https://www.linkedin.com/in/camoragaq' },
    { id: 'alex', nombre: 'Dr. Alex Di Genova', cargo: 'Director de SeqUOH', imagen: 'alex', imagenNum: '2', linkedin: 'https://www.linkedin.com/in/alex-di-genova-522b99246' },
    { id: 'susan', nombre: 'Mag. Susan Calfunao', cargo: 'Encargada de Lab. SeqUOH', imagen: 'susan', imagenNum: '3', linkedin: 'https://www.linkedin.com/in/susan-calfunao-caro-367a3173' },
    { id: 'gabriel', nombre: 'Gabriel Cabas', cargo: 'Investigador asociado SeqUOH', imagen: 'gabriel', imagenNum: '5', linkedin: 'https://www.linkedin.com/in/gabriel-cabas-1834601b4' }
  ];

  return (
    <section id="equipo" className="sn" data-nav-theme="light">
      {/* Breadcrumb / pastilla superior */}
      <div className="sn-crumb"><div className="breadcrumb breadcrumb--blue">Equipo</div></div>

      {/* Título principal */}
      <h1 className="sn-title">Somos GenomIA</h1>

      {/* Tarjetas informativas (3 columnas) */}
      <div className="sn-features">
        <article className="sn-feature">
          <div className="sn-icon"><DocStarIcon /></div>
          <h3 className="sn-feature-title">Tu ADN, Tu Historia</h3>
          <p className="sn-feature-desc">En GenomIA transformamos tu información genética en reportes claros, comprensibles y personalizados sobre ti.</p>
        </article>
        <article className="sn-feature">
          <div className="sn-icon"><LockIcon /></div>
          <h3 className="sn-feature-title">Tus datos son tuyos</h3>
          <p className="sn-feature-desc">Garantizamos encriptación, almacenamiento seguro y total control sobre tu información genética.</p>
        </article>
        <article className="sn-feature is-accent">
          <div className="sn-icon -invert"><LabIcon /></div>
          <h3 className="sn-feature-title">Detrás de GenomIA</h3>
          <p className="sn-feature-desc">Nacimos junto a SeqUOH, laboratorio genómico de la Universidad de O'Higgins, referente en investigación genética.</p>
        </article>
      </div>

      {/* Separador y título de equipo */}
      <h2 className="sn-team-title">Nuestro Equipo</h2>

      {/* Grid de personas */}
      <div className="equipo-grid">
        {equipoMiembros.map((miembro) => (
          <div key={miembro.id} className="miembro-card">
            <div className={`miembro-imagen ${miembro.imagen}`}>
              <img
                className="miembro-img"
                src={`/SobreNosotros/${miembro.imagenNum}.png`}
                alt={miembro.nombre}
                loading="lazy"
              />
            </div>
            <div className="miembro-info">
              <h3 className="miembro-nombre">{miembro.nombre}</h3>
              <p className="miembro-cargo">{miembro.cargo}</p>
              <a
                href={miembro.linkedin}
                className="linkedin-btn"
                target="_blank"
                rel="noopener noreferrer"
                aria-label={`Ver perfil de LinkedIn de ${miembro.nombre}`}
              >
                <svg className="linkedin-icon" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                  <path d="M4.98 3.5A2.5 2.5 0 1 1 0 3.5a2.5 2.5 0 0 1 4.98 0ZM.5 8.5h4.96V24H.5V8.5Zm7.5 0h4.76v2.05h.07c.66-1.27 2.26-2.6 4.66-2.6 4.98 0 5.91 3.33 5.91 7.66V24h-4.96v-6.92c0-1.65-.03-3.8-2.29-3.8-2.29 0-2.64 1.8-2.64 3.68V24H8V8.5Z"/>
                </svg>
                <span>LinkedIn</span>
              </a>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
};

export default SobreNosotros;
