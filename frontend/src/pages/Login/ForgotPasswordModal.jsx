import React, { useState } from 'react';
import { API_ENDPOINTS, apiRequest } from '../../config/api.js';
import ModalShell from '../../components/ModalShell/ModalShell';

const ForgotPasswordModal = ({ isOpen, onClose }) => {
  const [email, setEmail] = useState('');
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [step, setStep] = useState('form'); // 'form' | 'success'

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    setMessage('');

    try {
      const result = await apiRequest(API_ENDPOINTS.PASSWORD_RESET, {
        method: 'POST',
        body: JSON.stringify({ email }),
      });

      if (result.ok) {
        setStep('success');
        setMessage(result.data.message);
      } else {
        setError(result.data.error || 'Error al enviar el correo de recuperación');
      }
    } catch (error) {
      console.error('Error de conexión:', error);
      setError('Error de conexión con el servidor. Verifica que el backend esté ejecutándose.');
    } finally {
      setLoading(false);
    }
  };

  const handleClose = () => {
    setEmail('');
    setMessage('');
    setError('');
    setStep('form');
    onClose();
  };

  if (!isOpen) return null;

  return (
    <ModalShell
      title={step === 'form' ? '¿Olvidaste tu contraseña?' : 'Correo enviado'}
      onClose={handleClose}
    >
      {step === 'form' ? (
        <>
          <p className="modal-description">
            Ingresa tu correo electrónico y te enviaremos un enlace para restablecer tu contraseña.
          </p>

          <form onSubmit={handleSubmit} className="forgot-password-form">
            <div className="uv-field">
              <span className="uv-icon" aria-hidden="true">
                <svg viewBox="0 0 24 24" width="20" height="20">
                  <path
                    d="M20 8l-8 5-8-5V6l8 5 8-5v2zm0 3v7H4v-7l8 5 8-5z"
                    fill="currentColor"
                  />
                </svg>
              </span>
              <input
                className="uv-input"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder=" "
                required
                disabled={loading}
              />
              <label className="uv-label">Correo electrónico</label>
              <span className="uv-focus-bg" />
            </div>

            {error && (
              <div className="modal-error">
                {error}
              </div>
            )}

            <button
              type="submit"
              className="modal-submit-btn"
              disabled={loading || !email.trim()}
            >
              {loading ? 'Enviando...' : 'Enviar enlace de recuperación'}
            </button>
          </form>
        </>
      ) : (
        <>
          <div className="success-icon">
            <svg viewBox="0 0 24 24" width="48" height="48">
              <path
                d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
                stroke="currentColor"
                strokeWidth="2"
                fill="none"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </div>

          <p className="success-message">
            {message}
          </p>

          <div className="success-note">
            <strong>Nota:</strong> Revisa tu bandeja de entrada y carpeta de spam.
            El enlace expirará en 24 horas por seguridad.
          </div>

          <button
            className="modal-submit-btn"
            onClick={handleClose}
          >
            Entendido
          </button>
        </>
      )}
    </ModalShell>
  );
};

export default ForgotPasswordModal;
