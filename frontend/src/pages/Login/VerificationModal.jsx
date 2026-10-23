import React, { useEffect, useMemo, useState } from 'react';
import ModalShell from '../../components/ModalShell/ModalShell';
import { API_ENDPOINTS, apiRequest } from '../../config/api.js';

const RESEND_COOLDOWN_SECONDS = 60;
// The server answers the same for any address, so the text must not claim a mail was sent.
const RESEND_NOTICES = {
  sent: 'Si el correo está pendiente de verificación, te enviamos un nuevo enlace.',
  throttled: 'Espera un momento antes de pedir otro correo.',
  failed: 'No pudimos reenviar el correo. Inténtalo nuevamente.',
};

const VerificationModal = ({ isOpen, onClose, message, title = 'Verificación de cuenta', resendEmail }) => {
  const [cooldown, setCooldown] = useState(0);
  const [notice, setNotice] = useState('');
  const cooling = cooldown > 0;

  useEffect(() => {
    if (!cooling) return undefined;
    const timer = setInterval(() => setCooldown((seconds) => Math.max(0, seconds - 1)), 1000);
    return () => clearInterval(timer);
  }, [cooling]);

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

  const resend = async () => {
    setCooldown(RESEND_COOLDOWN_SECONDS);
    setNotice('');
    const { ok, status } = await apiRequest(API_ENDPOINTS.RESEND_VERIFICATION, {
      method: 'POST',
      body: JSON.stringify({ email: resendEmail }),
    });
    if (ok) {
      setNotice(RESEND_NOTICES.sent);
    } else if (status === 429) {
      setNotice(RESEND_NOTICES.throttled);
    } else {
      setCooldown(0); // Nothing was sent, so there is nothing to wait for.
      setNotice(RESEND_NOTICES.failed);
    }
  };

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

      {resendEmail && (
        <>
          <button
            type="button"
            className="login-link subtle"
            onClick={resend}
            disabled={cooling}
            style={{ margin: '0 auto 16px' }}
          >
            {cooling ? `Reenviar correo (${cooldown} s)` : 'Reenviar correo'}
          </button>
          {notice && (
            <p className="modal-description" role="status" style={{ textAlign: 'center', fontSize: '14px' }}>
              {notice}
            </p>
          )}
        </>
      )}

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
