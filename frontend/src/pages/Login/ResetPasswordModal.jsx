import React, { useState } from 'react';
import { API_ENDPOINTS, apiRequest } from '../../config/api.js';
import ModalShell from '../../components/ModalShell/ModalShell';
import { usePasswordValidation } from '../../hooks/usePasswordValidation';

const ResetPasswordModal = ({ isOpen, onClose, token }) => {
  const [formData, setFormData] = useState({
    password: '',
    confirmPassword: ''
  });
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [showPasswordValidation, setShowPasswordValidation] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(false);

  const passwordValidation = usePasswordValidation(formData.password);
  const isPasswordValid = Object.values(passwordValidation).every(Boolean);
  const passwordsMatch = formData.password === formData.confirmPassword && formData.confirmPassword !== '';

  const handleInputChange = (e) => {
    const { name, value } = e.target;
    setFormData(prev => ({
      ...prev,
      [name]: value
    }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    if (!isPasswordValid) {
      setError('La contraseña no cumple con todos los requisitos');
      return;
    }
    
    if (!passwordsMatch) {
      setError('Las contraseñas no coinciden');
      return;
    }

    setLoading(true);
    setError('');

    try {
      const result = await apiRequest(API_ENDPOINTS.PASSWORD_RESET_CONFIRM, {
        method: 'POST',
        body: JSON.stringify({
          token: token,
          password: formData.password,
          confirmPassword: formData.confirmPassword
        }),
      });

      if (result.ok) {
        setSuccess(true);
        // Cerrar modal después de 2 segundos y recargar la página
        setTimeout(() => {
          onClose();
          window.location.reload();
        }, 2000);
      } else {
        setError(result.data.error || 'Error al restablecer la contraseña');
      }
    } catch (error) {
      console.error('Error de conexión:', error);
      setError('Error de conexión con el servidor. Verifica que el backend esté ejecutándose.');
    } finally {
      setLoading(false);
    }
  };

  const handleClose = () => {
    setFormData({ password: '', confirmPassword: '' });
    setError('');
    setSuccess(false);
    setShowPassword(false);
    setShowConfirmPassword(false);
    setShowPasswordValidation(false);
    onClose();
  };

  if (!isOpen) return null;

  return (
    <ModalShell
      maxWidth="550px"
      title={success ? '¡Contraseña actualizada!' : 'Nueva Contraseña'}
      onClose={handleClose}
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
            Tu contraseña ha sido actualizada exitosamente. La página se recargará automáticamente.
          </p>
        </>
      ) : (
        <>
          <p className="modal-description">
            Crea una nueva contraseña segura para tu cuenta.
          </p>

          <form onSubmit={handleSubmit} className="forgot-password-form">
            {/* Nueva Contraseña */}
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
                value={formData.password}
                onChange={handleInputChange}
                onFocus={() => setShowPasswordValidation(true)}
                placeholder=" "
                required
                disabled={loading}
              />
              <label className="uv-label">Nueva Contraseña</label>
              <span className="uv-focus-bg" />
              <button
                type="button"
                className="pwd-toggle"
                onClick={() => setShowPassword(s => !s)}
                aria-label={showPassword ? "Ocultar contraseña" : "Mostrar contraseña"}
              >
                {showPassword ? (
                  <svg viewBox="0 0 24 24" width="18" height="18">
                    <path
                      d="M12 5c-5 0-9 4.5-10 7 1 2.5 5 7 10 7s9-4.5 10-7c-1-2.5-5-7-10-7zm0 11a4 4 0 110-8 4 4 0 010 8z"
                      fill="currentColor"
                    />
                  </svg>
                ) : (
                  <svg viewBox="0 0 24 24" width="18" height="18">
                    <path
                      d="M12 5c-5 0-9 4.5-10 7 1 2.5 5 7 10 7s9-4.5 10-7c-1-2.5-5-7-10-7zm0 11a4 4 0 110-8 4 4 0 010 8z"
                      fill="currentColor"
                    />
                    <path d="M4 4l16 16" stroke="currentColor" strokeWidth="2" />
                  </svg>
                )}
              </button>
            </div>

            {/* Validador de contraseña - JUSTO ABAJO DE NUEVA CONTRASEÑA */}
            <div className="password-validator" style={{ display: 'block', visibility: 'visible', opacity: 1, position: 'relative', left: 0, right: 0, width: '100%', marginTop: '12px', marginBottom: '12px' }}>
              <div className={`validator-item ${passwordValidation.minLength ? 'valid' : 'invalid'}`}>
                <span className="validator-icon">
                  {passwordValidation.minLength ? '✓' : '×'}
                </span>
                <span>Mínimo 10 caracteres</span>
              </div>
              <div className={`validator-item ${passwordValidation.hasUppercase ? 'valid' : 'invalid'}`}>
                <span className="validator-icon">
                  {passwordValidation.hasUppercase ? '✓' : '×'}
                </span>
                <span>Una mayúscula</span>
              </div>
              <div className={`validator-item ${passwordValidation.hasNumber ? 'valid' : 'invalid'}`}>
                <span className="validator-icon">
                  {passwordValidation.hasNumber ? '✓' : '×'}
                </span>
                <span>Un número</span>
              </div>
              <div className={`validator-item ${passwordValidation.hasSymbol ? 'valid' : 'invalid'}`}>
                <span className="validator-icon">
                  {passwordValidation.hasSymbol ? '✓' : '×'}
                </span>
                <span>Un símbolo especial</span>
              </div>
            </div>

            {/* Confirmar Contraseña */}
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
                type={showConfirmPassword ? "text" : "password"}
                name="confirmPassword"
                value={formData.confirmPassword}
                onChange={handleInputChange}
                placeholder=" "
                required
                disabled={loading}
              />
              <label className="uv-label">Confirmar Contraseña</label>
              <span className="uv-focus-bg" />
              <button
                type="button"
                className="pwd-toggle"
                onClick={() => setShowConfirmPassword(s => !s)}
                aria-label={showConfirmPassword ? "Ocultar contraseña" : "Mostrar contraseña"}
              >
                {showConfirmPassword ? (
                  <svg viewBox="0 0 24 24" width="18" height="18">
                    <path
                      d="M12 5c-5 0-9 4.5-10 7 1 2.5 5 7 10 7s9-4.5 10-7c-1-2.5-5-7-10-7zm0 11a4 4 0 110-8 4 4 0 010 8z"
                      fill="currentColor"
                    />
                  </svg>
                ) : (
                  <svg viewBox="0 0 24 24" width="18" height="18">
                    <path
                      d="M12 5c-5 0-9 4.5-10 7 1 2.5 5 7 10 7s9-4.5 10-7c-1-2.5-5-7-10-7zm0 11a4 4 0 110-8 4 4 0 010 8z"
                      fill="currentColor"
                    />
                    <path d="M4 4l16 16" stroke="currentColor" strokeWidth="2" />
                  </svg>
                )}
              </button>
            </div>

            {/* Indicador de contraseñas coincidentes */}
            {formData.confirmPassword && (
              <div className={`password-match ${passwordsMatch ? 'valid' : 'invalid'}`}>
                <span className="validator-icon">
                  {passwordsMatch ? '✓' : '×'}
                </span>
                <span>{passwordsMatch ? 'Las contraseñas coinciden' : 'Las contraseñas no coinciden'}</span>
              </div>
            )}

            {error && (
              <div className="modal-error">
                {error}
              </div>
            )}

            <button
              type="submit"
              className="modal-submit-btn"
              disabled={loading || !isPasswordValid || !passwordsMatch}
            >
              {loading ? 'Actualizando...' : 'Actualizar Contraseña'}
            </button>
          </form>
        </>
      )}
    </ModalShell>
  );
};

export default ResetPasswordModal;
