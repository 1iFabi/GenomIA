import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { API_ENDPOINTS, apiRequest } from "../../config/api.js";
import "./GoogleAuthButton.css";

const GIS_SRC = "https://accounts.google.com/gsi/client";
const CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID;

export function AuthDivider({ children }) {
  return <div className="auth-divider">{children}</div>;
}

let gisPromise;
function loadGoogleIdentity() {
  gisPromise ??= new Promise((resolve, reject) => {
    if (window.google?.accounts?.id) return resolve(window.google.accounts.id);
    const script = document.createElement("script");
    script.src = GIS_SRC;
    script.async = true;
    script.onload = () => resolve(window.google.accounts.id);
    script.onerror = () => {
      gisPromise = undefined; // Permite reintentar en el próximo montaje.
      reject(new Error("Google Identity Services no cargó"));
    };
    document.head.appendChild(script);
  });
  return gisPromise;
}

/**
 * Botón oficial de Google (GIS). Es obligatorio usar el suyo: solo ese botón entrega
 * el ID token (`credential`) que el backend verifica. `onCredential` recibe ese token.
 */
export function GoogleCredentialButton({ onCredential, text = "continue_with" }) {
  const slotRef = useRef(null);
  const callbackRef = useRef(onCredential);
  callbackRef.current = onCredential;
  const [unavailable, setUnavailable] = useState(!CLIENT_ID);

  useEffect(() => {
    if (!CLIENT_ID) return undefined;
    let active = true;
    loadGoogleIdentity()
      .then((identity) => {
        const slot = slotRef.current;
        if (!active || !slot) return;
        identity.initialize({
          client_id: CLIENT_ID,
          callback: (response) => callbackRef.current(response.credential),
          ux_mode: "popup",
        });
        // GIS acepta un ancho fijo entre 200 y 400 px.
        const width = Math.max(200, Math.min(400, Math.round(slot.offsetWidth || 320)));
        identity.renderButton(slot, {
          theme: "outline", size: "large", shape: "pill", text, width, locale: "es",
        });
      })
      .catch(() => active && setUnavailable(true));
    return () => {
      active = false;
    };
  }, [text]);

  if (unavailable) {
    return <p className="google-auth-message">El acceso con Google no está disponible en este momento.</p>;
  }
  return <div ref={slotRef} className="google-auth-slot" />;
}

/**
 * Login y registro con Google: el backend decide si inicia sesión o pide un nombre de usuario.
 * `intent="signup"` (registro) hace que una cuenta ya existente se rechace en vez de abrirla.
 */
export default function GoogleAuthButton({ text = "continue_with", intent }) {
  const navigate = useNavigate();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const handleCredential = async (credential) => {
    setError("");
    setBusy(true);
    const { ok, data } = await apiRequest(API_ENDPOINTS.GOOGLE_LOGIN, {
      method: "POST",
      body: JSON.stringify({ credential, intent }),
    });
    setBusy(false);
    if (ok && data.needs_username) {
      navigate("/register/google", { state: { pending: data.pending, email: data.email } });
    } else if (ok && data.success) {
      navigate("/dashboard");
    } else {
      setError(data?.error || "No pudimos ingresar con Google. Inténtalo nuevamente.");
    }
  };

  return (
    <div className="google-auth" aria-busy={busy}>
      <GoogleCredentialButton onCredential={handleCredential} text={text} />
      {error && <p className="google-auth-message google-auth-message--error" role="alert">{error}</p>}
    </div>
  );
}
