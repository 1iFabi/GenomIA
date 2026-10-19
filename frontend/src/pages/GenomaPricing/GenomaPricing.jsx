import { useRef } from 'react';
import { Link } from 'react-router-dom';
import { ArrowUpRight } from 'lucide-react';
import './GenomaPricing.css';
import '../../styles/breadcrumb.css';
import usePricingIntro from './usePricingIntro';
import DnaTurntable from './DnaTurntable';

const PRICE = '300.000';

const INCLUDED = [
  'Tu genoma completo',
  'Los cinco análisis, en un solo pago',
  'Genomin te explica tus resultados',
  'Panel en línea e informe en PDF',
  'Actualizaciones futuras sin costo',
  'Soporte del equipo por correo',
];

const GenomaPricing = () => {
  const scope = useRef(null);
  usePricingIntro(scope);

  return (
    <section id="obten" ref={scope} className="gp" data-nav-theme="light" aria-labelledby="gp-title">
      <div className="gp-container">
        <div className="breadcrumb breadcrumb--blue">Obtén el Tuyo</div>

        <div className="gp-main">
          {/* la hélice renderizada: decorativa, gira sola */}
          <div className="gp-stage" aria-hidden="true">
            <DnaTurntable />
          </div>

          <div className="gp-pkg">
            <div className="gp-pkg__head">
              <h2 id="gp-title" className="gp-pkg__name">GenomIA.vcf</h2>
              <p className="gp-price">
                <span className="gp-sr">{PRICE} pesos chilenos</span>
                <span className="gp-price__figure" aria-hidden="true">
                  $
                  {[...PRICE].map((c, i) =>
                    c === '.' ? c : <span key={i} className="gp-digit" data-d={c}>{c}</span>,
                  )}
                  <span className="gp-price__code">CLP</span>
                </span>
              </p>
            </div>

            <p className="gp-pkg__desc">Todo tu ADN, un solo pago. Sin suscripción.</p>

            <ul className="gp-pkg__list">
              {INCLUDED.map((item) => <li key={item}>{item}</li>)}
            </ul>

            <Link to="/register" className="gp-cta">
              Empieza tu análisis
              <ArrowUpRight aria-hidden="true" size={20} strokeWidth={1.6} />
            </Link>
          </div>
        </div>
      </div>
    </section>
  );
};

export default GenomaPricing;
