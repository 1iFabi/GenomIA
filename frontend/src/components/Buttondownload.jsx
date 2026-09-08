import React, { useState } from 'react';
import styled from 'styled-components';
import { API_ENDPOINTS } from '../config/api';

const Buttondownload = ({ userName = 'Usuario', isDownloading: externalIsDownloading, setIsDownloading: externalSetIsDownloading }) => {
  const [internalIsDownloading, setInternalIsDownloading] = useState(false);
  const [showModal, setShowModal] = useState(false);
  const [downloadReady, setDownloadReady] = useState(false);
  const [pdfUrl, setPdfUrl] = useState(null);
  const abortControllerRef = React.useRef(null);
  
  const isDownloading = externalIsDownloading !== undefined ? externalIsDownloading : internalIsDownloading;
  const setIsDownloading = externalSetIsDownloading || setInternalIsDownloading;

  const handleCancel = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    setShowModal(false);
    setIsDownloading(false);
  };

  const handleDownload = async () => {
    if (isDownloading) return;
    
    setIsDownloading(true);
    setShowModal(true);
    setDownloadReady(false);
    setPdfUrl(null);

    // Crear nuevo controlador de aborto
    abortControllerRef.current = new AbortController();

    try {
      const baseUrl = API_ENDPOINTS.BASE_URL.endsWith('/') 
          ? API_ENDPOINTS.BASE_URL.slice(0, -1) 
          : API_ENDPOINTS.BASE_URL;
      
      const response = await fetch(`${baseUrl}/api/report/pdf/`, {
          credentials: 'include',
          signal: abortControllerRef.current.signal
      });

      if (!response.ok) {
          throw new Error('Error al generar el reporte');
      }

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      setPdfUrl(url);
      setDownloadReady(true);

      // Intentar descarga automática
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `Reporte_Genetico_${userName}.pdf`);
      document.body.appendChild(link);
      link.click();
      link.parentNode.removeChild(link);
      
    } catch (err) {
      if (err.name === 'AbortError') {
        console.log('Descarga cancelada por el usuario');
        return; // Salir silenciosamente si fue cancelado
      }
      console.error('Error descargando el PDF:', err);
      alert('No se pudo descargar el reporte genético en este momento.');
      setShowModal(false);
    } finally {
      // Solo desactivamos loading si NO estamos listos (si falló o terminó)
      // Si "downloadReady" es true, mantenemos el estado visual hasta que cierren el modal
      // Pero para mantener la lógica simple y consistente con el botón "Descargar PDF" del fondo:
      setIsDownloading(false); 
      abortControllerRef.current = null;
    }
  };

  const closeModal = () => {
    setShowModal(false);
    if (pdfUrl) {
      // window.URL.revokeObjectURL(pdfUrl);
    }
  };

  return (
    <StyledWrapper>
      <button className="button" onClick={handleDownload} disabled={isDownloading}>
        <span className="button-content">
           <svg 
            xmlns="http://www.w3.org/2000/svg" 
            width="18" 
            height="18" 
            viewBox="0 0 24 24" 
            fill="none" 
            stroke="currentColor" 
            strokeWidth="2" 
            strokeLinecap="round" 
            strokeLinejoin="round" 
            style={{ marginRight: '8px' }}
            aria-hidden="true"
          >
            <path d="M12 15V3"></path>
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
            <path d="m7 10 5 5 5-5"></path>
          </svg>
          {isDownloading ? 'Generando...' : 'Descargar PDF'} 
        </span>
      </button>

      {showModal && (
        <div className="modal-overlay">
          <div className="modal-content">
            {!downloadReady ? (
              <div className="modal-step">
                <div className="spinner"></div>
                <h3>Preparando tu reporte</h3>
                <p>Esto puede tardar unos minutos. Estamos analizando tus datos genéticos...</p>
                <button className="cancel-btn" onClick={handleCancel}>Cancelar</button>
              </div>
            ) : (
              <div className="modal-step">
                <div className="success-icon">✓</div>
                <h3>¡Tu reporte está listo!</h3>
                <p>La descarga debería haber comenzado automáticamente.</p>
                <div className="fallback-section">
                  <p>Si la descarga no se inició:</p>
                  <a href={pdfUrl} download={`Reporte_Genetico_${userName}.pdf`} className="download-link">
                    Haz click aquí
                  </a>
                </div>
                <button className="close-btn" onClick={closeModal}>Cerrar</button>
              </div>
            )}
          </div>
        </div>
      )}
    </StyledWrapper>
  );
}

const StyledWrapper = styled.div`
  .button {
    position: relative;
    overflow: hidden;
    height: 3rem;
    padding: 0 2rem;
    border-radius: 1.5rem;
    background: #0b7ad0;
    color: #fff;
    border: none;
    cursor: pointer;
    font-family: 'Inter', system-ui, sans-serif;
    font-weight: 600;
    font-size: 0.875rem;
    z-index: 10;
  }

  .button:disabled {
    opacity: 0.7;
    cursor: not-allowed;
  }

  .button-content {
    display: flex;
    align-items: center;
    justify-content: center;
  }

  /* Modal Styles */
  .modal-overlay {
    position: fixed;
    top: 0;
    left: 0;
    width: 100vw;
    height: 100vh;
    background: rgba(0, 0, 0, 0.6);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 9999;
    backdrop-filter: blur(4px);
  }

  .modal-content {
    background: white;
    padding: 2.5rem;
    border-radius: 1.5rem;
    max-width: 400px;
    width: 90%;
    text-align: center;
    box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04);
    animation: slideIn 0.3s ease-out;
  }

  @keyframes slideIn {
    from { transform: translateY(20px); opacity: 0; }
    to { transform: translateY(0); opacity: 1; }
  }

  .modal-step h3 {
    margin: 1.5rem 0 0.5rem;
    color: #1f2937;
    font-size: 1.25rem;
  }

  .modal-step p {
    color: #6b7280;
    font-size: 0.95rem;
    line-height: 1.5;
  }

  .spinner {
    width: 50px;
    height: 50px;
    border: 4px solid #f3f3f3;
    border-top: 4px solid #0b7ad0;
    border-radius: 50%;
    margin: 0 auto;
    animation: spin 1s linear infinite;
  }

  @keyframes spin {
    0% { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
  }

  .success-icon {
    width: 60px;
    height: 60px;
    background: #ecfdf5;
    color: #10b981;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 2rem;
    margin: 0 auto;
  }

  .fallback-section {
    margin-top: 1.5rem;
    padding-top: 1.5rem;
    border-top: 1px solid #f3f4f6;
  }

  .download-link {
    display: inline-block;
    margin-top: 0.5rem;
    color: #0b7ad0;
    font-weight: 600;
    text-decoration: underline;
    cursor: pointer;
  }

  .close-btn {
    margin-top: 2rem;
    width: 100%;
    padding: 0.75rem;
    background: #f3f4f6;
    border: none;
    border-radius: 0.75rem;
    color: #374151;
    font-weight: 600;
    cursor: pointer;
    transition: background 0.2s;
  }

  .close-btn:hover {
    background: #e5e7eb;
  }

  .cancel-btn {
    margin-top: 1.5rem;
    background: none;
    border: none;
    color: #ef4444;
    font-size: 0.875rem;
    font-weight: 600;
    cursor: pointer;
    text-decoration: underline;
    padding: 0.5rem;
  }

  .cancel-btn:hover {
    color: #dc2626;
  }
`;

export default Buttondownload;