// SobreNosotros.jsx
import React, { useRef } from 'react';
import { BookOpenText, FlaskConical, Lock } from 'lucide-react';
import useScrollReveal from '../../lib/useScrollReveal';
import './SobreNosotros.css';
import '../../styles/breadcrumb.css';

const SobreNosotros = () => {
  const scope = useRef(null);
  useScrollReveal(scope);
  const equipoMiembros = [
    { id: 'jonathan', nombre: 'Joaquin Soto', cargo: 'Encargado HPC-UOH', imagen: 'joaquin', imagenNum: '4', linkedin: 'https://www.linkedin.com/in/joaquin-soto-17b263332/' },
    { id: 'carol', nombre: 'Dra. Carol Moraga', cargo: 'Subdirectora SeqUOH', imagen: 'carol', imagenNum: '1', linkedin: 'https://www.linkedin.com/in/camoragaq' },
    { id: 'alex', nombre: 'Dr. Alex Di Genova', cargo: 'Director de SeqUOH', imagen: 'alex', imagenNum: '2', linkedin: 'https://www.linkedin.com/in/alex-di-genova-522b99246' },
    { id: 'susan', nombre: 'Mag. Susan Calfunao', cargo: 'Encargada de Lab. SeqUOH', imagen: 'susan', imagenNum: '3', linkedin: 'https://www.linkedin.com/in/susan-calfunao-caro-367a3173' },
    { id: 'gabriel', nombre: 'Gabriel Cabas', cargo: 'Investigador asociado SeqUOH', imagen: 'gabriel', imagenNum: '5', linkedin: 'https://www.linkedin.com/in/gabriel-cabas-1834601b4' }
  ];

  return (
    <section id="equipo" ref={scope} className="sn" data-nav-theme="light">
      {/* Breadcrumb / pastilla superior */}
      <div className="sn-crumb" data-reveal><div className="breadcrumb breadcrumb--blue">Equipo</div></div>

      {/* Título principal */}
      <h1 className="sn-title" data-reveal>Somos GenomIA</h1>

      {/* Tarjetas informativas (3 columnas) */}
      <div className="sn-features">
        <article className="sn-feature" data-reveal>
          <div className="sn-icon"><BookOpenText size={28} aria-hidden="true" /></div>
          <h3 className="sn-feature-title">Tu ADN, Tu Historia</h3>
          <p className="sn-feature-desc">En GenomIA transformamos tu información genética en reportes claros, comprensibles y personalizados sobre ti.</p>
        </article>
        <article className="sn-feature" data-reveal>
          <div className="sn-icon"><Lock size={28} aria-hidden="true" /></div>
          <h3 className="sn-feature-title">Tus datos son tuyos</h3>
          <p className="sn-feature-desc">Garantizamos encriptación, almacenamiento seguro y total control sobre tu información genética.</p>
        </article>
        <article className="sn-feature is-accent" data-reveal>
          <div className="sn-icon -invert"><FlaskConical size={28} aria-hidden="true" /></div>
          <h3 className="sn-feature-title">Detrás de GenomIA</h3>
          <p className="sn-feature-desc">Nacimos junto a SeqUOH, laboratorio genómico de la Universidad de O'Higgins, referente en investigación genética.</p>
        </article>
      </div>

      {/* Separador y título de equipo */}
      <h2 className="sn-team-title" data-reveal>Nuestro Equipo</h2>

      {/* Grid de personas */}
      <div className="equipo-grid">
        {equipoMiembros.map((miembro) => (
          <div key={miembro.id} className="miembro-card" data-reveal>
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
