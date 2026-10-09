import { useEffect, useRef } from "react";
import "./TermsModal.css";

const FOCUSABLE = [
  "a[href]", "button:not([disabled])", 'input:not([disabled]):not([type="hidden"])',
  "select:not([disabled])", "textarea:not([disabled])", '[tabindex]:not([tabindex="-1"])',
].join(",");

/** Términos y condiciones de GenomIA, compartidos por el registro con contraseña y con Google. */
export default function TermsModal({ onClose }) {
  const modalRef = useRef(null);
  const closeButtonRef = useRef(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  // Foco atrapado dentro del modal; Escape cierra y el foco vuelve a donde estaba.
  useEffect(() => {
    const previous = document.activeElement;
    const modal = modalRef.current;
    const focusables = () => Array.from(modal.querySelectorAll(FOCUSABLE));
    (closeButtonRef.current || modal).focus({ preventScroll: true });

    const onKeyDown = (event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onCloseRef.current();
        return;
      }
      if (event.key !== "Tab") return;
      const items = focusables();
      if (items.length === 0) {
        event.preventDefault();
        modal.focus();
        return;
      }
      const index = items.indexOf(document.activeElement);
      const leaving = event.shiftKey ? index <= 0 : index === -1 || index === items.length - 1;
      if (leaving) {
        event.preventDefault();
        items[event.shiftKey ? items.length - 1 : 0].focus();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      if (previous && document.contains(previous)) previous.focus();
    };
  }, []);

  return (
    <div className="terms-modal-overlay" onClick={onClose}>
      <div
        ref={modalRef}
        className="terms-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="terms-modal-title"
        tabIndex="-1"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="terms-modal-header">
          <h2 id="terms-modal-title">Términos y Condiciones de Genomia</h2>
          <button
            ref={closeButtonRef}
            className="terms-modal-close"
            onClick={onClose}
            aria-label="Cerrar"
          >
            ×
          </button>
        </div>
        <div className="terms-modal-content">
          <p>Bienvenido a Genomia. Al utilizar nuestros servicios, usted acepta los siguientes términos y condiciones. Por favor, léalos con atención.</p>
          
          <h3>1. Aceptación de los Términos</h3>
          <p>Al acceder y utilizar nuestro sitio web y servicios, usted confirma que ha leído, entendido y aceptado estar sujeto a estos Términos y Condiciones. Si no está de acuerdo con alguna parte de los términos, no podrá utilizar nuestros servicios.</p>
          
          <h3>2. Descripción del Servicio</h3>
          <p>Genomia ofrece servicios de análisis de ADN para determinar la ascendencia genética de nuestros usuarios, con un enfoque en la población chilena. Utilizamos bases de datos genéticas de referencia chilenas para proporcionar informes de ascendencia personalizados.</p>
          
          <h3>3. Requisitos para el Uso del Servicio</h3>
          <p>Para utilizar nuestros servicios, usted debe:</p>
          <ul>
            <li>Ser mayor de 18 años.</li>
            <li>Proporcionar una muestra de saliva para el análisis de ADN.</li>
            <li>Garantizar que la muestra de saliva que proporciona es suya.</li>
          </ul>
          
          <h3>4. Consentimiento Informado</h3>
          <p>El análisis genético es una decisión personal importante. Antes de utilizar nuestros servicios, usted debe otorgar su consentimiento informado, lo que significa que reconoce y acepta lo siguiente:</p>
          
          <h4>Naturaleza de la Información Genética:</h4>
          <p>Su información genética es única y personal. Los resultados de su análisis pueden revelar información inesperada sobre usted y su familia.</p>
          
          <h4>Uso de sus Datos:</h4>
          <p>Al aceptar estos términos, usted autoriza a Genomia a recolectar, procesar y almacenar su muestra de saliva y los datos genéticos derivados de ella con el fin de proporcionarle su informe de ascendencia.</p>
          
          <h4>Investigación y Desarrollo:</h4>
          <p>Usted puede optar por consentir que sus datos genéticos, de forma anónima y agregada, sean utilizados para fines de investigación y desarrollo para mejorar nuestros servicios y contribuir al conocimiento científico de la ascendencia chilena. Este consentimiento es voluntario y puede ser revocado en cualquier momento.</p>
          
          <h4>Riesgos y Limitaciones:</h4>
          <ul>
            <li>Los resultados de ascendencia son estimaciones basadas en los datos actuales y pueden cambiar a medida que la ciencia y nuestras bases de datos evolucionan.</li>
            <li>La información genética que comparte podría tener implicaciones sociales, legales o económicas.</li>
            <li>A pesar de nuestras medidas de seguridad, no podemos garantizar al 100% la seguridad de sus datos.</li>
          </ul>
          
          <h3>5. Privacidad y Protección de Datos</h3>
          <p>En Genomia, nos tomamos muy en serio su privacidad. Nuestra política de privacidad se rige por las Leyes N° 19.628 sobre Protección de la Vida Privada de Chile y la Ley N° 21.719 de Protección de datos.</p>
          
          <h4>Datos Sensibles:</h4>
          <p>Reconocemos que sus datos genéticos son "datos sensibles" según la legislación chilena. Nos comprometemos a protegerlos con los más altos estándares de seguridad.</p>
          
          <h4>Confidencialidad:</h4>
          <p>No compartiremos sus datos personales ni genéticos con terceros sin su consentimiento explícito, a menos que sea requerido por una orden judicial.</p>
          
          <h4>Derechos del Titular de los Datos:</h4>
          <p>Usted tiene derecho a:</p>
          <ul>
            <li>Acceder a sus datos personales y genéticos.</li>
            <li>Solicitar la rectificación o cancelación de sus datos.</li>
            <li>Oponerse al tratamiento de sus datos para fines que no sean los originalmente consentidos.</li>
          </ul>
          <p>Para ejercer estos derechos, puede contactarnos a través de Contacto.</p>
          
          <h4>Almacenamiento de Muestras:</h4>
          <p>Su muestra de saliva será almacenada de forma segura en nuestras instalaciones. Usted puede solicitar la destrucción de su muestra en cualquier momento.</p>
          
          <h3>6. Cuenta de Usuario y Seguridad</h3>
          <p>Usted es responsable de mantener la confidencialidad de su contraseña y de todas las actividades que ocurran en su cuenta. Notifíquenos inmediatamente sobre cualquier uso no autorizado de su cuenta.</p>
          
          <h3>7. Propiedad Intelectual</h3>
          <p>Todo el contenido de este sitio web, incluyendo textos, gráficos, logos e informes, es propiedad de GenomIA y está protegido por las leyes de propiedad intelectual.</p>
          
          <h3>8. Limitación de Responsabilidad</h3>
          <p>Genomia no será responsable por ninguna decisión o acción que usted tome basada en los resultados de su análisis de ascendencia. El servicio se proporciona "tal cual" y no garantizamos que los resultados sean 100% precisos o completos.</p>
          
          <h3>9. Modificaciones a los Términos y Condiciones</h3>
          <p>Nos reservamos el derecho de modificar estos Términos y Condiciones en cualquier momento. Las modificaciones entrarán en vigencia desde su publicación en nuestro sitio web. Le recomendamos revisar esta página periódicamente.</p>
          
          <h3>10. Ley Aplicable y Jurisdicción</h3>
          <p>Estos Términos y Condiciones se regirán e interpretarán de acuerdo con las leyes de la República de Chile. Cualquier disputa que surja en relación con estos términos será sometida a la jurisdicción de los tribunales de Rancagua, Chile.</p>
          
          <h3>11. Contacto</h3>
          <p>Si tiene alguna pregunta sobre estos Términos y Condiciones, por favor contáctenos en: seq@uoh.cl.</p>
        </div>
        <div className="terms-modal-footer">
          <button 
            className="terms-modal-accept"
            onClick={onClose}
          >
            Cerrar
          </button>
        </div>
      </div>
    </div>
  );
}
