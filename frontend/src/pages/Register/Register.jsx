// components/Register/Register.jsx
import React, { useState, useMemo } from "react";
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

// Reglas de formato RUT / teléfono (Chile)
const RUT_INPUT_PATTERN = /^\d{1,2}(?:\.\d{3}){1,2}-[0-9Kk]$/;
const RUT_VALID_PATTERN = /^\d{7,8}-[0-9Kk]$/; // sin puntos: mismo criterio que el backend
const PHONE_PATTERN = /^\+569\d{8}$/;
const PHONE_DIGITS_PATTERN = /^\d{8}$/;

/**
 * Formatea el RUT insertando puntos automáticamente, agrupando de 3 en 3 desde la derecha.
 * El guión lo escribe el usuario manualmente. El dígito verificador queda como último carácter.
 * Ej: "12345678-9" → "12.345.678-9" | "1234567-K" → "1.234.567-K"
 */
const formatRut = (raw) => {
  const value = raw.toUpperCase();
  const hyphenIndex = value.indexOf('-');
  const hasHyphen = hyphenIndex !== -1;

  // Cuerpo (dígitos antes del guión) y dígito verificador (después del guión)
  const bodyRaw = hasHyphen ? value.slice(0, hyphenIndex) : value;
  const dv = hasHyphen ? value.slice(hyphenIndex + 1) : '';

  // Solo dígitos en el cuerpo, máximo 8
  const bodyDigits = bodyRaw.replace(/\D/g, '').slice(0, 8);

  // Agrupar de 3 en 3 desde la derecha: 12345678 → 12.345.678
  const formattedBody = bodyDigits.replace(/\B(?=(\d{3})+(?!\d))/g, '.');

  // Dígito verificador: un único carácter 0-9 o K
  const cleanDv = dv.replace(/[^0-9K]/g, '').slice(0, 1);

  return hasHyphen ? `${formattedBody}-${cleanDv}` : formattedBody;
};

// Valida el RUT ignorando los puntos visuales (mismo criterio que el backend: 7-8 dígitos + DV)
const isValidRut = (rut) => RUT_VALID_PATTERN.test(rut.replace(/\./g, ''));


const Register = () => {
  const [formData, setFormData] = useState({
    nombre: "",
    apellido: "",
    contraseña: "",
    repetirContraseña: "",
    correo: "",
    rut: "",
    telefono: "",
    terminos: false,
  });
  const [isTransitioning, setIsTransitioning] = useState(false);
  const [showPasswordValidation, setShowPasswordValidation] = useState(false);
  const [showPhoneValidation, setShowPhoneValidation] = useState(false);
  const [showRutValidation, setShowRutValidation] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [focusedField, setFocusedField] = useState(null);
  const [fieldErrors, setFieldErrors] = useState({});
  const [attemptedNext, setAttemptedNext] = useState(false);
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

  const rutValidation = useMemo(() => {
    const rut = (formData.rut || "").trim();
    return {
      format: isValidRut(rut),
    };
  }, [formData.rut]);

  const isRutValid = rutValidation.format || formData.rut.length === 0;

  const handleInputChange = (e) => {
    const { name, value, type, checked } = e.target;
    setFormData((prev) => ({
      ...prev,
      [name]: type === "checkbox" ? checked : value,
    }));
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

    const telefonoCompleto = `+569${(formData.telefono || '').trim()}`;
    if (!PHONE_PATTERN.test(telefonoCompleto)) {
      alert('El teléfono debe tener 8 dígitos después de +569');
      return false;
    }

    if (!isValidRut((formData.rut || '').trim())) {
      alert('El RUT debe tener formato 12.345.678-9 (7-8 dígitos, guión y dígito verificador 0-9 o K)');
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
    
    // No necesitamos limpiar errores porque los toasts se autogestionan
    
    try {
      const result = await apiRequest(API_ENDPOINTS.REGISTER, {
        method: 'POST',
        body: JSON.stringify({
          nombre: formData.nombre,
          apellido: formData.apellido,
          correo: formData.correo,
          rut: formData.rut.replace(/\./g, '').toUpperCase(),
          telefono: telefonoCompleto,
          contraseña: formData.contraseña,
          repetirContraseña: formData.repetirContraseña,
          terminos: formData.terminos
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
        } else if (result.data.rut_exists) {
          // Si el RUT ya existe, mostrar error
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
  const validateStep = (stepNumber) => {
    const errors = {};
    
    switch(stepNumber) {
      case 1: // Información Personal
        if (!formData.nombre.trim()) {
          errors.nombre = 'El nombre es requerido';
        }
        if (!formData.apellido.trim()) {
          errors.apellido = 'El apellido es requerido';
        }
        break;
        
      case 2: // Información de Contacto
        if (!formData.correo.trim()) {
          errors.correo = 'El correo es requerido';
        } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(formData.correo)) {
          errors.correo = 'El correo no es válido';
        }
        if (!formData.rut.trim()) {
          errors.rut = 'El RUT es requerido';
        } else if (!isValidRut(formData.rut)) {
          errors.rut = 'El formato debe ser 12.345.678-9';
        }
        if (!formData.telefono.trim()) {
          errors.telefono = 'El teléfono es requerido';
        } else if (!/^\d{8}$/.test(formData.telefono)) {
          errors.telefono = 'El teléfono debe tener 8 dígitos después de +569';
        }
        break;
        
      case 3: // Seguridad
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
    
    setFieldErrors(errors);
    return Object.keys(errors).length === 0;
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

          <div className="login-form login-card register-form form-container">
            <Stepper
              initialStep={1}
              onStepChange={(step) => {
                setFieldErrors({}); // Limpiar errores al cambiar de paso
              }}
              onFinalStepCompleted={handleSubmit}
              validateStep={validateStep}
              disableStepIndicators={true}
              backButtonText="Anterior"
              nextButtonText="Siguiente"
            >
              {/* PASO 1: Nombre y Apellido */}
              <Step>
                <h2 style={{ fontSize: '1.5rem', marginBottom: '1.5rem', color: '#333' }}>Información Personal</h2>
                <div className="form-row">
                  <div className={`uv-field ${fieldErrors.nombre ? 'uv-field-error' : ''}`}>
                    <span className="uv-icon" aria-hidden="true">
                      <svg viewBox="0 0 24 24" width="20" height="20">
                        <path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2M12 11a4 4 0 100-8 4 4 0 000 8z" fill="currentColor" />
                      </svg>
                    </span>
                    <input
                      className="uv-input"
                      type="text"
                      name="nombre"
                      value={formData.nombre}
                      onChange={handleInputChange}
                      onFocus={() => setFocusedField('nombre')}
                      onBlur={() => setFocusedField(null)}
                      placeholder=" "
                      required
                      autoComplete="given-name"
                    />
                    <label className="uv-label">Nombre *</label>
                    <span className="uv-focus-bg" />
                    {focusedField === 'nombre' && !formData.nombre && (
                      <div className="input-hint">Ej: María</div>
                    )}
                    {fieldErrors.nombre && (
                      <div className="field-error-message">{fieldErrors.nombre}</div>
                    )}
                  </div>

                  <div className={`uv-field ${fieldErrors.apellido ? 'uv-field-error' : ''}`}>
                    <span className="uv-icon" aria-hidden="true">
                      <svg viewBox="0 0 24 24" width="20" height="20">
                        <path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2M12 11a4 4 0 100-8 4 4 0 000 8z" fill="currentColor" />
                      </svg>
                    </span>
                    <input
                      className="uv-input"
                      type="text"
                      name="apellido"
                      value={formData.apellido}
                      onChange={handleInputChange}
                      onFocus={() => setFocusedField('apellido')}
                      onBlur={() => setFocusedField(null)}
                      placeholder=" "
                      required
                      autoComplete="family-name"
                    />
                    <label className="uv-label">Apellido *</label>
                    <span className="uv-focus-bg" />
                    {focusedField === 'apellido' && !formData.apellido && (
                      <div className="input-hint">Ej: González</div>
                    )}
                    {fieldErrors.apellido && (
                      <div className="field-error-message">{fieldErrors.apellido}</div>
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

              {/* PASO 2: Correo, RUT y Teléfono */}
              <Step>
                <h2 style={{ fontSize: '1.5rem', marginBottom: '1.5rem', color: '#333' }}>Información de Contacto</h2>
                
                <div className={`uv-field ${fieldErrors.correo ? 'uv-field-error' : ''}`} style={{ marginBottom: '1.5rem' }}>
                  <span className="uv-icon" aria-hidden="true">
                    <svg viewBox="0 0 24 24" width="20" height="20">
                      <path d="M20 8l-8 5-8-5V6l8 5 8-5v2zm0 3v7H4v-7l8 5 8-5z" fill="currentColor" />
                    </svg>
                  </span>
                  <input
                    className="uv-input"
                    type="email"
                    name="correo"
                    value={formData.correo}
                    onChange={handleInputChange}
                    onFocus={() => setFocusedField('correo')}
                    onBlur={() => setFocusedField(null)}
                    placeholder=" "
                    required
                  />
                  <label className="uv-label">Correo *</label>
                  <span className="uv-focus-bg" />
                  {focusedField === 'correo' && !formData.correo && (
                    <div className="input-hint">ejemplo@correo.com</div>
                  )}
                  {fieldErrors.correo && (
                    <div className="field-error-message">{fieldErrors.correo}</div>
                  )}
                </div>

<div className="rut-wrapper" style={{ marginBottom: '1.5rem' }}>
                  <div className={`uv-field ${fieldErrors.rut ? 'uv-field-error' : ''}`}>
                    <span className="uv-icon" aria-hidden="true">
                      <svg viewBox="0 0 24 24" width="20" height="20">
                        <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8l-6-6z" fill="currentColor" />
                        <path d="M14 2v6h6M16 13H8M16 17H8M10 9H8" stroke="white" strokeWidth="1" fill="none" />
                      </svg>
                    </span>
                    <input
                      className="uv-input"
                      type="text"
                      name="rut"
                      value={formData.rut}
                      inputMode="text"
                      pattern={RUT_INPUT_PATTERN.source}
                      onChange={(e) => {
                        handleInputChange({ target: { name: 'rut', value: formatRut(e.target.value), type: 'text' } });
                      }}
                      onFocus={() => {
                        setFocusedField('rut');
                        setShowRutValidation(true);
                      }}
                      onBlur={() => {
                        setFocusedField(null);
                        setShowRutValidation(false);
                      }}
                      placeholder=" "
                      required
                      aria-describedby="rut-hint"
                    />
                    <label className="uv-label">RUT *</label>
                    <span className="uv-focus-bg" />
                    {focusedField === 'rut' && !formData.rut && (
                      <div className="input-hint">12.345.678-9</div>
                    )}
                    {fieldErrors.rut && (
                      <div className="field-error-message">{fieldErrors.rut}</div>
                    )}
                  </div>
                  
                  {showRutValidation && (
                    <div className="phone-validator">
                      <div className="validator-header">
                        <span className="validator-title">Formato:</span>
                      </div>
                      <div className="validator-rules">
                        <div className={`validator-rule ${isValidRut(formData.rut) ? 'valid' : 'invalid'}`}>
                          <span className="validator-icon">{isValidRut(formData.rut) ? '✓' : '×'}</span>
                          <span className="validator-text">Formato: 12.345.678-9</span>
                        </div>
                      </div>
                    </div>
                  )}
                </div>

<div className="phone-wrapper">
                  <div className={`uv-field phone-prefix-field ${fieldErrors.telefono ? 'uv-field-error' : ''}`}>
                    <span className="uv-icon" aria-hidden="true">
                      <svg viewBox="0 0 24 24" width="20" height="20">
                        <path d="M22 16.92v3a2 2 0 01-2.18 2 19.8 19.8 0 01-8.63-3.07 19.5 19.5 0 01-6-6A19.8 19.8 0 012.1 4.1A2 2 0 014.1 2h3a2 2 0 012 1.72c.07.96.27 1.9.7 2.81a2 2 0 01-.45 2.11L8.1 9.9a16 16 0 006 6l1.27-1.27a2 2 0 012.11-.45c.91.43 1.85.63 2.81.7A2 2 0 0122 16.92z" fill="currentColor" />
                      </svg>
                    </span>
                    <label className="uv-label">Teléfono *</label>
                    <div className="phone-input-group">
                      <span className="phone-prefix">+569 </span>
                      <input
                        className="uv-input"
                        type="tel"
                        name="telefono"
                        value={formData.telefono}
                        inputMode="tel"
                        pattern={/^\d{8}$/.source}
                        onChange={(e) => {
                          // Solo los 8 dígitos: el prefijo +569 es fijo y va aparte
                          const digits = e.target.value.replace(/\D/g, '').slice(0, 8);
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
                        aria-describedby="phone-hint"
                      />
                    </div>
                    <span className="uv-focus-bg" />
                    {fieldErrors.telefono && (
                      <div className="field-error-message">{fieldErrors.telefono}</div>
                    )}
                  </div>
                  
                  {showPhoneValidation && (
                    <div className="phone-validator">
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
              </Step>

              {/* PASO 3: Contraseña y Repetir Contraseña */}
              <Step>
                <h2 style={{ fontSize: '1.3rem', marginBottom: '1rem', color: '#333' }}>Seguridad</h2>
                
                <div className="password-wrapper" style={{ marginBottom: '1rem' }}>
                  <div className={`uv-field password-field-container ${fieldErrors.contraseña ? 'uv-field-error' : ''}`}>
                    <span className="uv-icon" aria-hidden="true">
                      <svg viewBox="0 0 24 24" width="20" height="20">
                        <path d="M17 10h-1V7a4 4 0 10-8 0v3H7a2 2 0 00-2 2v7a2 2 0 002 2h10a2 2 0 002-2v-7a2 2 0 00-2-2zm-6 0V7a3 3 0 616 0v3h-6z" fill="currentColor" />
                      </svg>
                    </span>
                    <input
                      className="uv-input"
                      type={showPassword ? "text" : "password"}
                      name="contraseña"
                      value={formData.contraseña}
                      onChange={handleInputChange}
                      onFocus={handlePasswordFocus}
                      onBlur={handlePasswordBlur}
                      placeholder=" "
                      required
                    />
                    <label className="uv-label">Contraseña *</label>
                    <span className="uv-focus-bg" />
                    
                    <button
                      type="button"
                      className="pwd-toggle"
                      onClick={() => setShowPassword(prev => !prev)}
                      aria-label={showPassword ? "Ocultar contraseña" : "Mostrar contraseña"}
                      tabIndex="-1"
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
                    {fieldErrors.contraseña && (
                      <div className="field-error-message">{fieldErrors.contraseña}</div>
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

                <div className={`uv-field password-field-container ${fieldErrors.repetirContraseña ? 'uv-field-error' : ''}`}>
                  <span className="uv-icon" aria-hidden="true">
                    <svg viewBox="0 0 24 24" width="20" height="20">
                      <path d="M17 10h-1V7a4 4 0 10-8 0v3H7a2 2 0 00-2 2v7a2 2 0 002 2h10a2 2 0 002-2v-7a2 2 0 00-2-2zm-6 0V7a3 3 0 616 0v3h-6z" fill="currentColor" />
                    </svg>
                  </span>
                  <input
                    className={`uv-input ${formData.repetirContraseña && !passwordsMatch ? 'input-error' : ''}`}
                    type={showConfirmPassword ? "text" : "password"}
                    name="repetirContraseña"
                    value={formData.repetirContraseña}
                    onChange={handleInputChange}
                    placeholder=" "
                    required
                  />
                  <label className="uv-label">Repetir contraseña *</label>
                  <span className="uv-focus-bg" />
                  
                  <button
                    type="button"
                    className="pwd-toggle"
                    onClick={() => setShowConfirmPassword(prev => !prev)}
                    aria-label={showConfirmPassword ? "Ocultar contraseña" : "Mostrar contraseña"}
                    tabIndex="-1"
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
                  
                  {formData.repetirContraseña && !passwordsMatch && (
                    <div className="password-error">Las contraseñas no coinciden</div>
                  )}
                  {fieldErrors.repetirContraseña && (
                    <div className="field-error-message">{fieldErrors.repetirContraseña}</div>
                  )}
                </div>

                <label className={`checkbox-line ${fieldErrors.terminos ? 'checkbox-error' : ''}`} style={{ marginTop: '1rem' }}>
                  <input
                    type="checkbox"
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
                  <div className="field-error-message" style={{ marginTop: '6px' }}>{fieldErrors.terminos}</div>
                )}
                
                <div className="step-spacer"></div>
              </Step>
            </Stepper>
          </div>
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
          <div className="terms-modal" onClick={(e) => e.stopPropagation()}>
            <div className="terms-modal-header">
              <h2>Términos y Condiciones de Genomia</h2>
              <button 
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
            <h2 className="success-title">Registro exitoso</h2>
            <p className="success-message">Redirigiendo al login...</p>
          </div>
        </div>
      )}
    </div>
  );
};

export default Register;