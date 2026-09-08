import React, { useState } from 'react';
import { API_ENDPOINTS, apiRequest, clearToken } from '../../config/api.js';
import { useNavigate } from 'react-router-dom';
import ModalShell from '../../components/ModalShell/ModalShell';

const DeleteAccountModal = ({ isOpen, onClose, userName }) => {
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [confirmText, setConfirmText] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(false);
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    if (!password) {
      setError('Debes ingresar tu contraseña');
      return;
    }

    if (confirmText.toLowerCase() !== 'eliminar') {
      setError('Debes escribir "ELIMINAR" para confirmar');
      return;
    }

    setLoading(true);
    setError('');

    try {
      const result = await apiRequest(API_ENDPOINTS.DELETE_ACCOUNT, {
        method: 'DELETE',
        body: JSON.stringify({
          password: password,
          confirmation: confirmText
        }),
      });

      if (result.ok) {
        setSuccess(true);
        // Esperar 2 segundos, limpiar token y redirigir al login
        setTimeout(() => {
          clearToken();
          navigate('/');
        }, 2000);
      } else {
        setError(result.data.error || result.data.detail || 'Error al eliminar la cuenta');
      }
    } catch (error) {
      console.error('Error de conexión:', error);
      setError('Error de conexión con el servidor.');
    } finally {
      setLoading(false);
    }
  };

  const handleClose = () => {
    if (loading) return; // No permitir cerrar durante la eliminación
    setPassword('');
    setConfirmText('');
    setError('');
    setSuccess(false);
    setShowPassword(false);
    onClose();
  };

  if (!isOpen) return null;

  return (
    <ModalShell
      overlayClass="delete-account-overlay"
      modalClass="delete-account-modal"
      title={success ? 'Cuenta Eliminada' : 'Eliminar Cuenta'}
      onClose={handleClose}
      showClose={!loading}
    >
      {success ? (
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
            Tu cuenta ha sido eliminada. Serás redirigido al inicio en un momento.
          </p>
        </>
      ) : (
        <>
          <div className="warning-banner">
            <svg viewBox="0 0 24 24" width="24" height="24" className="warning-icon">
              <path
                d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
                stroke="currentColor"
                strokeWidth="2"
                fill="none"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
            <div>
              <h3 className="warning-title">Acción Irreversible</h3>
              <p className="warning-text">
                Esta acción eliminará permanentemente tu cuenta y todos tus datos asociados. No podrás recuperar tu información.
              </p>
            </div>
          </div>

          <form onSubmit={handleSubmit} className="delete-account-form">
            {/* Campo de contraseña */}
            <div className="uv-field">
              <span className="uv-icon" aria-hidden="true">
                <svg viewBox="0 0 24 24" width="20" height="20">
                  <path
                    d="M17 10h-1V7a4 4 0 10-8 0v3H7a2 2 0 00-2 2v7a2 2 0 002 2h10a2 2 0 002-2v-7a2 2 0 00-2-2zm-6 0V7a3 3 0 016 0v3h-6z"
                    fill="currentColor"
                  />
                </svg>
              </span>
              <input
                className="uv-input"
                type={showPassword ? "text" : "password"}
                name="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder=" "
                required
                disabled={loading}
              />
              <label className="uv-label">Confirma tu Contraseña</label>
              <span className="uv-focus-bg" />
              <button
                type="button"
                className="pwd-toggle"
                onClick={() => setShowPassword(s => !s)}
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

            {/* Campo de confirmación */}
            <div className="confirmation-field">
              <label className="confirmation-label">
                Escribe <strong>ELIMINAR</strong> para confirmar:
              </label>
              <input
                className="confirmation-input"
                type="text"
                value={confirmText}
                onChange={(e) => setConfirmText(e.target.value)}
                placeholder="ELIMINAR"
                required
                disabled={loading}
              />
            </div>

            {error && (
              <div className="modal-error">
                {error}
              </div>
            )}

            <button
              type="submit"
              className="modal-delete-btn"
              disabled={loading || !password || confirmText.toLowerCase() !== 'eliminar'}
            >
              {loading ? 'Eliminando cuenta...' : 'Eliminar Cuenta Permanentemente'}
            </button>

            <p className="disclaimer-text">
              {userName && `Hola ${userName}, `}
              una vez eliminada tu cuenta, no podrás recuperarla ni acceder a tus datos genéticos.
            </p>
          </form>
        </>
      )}
    </ModalShell>
  );
};

export default DeleteAccountModal;
