import React, { useMemo } from 'react';
import ModalShell from '../../components/ModalShell/ModalShell';

const VerificationModal = ({ isOpen, onClose, message, title = 'Verificación de cuenta' }) => {
  const cleanMessage = useMemo(() => {
    if (!message) return 'Tu cuenta fue verificada correctamente.';
    let m = message;
    try {
          m = decodeURIComponent(m);
        } catch {
          // Keep the original message when it is not URI-encoded.
        }
    if ((m.startsWith('"') && m.endsWith('"')) || (m.startsWith("'") && m.endsWith("'"))) {
      m = m.slice(1, -1);
    }
    return m;
  }, [message]);

  if (!isOpen) return null;

  return (
    <ModalShell
      maxWidth="520px"
      title={title}
      onClose={onClose}
    >
      <p className="modal-description" style={{ textAlign: 'center' }}>
        {cleanMessage}
      </p>

      <button
        className="modal-submit-btn"
        onClick={onClose}
        style={{ display: 'block', margin: '0 auto' }}
      >
        Entendido
      </button>
    </ModalShell>
  );
};

export default VerificationModal;
