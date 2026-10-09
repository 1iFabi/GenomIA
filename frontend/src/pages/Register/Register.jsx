// components/Register/Register.jsx
import React, { useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import gsap from "gsap";
import { useGSAP } from "@gsap/react";
import { API_ENDPOINTS, apiRequest } from "../../config/api.js";
import { useToast } from "../../hooks/useToast.js";
import ToastContainer from "../../components/Toast/ToastContainer.jsx";
import {
  openAuthPanel,
  playAuthPageEntrance,
  playAuthPlateEntry,
  readAuthPanelSwap,
} from "../../lib/authPanelSwap";
import AuthPlate from "../../components/AuthPlate/AuthPlate.jsx";
import "./Register.css";
import "../Login/Login.css";
import VerificationModal from "../Login/VerificationModal.jsx";
import Stepper, { Step } from "../../components/Stepper/Stepper.jsx";
import GoogleAuthButton, { AuthDivider } from "../../components/GoogleAuthButton/GoogleAuthButton.jsx";
import TermsModal from "../../components/TermsModal/TermsModal.jsx";

import logo from "/cNormal.png";

gsap.registerPlugin(useGSAP);

// Reglas de formato de usuario. El teléfono y el RUT se piden recién al iniciar la compra.
const USERNAME_PATTERN = /^[a-z0-9_.-]{3,30}$/i;
const EMAIL_INVALID_MESSAGE = 'El correo no es válido.';
const EMAIL_VALIDATION_TIMEOUT_MS = 10000;

const normalizeUsername = (value) => (value || '').trim().toLowerCase();
const isValidUsername = (value) => USERNAME_PATTERN.test(normalizeUsername(value));
const normalizeEmail = (value) => (value || '').trim().toLowerCase();

const Register = () => {
  const [formData, setFormData] = useState({
    username: "",
    correo: "",
    contraseña: "",
    repetirContraseña: "",
    terminos: false,
  });
  const [showPasswordValidation, setShowPasswordValidation] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [focusedField, setFocusedField] = useState(null);
  const [fieldErrors, setFieldErrors] = useState({});
  const [attemptedNext, setAttemptedNext] = useState(false);
  const [isEmailValidationPending, setIsEmailValidationPending] = useState(false);
  const emailValidationRequestRef = useRef(0);
  const navigate = useNavigate();
  const authRef = useRef(null);
  // Read, never consumed: a replayed render must see the same handoff it settled into.
  const handoff = readAuthPanelSwap("/register");

  useGSAP(() => {
    if (handoff) {
      playAuthPlateEntry(authRef.current, {
        focusTarget: handoff.keyboard ? authRef.current.querySelector("#register-username") : null,
      });
      return;
    }
    playAuthPageEntrance(authRef.current);
  }, { scope: authRef });

  const passwordValidation = useMemo(() => {
    const password = formData.contraseña;
    return {
      minLength: password.length >= 10,
      hasUppercase: /[A-Z]/.test(password),
      hasNumber: /[0-9]/.test(password),
      hasSymbol: /[!@#$%^&*(),.?":{}|<>]/.test(password),
    };
  }, [formData.contraseña]);

  const isPasswordValid = Object.values(passwordValidation).every(Boolean);
  const passwordsMatch = formData.contraseña === formData.repetirContraseña && formData.repetirContraseña !== '';


  const handleInputChange = (e) => {
    const { name, value, type, checked } = e.target;
    setFormData((prev) => ({
      ...prev,
      [name]: type === "checkbox" ? checked : value,
    }));

    if (name === 'correo') {
      emailValidationRequestRef.current += 1;
      setIsEmailValidationPending(false);
    }

    if (name === 'correo' || name === 'username') {
      setFieldErrors((previous) => {
        const next = { ...previous };
        delete next[name];
        return next;
      });
    }
  };

  const [isLoading, setIsLoading] = useState(false);
  const [registrationSuccess, setRegistrationSuccess] = useState(false);
  const [showSuccessModal, setShowSuccessModal] = useState(false);
  const [showTermsModal, setShowTermsModal] = useState(false);
  const [showVerificationModal, setShowVerificationModal] = useState(false);
  const [verificationMessage, setVerificationMessage] = useState('');
  
  // Sistema de notificaciones Toast
  const toast = useToast();

  const handleSubmit = async () => {
    // Validaciones del último paso: si fallan, impedir finalizar devolviendo false
    if (!isPasswordValid) {
      alert('La contraseña no cumple con todos los requisitos');
      return false;
    }

    const normalizedUsername = normalizeUsername(formData.username);

    if (!passwordsMatch) {
      alert('Las contraseñas no coinciden');
      return false;
    }
    
    if (!formData.terminos) {
      alert('Debes aceptar los términos y condiciones');
      return false;
    }

    const normalizedEmail = normalizeEmail(formData.correo);
    // No necesitamos limpiar errores porque los toasts se autogestionan
    setIsLoading(true);
    
    try {
      const result = await apiRequest(API_ENDPOINTS.REGISTER, {
        method: 'POST',
        body: JSON.stringify({
          username: normalizedUsername,
          correo: normalizedEmail,
          contraseña: formData.contraseña,
          repetirContraseña: formData.repetirContraseña,
          terminos: formData.terminos,
        }),
      });
      
      if (result.ok && result.data.success) {
        const requiresVerification = !!result.data.requires_verification;
        const mensaje = result.data.mensaje || 'Usuario registrado exitosamente.';
        if (requiresVerification) {
          setVerificationMessage(mensaje);
          setShowVerificationModal(true);
        } else {
          setRegistrationSuccess(true);
          setShowSuccessModal(true);
          setTimeout(() => {
            navigate('/login');
          }, 2000);
        }
        // Permitir finalizar el stepper
        return true;
      } else {
        const errorMessage = result.data.error || 'Error en el registro';
        
        // Detectar si el correo ya existe y mostrar toast con acción, sin finalizar el stepper
        if (result.data.email_exists) {
          toast.error(errorMessage, {
            duration: 7000,
            action: {
              label: '¿Olvidaste tu contraseña?',
              onClick: () => {
                navigate('/login?forgot=true');
              }
            }
          });
          return false;
        } else if (result.data.username_exists) {
          toast.error(errorMessage, {
            duration: 7000
          });
          return false;
        } else {
          // Otros errores sin acción
          toast.error(errorMessage);
          return false;
        }
      }
    } catch (error) {
      console.error('Error de conexión:', error);
      toast.error('Error de conexión con el servidor. Verifica tu conexión a internet.');
      return false;
    } finally {
      setIsLoading(false);
    }
  };

  const handleLoginClick = (e) => {
    e.preventDefault();
    openAuthPanel({
      root: authRef.current,
      targetPath: '/login',
      keyboard: e.detail === 0,
      navigate,
    });
  };

  const handleTermsClick = (e) => {
    e.preventDefault();
    setShowTermsModal(true);
  };

  const handleCloseTermsModal = () => {
    setShowTermsModal(false);
  };

  const handlePasswordFocus = () => {
    setShowPasswordValidation(true);
  };

  const handlePasswordBlur = () => {
    setTimeout(() => {
      if (formData.contraseña.length === 0 || isPasswordValid) {
        setShowPasswordValidation(false);
      }
    }, 150);
  };

  // Funciones de validación para cada paso
  const validateStep = async (stepNumber) => {
    setAttemptedNext(true);
    const errors = {};

    switch(stepNumber) {
      case 1: { // Información de cuenta
        const normalizedUsername = normalizeUsername(formData.username);
        const normalizedEmail = normalizeEmail(formData.correo);

        if (!normalizedUsername) {
          errors.username = 'El nombre de usuario es requerido';
        } else if (!isValidUsername(normalizedUsername)) {
          errors.username = 'Usa 3-30 caracteres: letras, números, _, - o .';
        }
        if (!normalizedEmail) {
          errors.correo = EMAIL_INVALID_MESSAGE;
        } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(normalizedEmail)) {
          errors.correo = EMAIL_INVALID_MESSAGE;
        }
        break;
      }

      case 2: { // Seguridad
        if (!formData.contraseña) {
          errors.contraseña = 'La contraseña es requerida';
        } else if (!isPasswordValid) {
          errors.contraseña = 'La contraseña no cumple con los requisitos';
        }
        if (!formData.repetirContraseña) {
          errors.repetirContraseña = 'Debe repetir la contraseña';
        } else if (!passwordsMatch) {
          errors.repetirContraseña = 'Las contraseñas no coinciden';
        }
        if (!formData.terminos) {
          errors.terminos = 'Debe aceptar los términos y condiciones';
        }
        break;
      }
    }

    setFieldErrors(errors);
    if (Object.keys(errors).length > 0 || stepNumber !== 1) {
      return Object.keys(errors).length === 0;
    }

    const normalizedUsername = normalizeUsername(formData.username);
    const normalizedEmail = normalizeEmail(formData.correo);
    setFormData((previous) => ({
      ...previous,
      username: normalizedUsername,
      correo: normalizedEmail,
    }));

    const requestId = emailValidationRequestRef.current + 1;
    emailValidationRequestRef.current = requestId;
    setIsEmailValidationPending(true);
    const emailValidationController = new AbortController();
    const timeoutId = setTimeout(
      () => emailValidationController.abort(),
      EMAIL_VALIDATION_TIMEOUT_MS,
    );

    try {
      const result = await apiRequest(API_ENDPOINTS.REGISTER_EMAIL_VALIDATION, {
        method: 'POST',
        body: JSON.stringify({ email: normalizedEmail }),
        signal: emailValidationController.signal,
      });

      if (requestId !== emailValidationRequestRef.current) return false;
      if (!result.ok || result.data?.valid !== true || typeof result.data.normalized_email !== 'string') {
        setFieldErrors({ correo: EMAIL_INVALID_MESSAGE });
        return false;
      }

      setFormData((previous) => ({ ...previous, correo: result.data.normalized_email }));
      setFieldErrors({});
      return true;
    } catch {
      if (requestId === emailValidationRequestRef.current) {
        setFieldErrors({ correo: EMAIL_INVALID_MESSAGE });
      }
      return false;
    } finally {
      clearTimeout(timeoutId);
      if (requestId === emailValidationRequestRef.current) {
        setIsEmailValidationPending(false);
      }
    }
  };

  React.useEffect(() => {
    const handleClickOutside = (event) => {
      if (showPasswordValidation && 
          !event.target.closest('.password-field-container') &&
          !event.target.closest('.password-validator')) {
        setShowPasswordValidation(false);
      }
    };

    if (showPasswordValidation) {
      document.addEventListener('mousedown', handleClickOutside);
      return () => document.removeEventListener('mousedown', handleClickOutside);
    }
  }, [showPasswordValidation]);

  return (
    <div ref={authRef} className="auth register-page register-layout mirror">
      <section className="auth-left register-left">
        <div className="left-inner register-inner">
          <div className="logo-container">
            <button
              type="button"
              onClick={() => navigate('/')}
              style={{ background: 'none', border: 'none', padding: 0, cursor: 'pointer' }}
            >
              <img
                src={logo}
                alt="Logo"
                className="welcome-logo"
                draggable="false"
              />
            </button>
          </div>

          <h1 className="title register-title">Crea tu cuenta</h1>
          <p className="subtitle register-subtitle">Regístrate para acceder a tu perfil genético.</p>
          <div className="title-underline" />

          <form
            className="login-form login-card register-form form-container"
            onSubmit={(e) => e.preventDefault()}
          >
            <Stepper
              initialStep={1}
              aria-busy={isLoading || isEmailValidationPending}
              isSubmitting={isLoading}
              isNextDisabled={isEmailValidationPending}
              onStepChange={(step) => {
                if (step) setAttemptedNext(false);
                setFieldErrors({}); // Limpiar errores al cambiar de paso
              }}
              onFinalStepCompleted={handleSubmit}
              validateStep={validateStep}
              disableStepIndicators={true}
              backButtonText="Anterior"
              nextButtonText="Siguiente"
            >
              {/* PASO 1: Nombre de usuario y correo */}
              <Step>
                <h2 className="register-step-title">Información de cuenta</h2>
                <div className="account-row">
                  <div className={`account-field uv-field ${fieldErrors.username ? 'uv-field-error' : ''}`}>
                    <span className="uv-icon" aria-hidden="true">
                      <svg viewBox="0 0 24 24" width="20" height="20">
                        <path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2M12 11a4 4 0 100-8 4 4 0 000 8z" fill="currentColor" />
                      </svg>
                    </span>
                    <label htmlFor="register-username" className="uv-label">Nombre de usuario *</label>
                    <input
                      className="uv-input"
                      type="text"
                      id="register-username"
                      name="username"
                      value={formData.username}
                      onChange={handleInputChange}
                      onFocus={() => setFocusedField('username')}
                      onBlur={() => {
                        setFocusedField(null);
                        setFormData((previous) => ({ ...previous, username: normalizeUsername(previous.username) }));
                      }}
                      required
                      minLength={3}
                      maxLength={30}
                      pattern="[A-Za-z0-9_.-]{3,30}"
                      autoComplete="username"
                      aria-invalid={!!fieldErrors.username || (attemptedNext && !isValidUsername(formData.username))}
                      aria-describedby={fieldErrors.username ? 'register-username-error' : undefined}
                    />
                    <span className="uv-focus-bg" />
                    {focusedField === 'username' && !formData.username && (
                      <div className="input-hint">3-30 caracteres: letras, números, _, - o .</div>
                    )}
                    {fieldErrors.username && (
                      <div id="register-username-error" className="field-error-message">{fieldErrors.username}</div>
                    )}
                  </div>

                  <div className={`account-field uv-field ${fieldErrors.correo ? 'uv-field-error' : ''}`}>
                    <span className="uv-icon" aria-hidden="true">
                      <svg viewBox="0 0 24 24" width="20" height="20">
                        <path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2M12 11a4 4 0 100-8 4 4 0 000 8z" fill="currentColor" />
                      </svg>
                    </span>
                    <label htmlFor="register-correo" className="uv-label">Correo *</label>
                    <input
                      className="uv-input"
                      type="email"
                      id="register-correo"
                      name="correo"
                      value={formData.correo}
                      onChange={handleInputChange}
                      onFocus={() => setFocusedField('correo')}
                      onBlur={() => setFocusedField(null)}
                      required
                      autoComplete="email"
                      aria-invalid={!!fieldErrors.correo || (attemptedNext && !normalizeEmail(formData.correo))}
                      aria-describedby={fieldErrors.correo ? 'register-correo-error' : undefined}
                    />
                    <span className="uv-focus-bg" />
                    {focusedField === 'correo' && !formData.correo && (
                      <div className="input-hint">ejemplo@correo.com</div>
                    )}
                    {fieldErrors.correo && (
                      <div id="register-correo-error" className="field-error-message">{fieldErrors.correo}</div>
                    )}
                  </div>
                </div>

                <div className="step-spacer"></div>

                <p className="login-help register-login-help">
                  ¿Ya tienes cuenta? {" "}
                  <a className="login-link" href="#login" onClick={handleLoginClick}>
                    Inicia sesión
                  </a>
                </p>
              </Step>

              {/* PASO 2: Seguridad */}
              <Step>
                <h2 className="register-step-title register-step-title--compact">Seguridad</h2>

                <div className="password-wrapper" style={{ marginBottom: '1rem' }}>
                  <div className={`uv-field password-field-container security-field ${fieldErrors.contraseña ? 'uv-field-error' : ''}`}>
                    <span className="uv-icon" aria-hidden="true">
                      <svg viewBox="0 0 24 24" width="20" height="20">
                        <path d="M17 10h-1V7a4 4 0 10-8 0v3H7a2 2 0 00-2 2v7a2 2 0 002 2h10a2 2 0 002-2v-7a2 2 0 00-2-2zm-6 0V7a3 3 0 616 0v3h-6z" fill="currentColor" />
                      </svg>
                    </span>
                    <label htmlFor="register-password" className="uv-label">Contraseña *</label>
                    <div className="security-input-row">
                      <input
                        className="uv-input"
                        type={showPassword ? "text" : "password"}
                        id="register-password"
                        aria-invalid={!!fieldErrors.contraseña}
                        aria-describedby={fieldErrors.contraseña ? 'register-password-error' : undefined}
                        name="contraseña"
                        value={formData.contraseña}
                        onChange={handleInputChange}
                        onFocus={handlePasswordFocus}
                        onBlur={handlePasswordBlur}
                        placeholder=" "
                        required
                      />
                      <span className="uv-focus-bg" />
                      <button
                        type="button"
                        className="pwd-toggle"
                        onClick={() => setShowPassword(prev => !prev)}
                        aria-label={showPassword ? "Ocultar contraseña" : "Mostrar contraseña"}
                      >
                      {showPassword ? (
                        <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2">
                          <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                          <circle cx="12" cy="12" r="3"/>
                        </svg>
                      ) : (
                        <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2">
                          <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/>
                          <line x1="1" y1="1" x2="23" y2="23"/>
                        </svg>
                      )}
                      </button>
                    </div>
                    {fieldErrors.contraseña && (
                      <div id="register-password-error" className="field-error-message">{fieldErrors.contraseña}</div>
                    )}
                  </div>
                  
                  {(showPasswordValidation || formData.contraseña.length > 0) && (
                    <div className="password-validator password-validator-responsive">
                      <div className="validator-header">
                        <span className="validator-title">Requisitos:</span>
                      </div>
                      <div className="validator-rules">
                        <div className={`validator-rule ${passwordValidation.minLength ? 'valid' : 'invalid'}`}>
                          <span className="validator-icon">{passwordValidation.minLength ? '✓' : '×'}</span>
                          <span className="validator-text">Mínimo 10 caracteres</span>
                        </div>
                        <div className={`validator-rule ${passwordValidation.hasUppercase ? 'valid' : 'invalid'}`}>
                          <span className="validator-icon">{passwordValidation.hasUppercase ? '✓' : '×'}</span>
                          <span className="validator-text">1 letra mayúscula</span>
                        </div>
                        <div className={`validator-rule ${passwordValidation.hasNumber ? 'valid' : 'invalid'}`}>
                          <span className="validator-icon">{passwordValidation.hasNumber ? '✓' : '×'}</span>
                          <span className="validator-text">1 número</span>
                        </div>
                        <div className={`validator-rule ${passwordValidation.hasSymbol ? 'valid' : 'invalid'}`}>
                          <span className="validator-icon">{passwordValidation.hasSymbol ? '✓' : '×'}</span>
                          <span className="validator-text">1 símbolo (!@#$%^&*)</span>
                        </div>
                      </div>
                    </div>
                  )}
                </div>

                <div className={`uv-field password-field-container security-field ${fieldErrors.repetirContraseña ? 'uv-field-error' : ''}`}>
                  <span className="uv-icon" aria-hidden="true">
                    <svg viewBox="0 0 24 24" width="20" height="20">
                      <path d="M17 10h-1V7a4 4 0 10-8 0v3H7a2 2 0 00-2 2v7a2 2 0 002 2h10a2 2 0 002-2v-7a2 2 0 00-2-2zm-6 0V7a3 3 0 616 0v3h-6z" fill="currentColor" />
                    </svg>
                  </span>
                  <label htmlFor="register-confirm-password" className="uv-label">Repetir contraseña *</label>
                  <div className="security-input-row">
                    <input
                      className={`uv-input ${formData.repetirContraseña && !passwordsMatch ? 'input-error' : ''}`}
                      type={showConfirmPassword ? "text" : "password"}
                      id="register-confirm-password"
                      aria-invalid={Boolean(fieldErrors.repetirContraseña || (formData.repetirContraseña && !passwordsMatch))}
                      aria-describedby={[
                        formData.repetirContraseña && !passwordsMatch && 'register-confirm-password-mismatch',
                        fieldErrors.repetirContraseña && 'register-confirm-password-error',
                      ].filter(Boolean).join(' ') || undefined}
                      name="repetirContraseña"
                      value={formData.repetirContraseña}
                      onChange={handleInputChange}
                      placeholder=" "
                      required
                    />
                    <span className="uv-focus-bg" />
                    <button
                      type="button"
                      className="pwd-toggle"
                      onClick={() => setShowConfirmPassword(prev => !prev)}
                      aria-label={showConfirmPassword ? "Ocultar contraseña" : "Mostrar contraseña"}
                    >
                    {showConfirmPassword ? (
                      <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                        <circle cx="12" cy="12" r="3"/>
                      </svg>
                    ) : (
                      <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/>
                        <line x1="1" y1="1" x2="23" y2="23"/>
                      </svg>
                    )}
                    </button>
                  </div>
                  
                  {formData.repetirContraseña && !passwordsMatch && (
                    <div id="register-confirm-password-mismatch" className="password-error">Las contraseñas no coinciden</div>
                  )}
                  {fieldErrors.repetirContraseña && (
                    <div id="register-confirm-password-error" className="field-error-message">{fieldErrors.repetirContraseña}</div>
                  )}
                </div>

                <label className={`checkbox-line ${fieldErrors.terminos ? 'checkbox-error' : ''}`} style={{ marginTop: '1rem' }}>
                  <input
                    type="checkbox"
                    id="register-terminos"
                    aria-invalid={!!fieldErrors.terminos}
                    aria-describedby={fieldErrors.terminos ? 'register-terminos-error' : undefined}
                    name="terminos"
                    checked={formData.terminos}
                    onChange={handleInputChange}
                    required
                  />
                  <span>
                    Acepto los{" "}
                    <a 
                      href="#" 
                      onClick={handleTermsClick}
                      className="terms-link"
                      style={{
                        color: "#007bff",
                        textDecoration: "underline",
                        cursor: "pointer"
                      }}
                    >
                      términos y condiciones
                    </a> *
                  </span>
                </label>
                {fieldErrors.terminos && (
                  <div id="register-terminos-error" className="field-error-message" style={{ marginTop: '6px' }}>{fieldErrors.terminos}</div>
                )}
                
                <div className="step-spacer"></div>
              </Step>
            </Stepper>
          </form>

          <div className="register-social">
            <AuthDivider>O regístrate con</AuthDivider>
            <GoogleAuthButton text="signup_with" intent="signup" />
          </div>
        </div>
      </section>

      <section className="auth-right register-right">
        <AuthPlate />
      </section>

      {/* Toast Container para notificaciones */}
      <ToastContainer toasts={toast.toasts} removeToast={toast.removeToast} />

      <VerificationModal
        isOpen={showVerificationModal}
        onClose={() => {
          setShowVerificationModal(false);
          navigate('/login');
        }}
        message={verificationMessage || 'Usuario registrado exitosamente. Debes verificar tu cuenta desde tu correo para poder continuar.'}
        title="Verificación requerida"
      />

      {showTermsModal && <TermsModal onClose={handleCloseTermsModal} />}
      
      {showSuccessModal && registrationSuccess && (
        <div
          className="success-modal-overlay"
          role="status"
          aria-live="polite"
          aria-atomic="true"
        >
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
            <h2 className="success-title">Registro exitoso</h2>
            <p className="success-message">Redirigiendo al login...</p>
          </div>
        </div>
      )}
    </div>
  );
};

export default Register;