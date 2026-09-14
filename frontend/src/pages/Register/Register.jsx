// components/Register/Register.jsx
import React, { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { API_ENDPOINTS, apiRequest } from "../../config/api.js";
import { useToast } from "../../hooks/useToast.js";
import ToastContainer from "../../components/Toast/ToastContainer.jsx";
import "./Register.css";
import "../Login/Login.css";
import VerificationModal from "../Login/VerificationModal.jsx";
import Stepper, { Step } from "../../components/Stepper/Stepper.jsx";

import logo from "/cNormal.png";
import cromo from "/login.png";

// Reglas de formato de usuario y teléfono (Chile)
const USERNAME_PATTERN = /^[a-z0-9_.-]{3,30}$/i;
const PHONE_PATTERN = /^\+569\d{8}$/;
const PHONE_DIGITS_PATTERN = /^\d{8}$/;
const EMAIL_INVALID_MESSAGE = 'El correo no es válido.';
const EMAIL_VALIDATION_TIMEOUT_MS = 10000;

const normalizeUsername = (value) => (value || '').trim().toLowerCase();
const isValidUsername = (value) => USERNAME_PATTERN.test(normalizeUsername(value));
const normalizeEmail = (value) => (value || '').trim().toLowerCase();

const focusableSelector = [
  'a[href]',
  'area[href]',
  'button:not([disabled])',
  'input:not([disabled]):not([type="hidden"])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',');

const Register = () => {
  const [formData, setFormData] = useState({
    username: "",
    correo: "",
    telefono: "",
    contraseña: "",
    repetirContraseña: "",
    terminos: false,
  });
  const [isTransitioning, setIsTransitioning] = useState(false);
  const [showPasswordValidation, setShowPasswordValidation] = useState(false);
  const [showPhoneValidation, setShowPhoneValidation] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [focusedField, setFocusedField] = useState(null);
  const [fieldErrors, setFieldErrors] = useState({});
  const [attemptedNext, setAttemptedNext] = useState(false);
  const [isEmailValidationPending, setIsEmailValidationPending] = useState(false);
  const emailValidationRequestRef = useRef(0);
  const navigate = useNavigate();

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

  const phoneValidation = useMemo(() => {
    const phone = (formData.telefono || "").trim();
    return {
      format: PHONE_DIGITS_PATTERN.test(phone),
    };
  }, [formData.telefono]);

  const isPhoneValid = phoneValidation.format || formData.telefono.length === 0;


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
  const termsModalRef = useRef(null);
  const termsCloseButtonRef = useRef(null);
  const termsPreviousActiveElementRef = useRef(null);
  const closeTermsModalRef = useRef(null);
  
  // Sistema de notificaciones Toast
  const toast = useToast();

  const handleSubmit = async () => {
    // Validaciones del último paso: si fallan, impedir finalizar devolviendo false
    if (!isPasswordValid) {
      alert('La contraseña no cumple con todos los requisitos');
      return false;
    }

    const normalizedUsername = normalizeUsername(formData.username);
    const telefonoCompleto = `+569${(formData.telefono || '').trim()}`;
    if (!PHONE_PATTERN.test(telefonoCompleto)) {
      alert('El teléfono debe tener 8 dígitos después de +569');
      return false;
    }

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
          telefono: telefonoCompleto,
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
    setIsTransitioning(true);
    setTimeout(() => {
      navigate("/login");
    }, 150);
  };

  const handleTermsClick = (e) => {
    e.preventDefault();
    setShowTermsModal(true);
  };

  const handleCloseTermsModal = () => {
    setShowTermsModal(false);
  };

  closeTermsModalRef.current = handleCloseTermsModal;

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

  useEffect(() => {
    if (!showTermsModal) return undefined;

    const previousActiveElement = document.activeElement;
    termsPreviousActiveElementRef.current = previousActiveElement;

    const modal = termsModalRef.current;
    if (!modal) return undefined;

    const getFocusableElements = () => Array.from(modal.querySelectorAll(focusableSelector));
    const initialFocus = termsCloseButtonRef.current || getFocusableElements()[0] || modal;

    try {
      initialFocus.focus({ preventScroll: true });
    } catch {
      initialFocus.focus();
    }

    const handleTermsKeyDown = (event) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        closeTermsModalRef.current?.();
        return;
      }

      if (event.key !== 'Tab') return;

      const focusableElements = getFocusableElements();
      if (focusableElements.length === 0) {
        event.preventDefault();
        modal.focus();
        return;
      }

      const currentIndex = focusableElements.indexOf(document.activeElement);
      const isLeavingForward = !event.shiftKey && (currentIndex === -1 || currentIndex === focusableElements.length - 1);
      const isLeavingBackward = event.shiftKey && (currentIndex === -1 || currentIndex === 0);

      if (isLeavingForward || isLeavingBackward) {
        event.preventDefault();
        const target = event.shiftKey
          ? focusableElements[focusableElements.length - 1]
          : focusableElements[0];
        target.focus();
      }
    };

    document.addEventListener('keydown', handleTermsKeyDown);

    return () => {
      document.removeEventListener('keydown', handleTermsKeyDown);
      const elementToRestore = termsPreviousActiveElementRef.current;
      if (elementToRestore && document.contains(elementToRestore)) {
        elementToRestore.focus();
      }
    };
  }, [showTermsModal]);

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

      case 2: { // Contacto y seguridad
        if (!formData.telefono.trim()) {
          errors.telefono = 'El teléfono es requerido';
        } else if (!PHONE_DIGITS_PATTERN.test(formData.telefono.trim())) {
          errors.telefono = 'El teléfono debe tener 8 dígitos después de +569';
        }
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
    <div className={`auth register-page register-layout mirror ${isTransitioning ? "page-exit" : "page-enter"}`}>
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
                <h2 style={{ fontSize: '1.5rem', marginBottom: '1.5rem', color: '#333' }}>Información de cuenta</h2>
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

                <p className="login-help" style={{ marginTop: '1.5rem', textAlign: 'center' }}>
                  ¿Ya tienes cuenta? {" "}
                  <a className="login-link" href="#login" onClick={handleLoginClick}>
                    Inicia sesión
                  </a>
                </p>
              </Step>

              {/* PASO 2: Teléfono y seguridad */}
              <Step>
                <h2 style={{ fontSize: '1.3rem', marginBottom: '1rem', color: '#333' }}>Información de Contacto y Seguridad</h2>
                
                <div className="phone-wrapper">
                  <div className={`uv-field phone-prefix-field ${fieldErrors.telefono ? 'uv-field-error' : ''}`}>
                    <span className="uv-icon" aria-hidden="true">
                      <svg viewBox="0 0 24 24" width="20" height="20">
                        <path d="M22 16.92v3a2 2 0 01-2.18 2 19.8 19.8 0 01-8.63-3.07 19.5 19.5 0 01-6-6A19.8 19.8 0 012.1 4.1A2 2 0 014.1 2h3a2 2 0 012 1.72c.07.96.27 1.9.7 2.81a2 2 0 01-.45 2.11L8.1 9.9a16 16 0 006 6l1.27-1.27a2 2 0 012.11-.45c.91.43 1.85.63 2.81.7A2 2 0 0122 16.92z" fill="currentColor" />
                      </svg>
                    </span>
                    <label htmlFor="register-telefono" className="uv-label">Teléfono *</label>
                    <div className="phone-input-group">
                      <span className="phone-prefix">+569 </span>
                      <input
                        className="uv-input"
                        type="tel"
                        id="register-telefono"
                        name="telefono"
                        value={formData.telefono}
                        inputMode="tel"
                        pattern={/^\d{8}$/.source}
                        onChange={(e) => {
                          // Solo los 8 dígitos: el prefijo +569 es fijo y va aparte
                          const rawDigits = e.target.value.replace(/\D/g, '');
                          const digits = rawDigits.startsWith('569')
                            ? rawDigits.slice(3, 11)
                            : rawDigits.slice(0, 8);
                          handleInputChange({ target: { name: 'telefono', value: digits, type: 'tel' } });
                        }}
                        onFocus={() => {
                          setFocusedField('telefono');
                          setShowPhoneValidation(true);
                        }}
                        onBlur={() => {
                          setFocusedField(null);
                          setShowPhoneValidation(false);
                        }}
                        placeholder=" "
                        required
                        aria-invalid={!!fieldErrors.telefono || !isPhoneValid}
                        aria-describedby={[
                          showPhoneValidation && 'phone-hint',
                          fieldErrors.telefono && 'register-telefono-error',
                        ].filter(Boolean).join(' ') || undefined}
                      />
                    </div>
                    <span className="uv-focus-bg" />
                    {fieldErrors.telefono && (
                      <div id="register-telefono-error" className="field-error-message">{fieldErrors.telefono}</div>
                    )}
                  </div>
                  
                  {showPhoneValidation && (
                    <div id="phone-hint" className="phone-validator">
                      <div className="validator-header">
                        <span className="validator-title">Formato:</span>
                      </div>
                      <div className="validator-rules">
                        <div className={`validator-rule ${/^\d{8}$/.test(formData.telefono) ? 'valid' : 'invalid'}`}>
                          <span className="validator-icon">{/^\d{8}$/.test(formData.telefono) ? '✓' : '×'}</span>
                          <span className="validator-text">Ingresa 8 dígitos después de +569</span>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
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
        </div>
      </section>

      <section className="auth-right register-right">
        <img src={cromo} alt="imagen de cromosomas" />
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

      {showTermsModal && (
        <div className="terms-modal-overlay" onClick={handleCloseTermsModal}>
          <div
            ref={termsModalRef}
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
                ref={termsCloseButtonRef}
                className="terms-modal-close"
                onClick={handleCloseTermsModal}
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
                onClick={handleCloseTermsModal}
              >
                Cerrar
              </button>
            </div>
          </div>
        </div>
      )}
      
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