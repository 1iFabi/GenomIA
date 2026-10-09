import { useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { API_ENDPOINTS, apiRequest } from "../../config/api.js";
import AuthPlate from "../../components/AuthPlate/AuthPlate.jsx";
import TermsModal from "../../components/TermsModal/TermsModal.jsx";
import "../Login/Login.css";
import "./GoogleSignup.css";
import logo from "/cNormal.png";

// Mismas reglas que el backend (accounts/username_validation.py).
const USERNAME_PATTERN = /^[a-z0-9_.-]{3,30}$/;

/** Segundo paso del registro con Google: elegir nombre de usuario y aceptar términos. */
export default function GoogleSignup() {
  const { state } = useLocation();
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [terms, setTerms] = useState(false);
  const [showTerms, setShowTerms] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  // Sin el token de Google (recarga o acceso directo) no hay nada que completar.
  if (!state?.pending) return <Navigate to="/login" replace />;

  const normalized = username.trim().toLowerCase();
  const usernameValid = USERNAME_PATTERN.test(normalized);

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (!usernameValid) {
      setError("Usa 3-30 caracteres: letras, números, _, - o .");
      return;
    }
    if (!terms) {
      setError("Debes aceptar los términos y condiciones");
      return;
    }
    setLoading(true);
    setError("");
    const { ok, data } = await apiRequest(API_ENDPOINTS.GOOGLE_COMPLETE, {
      method: "POST",
      body: JSON.stringify({ pending: state.pending, username: normalized, terminos: true }),
    });
    setLoading(false);
    if (ok && data.success) {
      navigate("/dashboard", { replace: true });
    } else {
      setError(data?.error || "No pudimos crear tu cuenta. Inténtalo nuevamente.");
    }
  };

  return (
    <div className="auth login-page google-signup-page">
      <section className="auth-left">
        <div className="left-inner">
          <div className="logo-container">
            <button type="button" className="google-signup-logo" onClick={() => navigate("/")} aria-label="Ir al inicio">
              <img src={logo} alt="" className="welcome-logo" draggable="false" />
            </button>
          </div>
          <h1 className="title">Un último paso</h1>
          <p className="subtitle">
            Elige tu nombre de usuario para <strong>{state.email}</strong>.
          </p>
          <div className="title-underline" />

          <form onSubmit={handleSubmit} className="login-form login-card form-container" noValidate>
            <div className={`uv-field ${error && !usernameValid ? "has-error" : ""}`}>
              <label htmlFor="google-username" className="uv-label">Nombre de usuario</label>
              <div className="uv-input-wrap">
                <input
                  className="uv-input"
                  id="google-username"
                  name="username"
                  value={username}
                  onChange={(event) => setUsername(event.target.value)}
                  autoComplete="username"
                  maxLength={30}
                  required
                  aria-invalid={!!error && !usernameValid}
                  aria-describedby="google-username-hint"
                />
                <span className="uv-focus-bg" />
              </div>
            </div>
            <p id="google-username-hint" className="google-signup-hint">3-30 caracteres: letras, números, _, - o .</p>

            <label className="remember-row">
              <input type="checkbox" checked={terms} onChange={(event) => setTerms(event.target.checked)} />
              <span>
                Acepto los{" "}
                <button type="button" className="login-link google-signup-terms" onClick={() => setShowTerms(true)}>
                  términos y condiciones
                </button>
              </span>
            </label>

            {error && <p className="google-signup-error" role="alert">{error}</p>}

            <button className="login-button" type="submit" disabled={loading}>
              {loading ? "Creando cuenta..." : "Crear mi cuenta"}
            </button>
          </form>
        </div>
      </section>

      <section className="auth-right">
        <AuthPlate />
      </section>

      {showTerms && <TermsModal onClose={() => setShowTerms(false)} />}
    </div>
  );
}
