import React, { useState, useEffect } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { API_ENDPOINTS, apiRequest } from "../../config/api.js";
import ErrorMessage from "../../components/Errormessage.jsx";
import "./Login.css";
import ForgotPasswordModal from "./ForgotPasswordModal.jsx";
import ResetPasswordModal from "./ResetPasswordModal.jsx";
import VerificationModal from "./VerificationModal.jsx";
import logo from "/cNormal.png";
import cromo from "/login.png";

export default function Login() {
  const [form, setForm] = useState({ email: "", password: "" });
  const [showPwd, setShowPwd] = useState(false);
  const [remember, setRemember] = useState(false);
  const [loading, setLoading] = useState(false);
  const [isTransitioning, setIsTransitioning] = useState(false);
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();

  const [errors, setErrors] = useState({ email: '', password: '', global: '' });
  const [loginSuccess, setLoginSuccess] = useState(false);
  const [showSuccessModal, setShowSuccessModal] = useState(false);
  const [showForgotPassword, setShowForgotPassword] = useState(false);
  const [showResetPassword, setShowResetPassword] = useState(false);
  const [resetToken, setResetToken] = useState('');
  // Modal de verificación de cuenta (via cookies)
  const [showVerificationModal, setShowVerificationModal] = useState(false);
  const [verificationMessage, setVerificationMessage] = useState('');

  const onChange = (e) => {
    const { name, value } = e.target;
    setForm((f) => ({ ...f, [name]: value }));
    // Limpiar error del campo al escribir
    setErrors((prev) => ({ ...prev, [name === 'email' ? 'email' : name]: '' }));
  };

  // La sesión vive en cookie HttpOnly (no localStorage): no se cierra desde aquí.
  useEffect(() => {}, []);

// Detectar si hay un token de reset en la URL
  useEffect(() => {
    const token = searchParams.get('token');
    const forgot = searchParams.get('forgot');
    
    if (token) {
      // Mostrar SOLO el modal de restablecer contraseña, sin modales intermedios
      setResetToken(token);
      setShowResetPassword(true);
      // Limpiar la URL después de obtener el token
      window.history.replaceState({}, document.title, '/login');
    } else if (forgot) {
      // Abrir modal de "Olvidé mi contraseña"
      setShowForgotPassword(true);
      // Limpiar la URL
      window.history.replaceState({}, document.title, '/login');
    }
  }, [searchParams]);

// Leer cookies de verificación Y parámetro verified en URL
  useEffect(() => {
    const getCookie = (name) => {
      const cookies = document.cookie.split('; ');
      const found = cookies.find(row => row.startsWith(name + '='));
      return found ? found.split('=')[1] : null;
    };

    // Primero verificar si hay parámetro verified en URL
    const verifiedParam = searchParams.get('verified');
    
    // Leer cookies
    const status = getCookie('verification_status');
    let message = getCookie('verification_message');

    // Debug: ver qué recibimos
    console.log('[Verification Check]', { verifiedParam, status, message, allCookies: document.cookie });

    // Si hay verified=1 en URL o cookie de status
    if (verifiedParam === '1' || status === '1') {
      let finalMessage = 'Tu cuenta fue verificada correctamente. Ya puedes iniciar sesión.';
      
      if (message) {
        try {
          finalMessage = decodeURIComponent(message);
          // Quitar comillas envolventes si las hay
          if ((finalMessage.startsWith('"') && finalMessage.endsWith('"')) || 
              (finalMessage.startsWith("'") && finalMessage.endsWith("'"))) {
            finalMessage = finalMessage.slice(1, -1);
          }
        } catch (e) {
          console.error('Error decoding message:', e);
        }
      }
      
      setVerificationMessage(finalMessage);
      setShowVerificationModal(true);

      // Limpiar cookies y URL
      document.cookie = 'verification_status=; Max-Age=0; Path=/; SameSite=Lax';
      document.cookie = 'verification_message=; Max-Age=0; Path=/; SameSite=Lax';
      if (verifiedParam) {
        window.history.replaceState({}, document.title, '/login');
      }
    } else if (status === '0') {
      // Error en verificación
      let errorMsg = 'Ocurrió un error al verificar la cuenta.';
      if (message) {
        try {
          errorMsg = decodeURIComponent(message);
          if ((errorMsg.startsWith('"') && errorMsg.endsWith('"')) || 
              (errorMsg.startsWith("'") && errorMsg.endsWith("'"))) {
            errorMsg = errorMsg.slice(1, -1);
          }
        } catch (e) {}
      }
      setVerificationMessage(errorMsg);
      setShowVerificationModal(true);
      
      // Limpiar cookies
      document.cookie = 'verification_status=; Max-Age=0; Path=/; SameSite=Lax';
      document.cookie = 'verification_message=; Max-Age=0; Path=/; SameSite=Lax';
    }
  }, [searchParams]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setErrors({ email: '', password: '', global: '' });
    
    try {
      const result = await apiRequest(API_ENDPOINTS.LOGIN, {
        method: 'POST',
        body: JSON.stringify({
          username: form.email,
          password: form.password,
          remember
        }),
      });
      
      if (result.ok && result.data.success) {
        // El token viaja en cookie HttpOnly; no se guarda en localStorage.
        setLoginSuccess(true);
        setShowSuccessModal(true);
        setTimeout(() => {
          // Generar session ID único y legible
          const generateSessionId = () => {
            const timestamp = Date.now().toString(36);
            const randomPart = Math.random().toString(36).substring(2, 9);
            return `${timestamp}${randomPart}`.toUpperCase();
          };
          const sessionId = generateSessionId();
          navigate(`/dashboard?session=${sessionId}`);
        }, 600);
      } else {
        // Mapear errores del backend a campos específicos cuando sea posible
        const { status, data } = result;
        let fieldErrors = { email: '', password: '', global: '' };

        // DRF puede devolver { username: ["..."], password: ["..."] }
        // También puede devolver { error: "..." } o { detail: "..." }
        const messages = [];

        if (data) {
          // Username backend mapea a 'email' en UI
          if (data.username) {
            fieldErrors.email = Array.isArray(data.username) ? data.username.join(' ') : String(data.username);
          }
          if (data.email) {
            fieldErrors.email = Array.isArray(data.email) ? data.email.join(' ') : String(data.email);
          }
          if (data.password) {
            fieldErrors.password = Array.isArray(data.password) ? data.password.join(' ') : String(data.password);
          }
          if (data.detail) messages.push(data.detail);
          if (data.error) messages.push(data.error);
        }

        // 400/401 Invalid credentials: marcar ambos campos cuando no hay error específico
        if ((status === 400 || status === 401) && !fieldErrors.email && !fieldErrors.password) {
          fieldErrors.email = 'error'; // solo para marcar el campo en rojo
          fieldErrors.password = 'error'; // solo para marcar el campo en rojo
        }

        // Si no hay errores de campo específicos, usar global (solo para debug interno)
        const globalMsg = messages.join(' ').trim() || 'No se pudo iniciar sesión';
        if (!fieldErrors.email && !fieldErrors.password) {
          fieldErrors.global = globalMsg;
        }

        console.log('[Login Error Debug]', { status, data, fieldErrors });
        setErrors(fieldErrors);
      }
    } catch (error) {
      console.error('Error de conexión:', error);
      setErrors({ email: '', password: '', global: 'Error de conexión con el servidor. Verifica que el backend esté ejecutándose.' });
    } finally {
      setLoading(false);
    }
  };

  const handleRegisterClick = (e) => {
    e.preventDefault();
    setIsTransitioning(true);
    
    // Esperar a que termine la animación de salida
    setTimeout(() => {
      navigate('/register');
    }, 150); // ← Reducido de 300ms a 150ms
  };

  return (
    <div className={`auth login-page ${isTransitioning ? 'page-exit' : 'page-enter'}`}>
      {/* Columna izquierda */}
      <section className="auth-left">
        <div className="left-inner">
          <div className="logo-container">
            <button
              type="button"
              onClick={() => navigate('/')}
              style={{ background: 'none', border: 'none', padding: 0, cursor: 'pointer' }}
            >
              <img src={logo} alt="Logo cNormal" className="welcome-logo" draggable="false" />
            </button>
          </div>
          <h1 className="title">¡Bienvenido!</h1>
          <p className="subtitle">Ingresa tu correo y contraseña para acceder a tu cuenta.</p>
          <div className="title-underline" />

          <form onSubmit={handleSubmit} className="login-form login-card form-container">
            {/* Email */}
                <div className="field-with-error-wrapper">
                  <div className={`uv-field ${errors.email ? 'has-error' : ''}`}>
                    <label className="uv-label">Correo</label>
                    <div className="uv-input-wrap">
                      <span className="uv-icon" aria-hidden="true">
                        <svg viewBox="0 0 24 24" width="20" height="20">
                          <path
                            d="M20 8l-8 5-8-5V6l8 5 8-5v2zm0 3v7H4v-7l8 5 8-5z"
                            fill="currentColor"
                          />
                        </svg>
                      </span>
                      <input
                        className={`uv-input ${errors.email ? 'error' : ''}`}
                        type="email"
                        name="email"
                        value={form.email}
                        onChange={onChange}
                        autoComplete="username"
                        required
                        aria-invalid={!!errors.email}
                        aria-describedby={errors.email ? 'email-error' : undefined}
                      />
                      <span className="uv-focus-bg" />
                    </div>
                  </div>
                  {errors.email && errors.email !== 'error' && (
                    <div className="error-message-right">
                      <ErrorMessage message={errors.email} small={true} />
                    </div>
                  )}
                </div>

                {/* Password */}
                <div className="field-with-error-wrapper">
                  <div className={`uv-field ${errors.password ? 'has-error' : ''}`}>
                    <label className="uv-label">Contraseña</label>
                    <div className="uv-input-wrap">
                      <span className="uv-icon" aria-hidden="true">
                        <svg viewBox="0 0 24 24" width="20" height="20">
                          <path
                            d="M17 10h-1V7a4 4 0 10-8 0v3H7a2 2 0 00-2 2v7a2 2 0 002 2h10a2 2 0 002-2v-7a2 2 0 00-2-2zm-6 0V7a3 3 0 016 0v3h-6z"
                            fill="currentColor"
                          />
                        </svg>
                      </span>
                      <input
                        className={`uv-input ${errors.password ? 'error' : ''}`}
                        type={showPwd ? "text" : "password"}
                        name="password"
                        value={form.password}
                        onChange={onChange}
                        autoComplete="current-password"
                        required
                        aria-invalid={!!errors.password}
                        aria-describedby={errors.password ? 'password-error' : undefined}
                      />
                      <span className="uv-focus-bg" />
                      <button
                        type="button"
                        className="pwd-toggle"
                        onClick={() => setShowPwd((s) => !s)}
                        aria-label={showPwd ? "Ocultar contraseña" : "Mostrar contraseña"}
                        tabIndex="-1"
                      >
                        {showPwd ? (
                          <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                            <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7z"/>
                            <circle cx="12" cy="12" r="3"/>
                          </svg>
                        ) : (
                          <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                            <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7z"/>
                            <line x1="4" y1="4" x2="20" y2="20"/>
                          </svg>
                        )}
                      </button>
                    </div>
                  </div>
                  {errors.password && errors.password !== 'error' && (
                    <div className="error-message-right">
                      <ErrorMessage message={errors.password} small={true} />
                    </div>
                  )}
                </div>

                {/* Recordar cuenta */}
                <label className="remember-row">
                  <input
                    type="checkbox"
                    checked={remember}
                    onChange={(e) => setRemember(e.target.checked)}
                  />
                  <span>Recordar mi cuenta</span>
                </label>

                {/* Botón de login */}
            <button className="login-button" type="submit" disabled={loading}>
              {loading ? "Ingresando..." : "Ingresa tu cuenta"}
            </button>


            <p className="login-help">
              ¿No tienes cuenta?{" "}
              <a className="login-link" href="#" onClick={handleRegisterClick}>
                Regístrate
              </a>
            </p>

            <button 
              type="button" 
              className="login-link subtle"
              onClick={() => setShowForgotPassword(true)}
            >
              ¿Olvidaste tu contraseña?
            </button>
          </form>
        </div>
      </section>

      {/* Columna derecha (imagen) */}
      <section className="auth-right">
        <img src={cromo} alt="imagen de cromosomas" />
      </section>

      {/* Modal de éxito */}
      {showSuccessModal && (
        <div className="success-modal-overlay">
          <div className="success-modal">
            <div className="success-icon">
              <svg viewBox="0 0 24 24" width="64" height="64" fill="none">
                <circle 
                  cx="12" 
                  cy="12" 
                  r="10" 
                  stroke="#10b981" 
                  strokeWidth="2.5"
                  strokeDasharray="63"
                  strokeDashoffset="63"
                  className="success-circle"
                />
                <path 
                  d="M9 12l2 2 4-4" 
                  stroke="#10b981" 
                  strokeWidth="2.5" 
                  strokeLinecap="round" 
                  strokeLinejoin="round"
                  strokeDasharray="8"
                  strokeDashoffset="8"
                  className="success-check"
                />
              </svg>
            </div>
            <h2 className="success-title">Login exitoso</h2>
            <p className="success-message">Redirigiendo al dashboard...</p>
          </div>
        </div>
      )}

      {/* Modal de recuperación de contraseña */}
      <ForgotPasswordModal 
        isOpen={showForgotPassword}
        onClose={() => setShowForgotPassword(false)}
      />

      {/* Modal de restablecimiento de contraseña */}
      <ResetPasswordModal 
        isOpen={showResetPassword}
        onClose={() => {
          setShowResetPassword(false);
          setResetToken('');
        }}
        token={resetToken}
      />

      {/* Modal de verificación de cuenta reutilizando estilos del modal de recuperación */}
      <VerificationModal 
        isOpen={showVerificationModal}
        onClose={() => setShowVerificationModal(false)}
        message={verificationMessage || 'Tu cuenta fue verificada correctamente.'}
      />
    </div>
  );
}
