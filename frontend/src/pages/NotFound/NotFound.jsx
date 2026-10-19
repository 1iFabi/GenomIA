import { Link } from "react-router-dom";
import "./NotFound.css";

const NotFound = () => {
  return (
    <main className="nf-page">
      <img
        className="nf-art"
        src="/genomin-404.webp"
        width="1340"
        height="878"
        alt="Error 404: Genomin, la mascota de GenomIA, asomado sobre el número 404"
      />
      <h1 className="nf-title">Parece que te perdiste…</h1>
      <Link to="/" className="nf-btn">
        Volver al inicio
      </Link>
    </main>
  );
};

export default NotFound;
