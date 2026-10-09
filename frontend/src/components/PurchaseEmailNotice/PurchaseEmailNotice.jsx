import React from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import VerificationModal from '../../pages/Login/VerificationModal';

/** Aviso en el landing tras completar los datos de compra: el Sample ID llegó (o no) por correo. */
export default function PurchaseEmailNotice() {
  const location = useLocation();
  const navigate = useNavigate();
  const notice = location.state?.purchaseEmail;
  if (!notice) return null;

  const close = () => navigate(location.pathname, { replace: true, state: null });
  const message = notice.sent
    ? `Te enviamos tu Sample ID${notice.email ? ` a ${notice.email}` : ''}. Preséntalo en el laboratorio para realizar tu examen.`
    : 'Registramos tus datos, pero no pudimos enviar el correo. Escríbenos a seqgenomia@gmail.com y te ayudamos.';

  return (
    <VerificationModal
      isOpen
      title={notice.sent ? 'Revisa tu correo' : 'Tus datos quedaron registrados'}
      message={message}
      onClose={close}
    />
  );
}
