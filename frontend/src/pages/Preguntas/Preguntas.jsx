import React, { useRef, useState } from 'react';
import useScrollReveal from '../../lib/useScrollReveal';
import './Preguntas.css';

const faqData = [
  {
    pregunta: '¿Qué tipo de pruebas genéticas realiza el servicio?',
    respuesta: 'Realizamos un análisis genético amplio que incluye predisposición a enfermedades comunes, farmacogenética, rasgos biológicos, ancestría, biomarcadores y biométricas. El estudio se basa en el análisis de cientos de miles de marcadores genéticos relevantes, seleccionados por su respaldo científico, lo que permite entregar información útil y accionable sobre el ADN del usuario.'
  },
  {
    pregunta: '¿Los resultados genéticos garantizan que desarrollaré la enfermedad indicada?',
    respuesta: 'No. Los resultados genéticos no garantizan que una persona desarrollará una enfermedad. Indican predisposición o riesgo relativo, no certezas. La salud depende de múltiples factores como el estilo de vida, el ambiente y los antecedentes personales. Los resultados deben interpretarse como una herramienta informativa y preventiva, idealmente junto a un profesional de la salud.'
  },
  {
    pregunta: '¿Cuánto tiempo toma recibir los resultados de mi prueba genética?',
    respuesta: 'Una vez que la muestra llega al laboratorio, el proceso de análisis y validación de resultados suele tomar algunas semanas. Cuando el reporte está listo, el usuario recibe una notificación por correo electrónico con acceso a sus resultados a través de la plataforma.'
  },
  {
    pregunta: '¿Mis resultados genéticos están seguros y protegidos?',
    respuesta: 'Sí. El sistema está diseñado para minimizar el uso de datos personales. Cada muestra se procesa utilizando un SampleID único, que es enviado al usuario por correo al momento del registro. El laboratorio trabaja únicamente con este identificador, sin acceso a nombres, RUT u otros datos sensibles. De esta forma, los resultados genéticos no están directamente asociados a información personal identificable dentro del flujo de análisis.'
  },
  {
    pregunta: '¿Puedo hacer cambios en mi estilo de vida basados en los resultados de la prueba genética?',
    respuesta: 'Los resultados pueden servir como una guía orientativa para tomar decisiones informadas sobre nutrición, actividad física y hábitos generales. Sin embargo, no reemplazan la evaluación clínica. Siempre se recomienda consultar con profesionales de la salud antes de realizar cambios importantes en dieta, ejercicio o tratamientos médicos.'
  },
  {
    pregunta: '¿Las pruebas genéticas cubren todas las mutaciones posibles?',
    respuesta: 'No. El análisis se enfoca en las variantes genéticas más estudiadas y relevantes según la evidencia científica actual. Si bien se analizan cientos de miles de marcadores, no es posible cubrir todas las mutaciones existentes. La genética es un campo en constante evolución, por lo que los análisis se actualizan progresivamente a medida que surgen nuevos descubrimientos validados.'
  },
  {
    pregunta: '¿Puedo compartir mis resultados con familiares o con mi médico?',
    respuesta: 'Sí, los resultados son propiedad del usuario, ya que corresponden a su información genética personal. Puedes mostrarlos o compartirlos con quien estimes conveniente. Sin embargo, este reporte está diseñado exclusivamente para el análisis individual y no debe utilizarse como referencia clínica ni genética para otras personas, incluidos familiares. La empresa no se hace responsable por interpretaciones, decisiones o conclusiones realizadas por terceros a partir de un reporte que fue generado para una persona específica.'
  },
  {
    pregunta: '¿Qué tipos de ancestros se pueden identificar con el análisis genético?',
    respuesta: 'El análisis de ancestría estima la composición genética del usuario mediante la comparación con poblaciones de referencia de distintas regiones del mundo, incluyendo componentes europeos, africanos, asiáticos, nativos americanos y oceánicos, con subdivisiones regionales. Además, el análisis se apoya en una base de datos genética gestionada y contextualizada para población chilena, lo que permite interpretar ancestría, rasgos y predisposiciones considerando el contexto genético y estilo de vida predominante a nivel nacional, entregando resultados más acordes a la realidad local.'
  }
];

const VISIBLES = 5;

const Preguntas = () => {
  const [abierta, setAbierta] = useState(null);
  const [todas, setTodas] = useState(false);
  const scope = useRef(null);
  useScrollReveal(scope);
  const mascotaRef = useRef(null);
  const listaRef = useRef(null);

  const toggle = (index) => {
    const abre = abierta !== index;
    setAbierta(abre ? index : null);
    const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    if (abre && !reduce) {
      mascotaRef.current?.animate?.(
        [
          { transform: 'translateY(0) rotate(0)' },
          { transform: 'translateY(-14px) rotate(-3deg)', offset: 0.4 },
          { transform: 'translateY(0) rotate(0)' }
        ],
        { duration: 520, easing: 'cubic-bezier(0.22, 1, 0.36, 1)' }
      );
    }
  };

  const verMas = () => {
    setTodas(true);
    // lleva el foco a la primera pregunta revelada
    requestAnimationFrame(() => {
      listaRef.current?.querySelectorAll('.faq-q')[VISIBLES]?.focus();
    });
  };

  const items = todas ? faqData : faqData.slice(0, VISIBLES);

  return (
    <section id="preguntas" ref={scope} className="faq" data-nav-theme="brand">
      <div className="faq-inner">
        <div className="faq-aside">
          <h2 className="faq-title" data-reveal>
            Preguntas<span>frecuentes</span>
          </h2>
          <img
            ref={mascotaRef}
            className="faq-mascota"
            data-reveal
            src="/genomin-faq.webp"
            alt=""
            width="1078"
            height="1071"
            loading="lazy"
            decoding="async"
          />
        </div>

        <div className="faq-main">
          <ul className="faq-list" ref={listaRef}>
            {items.map((item, index) => {
              const isOpen = abierta === index;
              return (
                <li key={item.pregunta} className={`faq-item${isOpen ? ' is-open' : ''}`} data-reveal>
                  <h3>
                    <button
                      type="button"
                      id={`faq-q-${index}`}
                      className="faq-q"
                      onClick={() => toggle(index)}
                      aria-expanded={isOpen}
                      aria-controls={`faq-a-${index}`}
                    >
                      <span>{item.pregunta}</span>
                      <svg className="faq-chevron" viewBox="0 0 24 24" aria-hidden="true">
                        <path d="M6 9l6 6 6-6" />
                      </svg>
                    </button>
                  </h3>
                  <div
                    id={`faq-a-${index}`}
                    className="faq-a"
                    role="region"
                    aria-labelledby={`faq-q-${index}`}
                    inert={isOpen ? undefined : ''}
                  >
                    <div>
                      <p>{item.respuesta}</p>
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>

          <div className="faq-actions" data-reveal>
            {!todas && (
              <button type="button" className="faq-link" onClick={verMas}>
                Ver más preguntas
              </button>
            )}
            <a className="faq-link faq-link--soft" href="/#contacto">
              ¿Otra duda? Escríbenos
            </a>
          </div>
        </div>
      </div>
    </section>
  );
};

export default Preguntas;
