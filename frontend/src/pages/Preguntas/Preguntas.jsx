import React, { useState } from 'react';
import './Preguntas.css';

const Preguntas = () => {
  const [openIndices, setOpenIndices] = useState([]);

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

  const handleToggle = (index) => {
    setOpenIndices(prevIndices => {
      const isCurrentlyOpen = prevIndices.includes(index);

      if (isCurrentlyOpen) {
        return prevIndices.filter(i => i !== index);
      } else {
        return [...prevIndices, index];
      }
    });
  };

  return (
    <section 
      id="preguntas"
      className="preguntas-section"
      data-nav-theme="brand"
    >
      <h1 className="title">Preguntas Frecuentes</h1>
      <p className="subtitle">
        Hemos recolectado las preguntas más populares para ayudarte a navegar
        correctamente. Escoge la pregunta que te interesa:
      </p>

      <div className="preguntas-grid">
        {faqData.map((item, index) => {
          const isOpen = openIndices.includes(index);

          return (
            <div 
              key={index} 
              className={`pregunta-card ${isOpen ? 'open' : ''}`}
            >
              <div 
                className="pregunta-header" 
                onClick={() => handleToggle(index)}
              >
                <span className="pregunta-text">{item.pregunta}</span>
                <div className="expand-btn">
                  <svg 
                    width="24" 
                    height="24" 
                    viewBox="0 0 24 24" 
                    fill="none" 
                    xmlns="http://www.w3.org/2000/svg"
                    // CAMBIO: Añadimos la clase 'rotated' al SVG contenedor
                    // para girar todo el icono ligeramente.
                    className={isOpen ? 'rotated' : ''}
                  >
                    <circle cx="12" cy="12" r="10" fill="white"/>
                    <path 
                      d="M8 12h8" 
                      stroke="#277EAF" 
                      strokeWidth="2" 
                      strokeLinecap="round"
                    />
                    <path 
                      d="M12 8v8" 
                      stroke="#277EAF" 
                      strokeWidth="2" 
                      strokeLinecap="round"
                      // CAMBIO CLAVE: Aplicamos la clase 'collapsed-path'
                      className={isOpen ? 'collapsed-path' : ''} 
                    />
                  </svg>
                </div>
              </div>
              
              {isOpen && (
                <div className="pregunta-content">
                  <p>{item.respuesta}</p>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
};

export default Preguntas;