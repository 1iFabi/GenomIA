import { Link } from "react-router-dom";
import Iridescence from "../../components/Iridescence/Iridescence";
import "./NotFound.css";

const NotFound = () => {
  return (
    <div className="nf-page">
      {/* Fondo iridiscente en azul claro #7fbfe8 */}
      <div className="nf-bg" aria-hidden="true">
        <Iridescence
          color={[0.498, 0.749, 0.91]}
          speed={1.0}
          amplitude={0.1}
          mouseReact={false}
        />
      </div>

      {/* 404 + leyenda + botón gris claro */}
      <div className="nf-content">
        <div className="nf-code">404</div>
        <div className="nf-sub">PÁGINA NO ENCONTRADA</div>
        <Link to="/" className="nf-btn">
          Volver al inicio
        </Link>
      </div>
    </div>
  );
};

export default NotFound;
