import React, { useEffect, useId, useRef, useState } from 'react';
import './UploadFileModal.css';
import { getCsrfToken } from '../../config/api';

const focusableSelector = [
  'a[href]',
  'area[href]',
  'button:not([disabled])',
  'input:not([disabled]):not([type="hidden"])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',');

const UploadFileModal = ({ isOpen, onClose }) => {
  const [formData, setFormData] = useState({
    userEmail: '',
    file: null
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(false);
  const [dragActive, setDragActive] = useState(false);
  const modalRef = useRef(null);
  const closeButtonRef = useRef(null);
  const previousActiveElementRef = useRef(null);
  const handleCloseRef = useRef(null);
  const titleId = `upload-modal-title-${useId().replace(/:/g, '')}`;

  const handleInputChange = (e) => {
    const { name, value } = e.target;
    setFormData(prev => ({
      ...prev,
      [name]: value
    }));
  };

  const handleFileChange = (e) => {
    const file = e.target.files[0];
    if (file) {
      // Validar tipo de archivo (ejemplo: solo archivos genéticos)
      const allowedTypes = ['.vcf', '.txt', '.csv', '.zip', '.rar'];
      const fileExtension = '.' + file.name.split('.').pop().toLowerCase();
      
      if (!allowedTypes.includes(fileExtension)) {
        setError(`Tipo de archivo no permitido. Formatos aceptados: ${allowedTypes.join(', ')}`);
        return;
      }

      // Validar tamaño (ejemplo: máximo 100MB)
      const maxSize = 100 * 1024 * 1024; // 100MB
      if (file.size > maxSize) {
        setError('El archivo es demasiado grande. Tamaño máximo: 100MB');
        return;
      }

      setFormData(prev => ({
        ...prev,
        file: file
      }));
      setError('');
    }
  };

  const handleDrag = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);

    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      const file = e.dataTransfer.files[0];
      handleFileChange({ target: { files: [file] } });
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (!formData.userEmail || !formData.file) {
      setError('Por favor completa todos los campos');
      return;
    }

    setLoading(true);
    setError('');

    try {
      // Crear FormData para enviar archivo
      const data = new FormData();
      data.append('file', formData.file);
      data.append('userEmail', formData.userEmail);

      // Usar endpoint de Django para subir archivo
      const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api';
      const uploadUrl = `${API_BASE_URL}/ingest/upload-genetic-file/`;

      const response = await fetch(uploadUrl, {
        method: 'POST',
        credentials: 'include',
        headers: {
          'X-CSRFToken': getCsrfToken(),
        },
        body: data,
      });

      if (response.ok) {
        setSuccess(true);
        setTimeout(() => {
          handleClose();
        }, 2000);
      } else {
        const errorData = await response.json().catch(() => ({}));
        setError(errorData.message || errorData.error || 'Error al subir el archivo');
      }
    } catch (error) {
      console.error('Error de conexión:', error);
      setError('Error de conexión con el servidor.');
    } finally {
      setLoading(false);
    }
  };

  const handleClose = () => {
    setFormData({ userEmail: '', file: null });
    setError('');
    setSuccess(false);
    setDragActive(false);
    onClose();
  };

  handleCloseRef.current = handleClose;

  useEffect(() => {
    if (!isOpen) return undefined;

    const previousActiveElement = document.activeElement;
    previousActiveElementRef.current = previousActiveElement;

    const modal = modalRef.current;
    if (!modal) return undefined;

    const getFocusableElements = () => Array.from(modal.querySelectorAll(focusableSelector));
    const initialFocus = closeButtonRef.current || getFocusableElements()[0] || modal;

    try {
      initialFocus.focus({ preventScroll: true });
    } catch {
      initialFocus.focus();
    }

    const handleKeyDown = (event) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        handleCloseRef.current?.();
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
      const nextIndex = event.shiftKey ? currentIndex - 1 : currentIndex + 1;

      if (currentIndex === -1 || nextIndex < 0 || nextIndex >= focusableElements.length) {
        event.preventDefault();
        const target = event.shiftKey
          ? focusableElements[focusableElements.length - 1]
          : focusableElements[0];
        target.focus();
      }
    };

    document.addEventListener('keydown', handleKeyDown);

    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      const elementToRestore = previousActiveElementRef.current;
      if (elementToRestore && document.contains(elementToRestore)) {
        elementToRestore.focus();
      }
    };
  }, [isOpen]);

  if (!isOpen) return null;

  return (
    <div
      className="upload-modal-overlay"
      onClick={(event) => {
        if (event.target === event.currentTarget) {
          handleClose();
        }
      }}
    >
      <div
        ref={modalRef}
        className="upload-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex="-1"
      >
        {/* Header */}
        <div className="upload-modal__header">
          <h2 id={titleId} className="upload-modal__title">
            {success ? '¡Archivo Subido!' : 'Subir Archivo de Usuario'}
          </h2>
          <button
            ref={closeButtonRef}
            className="upload-modal__close"
            onClick={handleClose}
            aria-label="Cerrar modal"
          >
            <svg viewBox="0 0 24 24" width="24" height="24">
              <path
                d="M6 6l12 12M18 6l-12 12"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
              />
            </svg>
          </button>
        </div>

        {/* Content */}
        <div className="upload-modal__content">
          {success ? (
            <>
              <div className="upload-modal__success-icon">
                <svg viewBox="0 0 24 24" width="64" height="64">
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
              
              <p className="upload-modal__success-message">
                El archivo ha sido procesado exitosamente y los datos del usuario se están actualizando.
              </p>
            </>
          ) : (
            <>
              <p className="upload-modal__description">
                Sube el archivo genético del usuario que ha comprado el servicio para procesar su información.
              </p>

              <form onSubmit={handleSubmit} className="upload-modal__form">
                {/* Email del usuario */}
                <div className="upload-modal__field">
                  <label htmlFor="upload-user-email" className="upload-modal__label">
                    Email del Usuario
                  </label>
                  <input
                    id="upload-user-email"
                    className="upload-modal__input"
                    type="email"
                    name="userEmail"
                    value={formData.userEmail}
                    onChange={handleInputChange}
                    placeholder="usuario@ejemplo.com"
                    required
                    disabled={loading}
                  />
                </div>

                {/* Zona de subida de archivo */}
                <div 
                  className={`upload-modal__dropzone ${dragActive ? 'upload-modal__dropzone--active' : ''} ${formData.file ? 'upload-modal__dropzone--has-file' : ''}`}
                  onDragEnter={handleDrag}
                  onDragLeave={handleDrag}
                  onDragOver={handleDrag}
                  onDrop={handleDrop}
                >
                  <input
                    type="file"
                    id="file-input"
                    aria-label="Seleccionar archivo"
                    className="upload-modal__file-input"
                    onChange={handleFileChange}
                    disabled={loading}
                    accept=".vcf,.txt,.csv,.zip,.rar"
                  />
                  
                  {formData.file ? (
                    <div className="upload-modal__file-info">
                      <svg viewBox="0 0 24 24" width="48" height="48">
                        <path
                          d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                          stroke="currentColor"
                          strokeWidth="2"
                          fill="none"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                        />
                      </svg>
                      <p className="upload-modal__file-name">{formData.file.name}</p>
                      <p className="upload-modal__file-size">
                        {(formData.file.size / 1024 / 1024).toFixed(2)} MB
                      </p>
                      <button
                        type="button"
                        className="upload-modal__file-remove"
                        onClick={() => setFormData(prev => ({ ...prev, file: null }))}
                      >
                        Cambiar archivo
                      </button>
                    </div>
                  ) : (
                    <>
                      <svg viewBox="0 0 24 24" width="48" height="48">
                        <path
                          d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
                          stroke="currentColor"
                          strokeWidth="2"
                          fill="none"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                        />
                      </svg>
                      <p className="upload-modal__dropzone-text">
                        Arrastra y suelta el archivo aquí
                      </p>
                      <p className="upload-modal__dropzone-subtext">o</p>
                      <label htmlFor="file-input" className="upload-modal__file-button">
                        Seleccionar archivo
                      </label>
                      <p className="upload-modal__dropzone-hint">
                        Formatos: VCF, TXT, CSV, ZIP, RAR (máx. 100MB)
                      </p>
                    </>
                  )}
                </div>

                {/* Mensaje de error */}
                {error && (
                  <div className="upload-modal__error">
                    <svg viewBox="0 0 24 24" width="20" height="20">
                      <path
                        d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                        stroke="currentColor"
                        strokeWidth="2"
                        fill="none"
                        strokeLinecap="round"
                      />
                    </svg>
                    {error}
                  </div>
                )}

                {/* Botones */}
                <div className="upload-modal__actions">
                  <button
                    type="button"
                    className="upload-modal__button upload-modal__button--secondary"
                    onClick={handleClose}
                    disabled={loading}
                  >
                    Cancelar
                  </button>
                  <button
                    type="submit"
                    className="upload-modal__button upload-modal__button--primary"
                    disabled={loading || !formData.file || !formData.userEmail}
                  >
                    {loading ? 'Subiendo...' : 'Subir Archivo'}
                  </button>
                </div>
              </form>
            </>
          )}
        </div>
      </div>
    </div>
  );
};

export default UploadFileModal;