import React, { useContext, useEffect, useId, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { Globe, LogOut, Menu, MessageCircleQuestion, UserRound, X } from 'lucide-react';
import { GenominContext } from '../../context/use-genomin';
import './AccountMenu.css';

/**
 * The client's account behind the three-line button, top right: a small glass list that grows
 * out of the button. Colours come from the page (--ink, --tint).
 * Back to the results is the arrow beside the module dots; here the public site is named as such,
 * so the two never read alike. Password and account deletion live on /profile ("Mi cuenta").
 */
const AccountMenu = ({ user, onLogout, className = '' }) => {
  const [open, setOpen] = useState(false);
  const root = useRef(null);
  const toggle = useRef(null);
  const id = useId();
  const genomin = useContext(GenominContext); // optional: the menu also renders outside the provider
  const name = [user?.first_name, user?.firstName, user?.name, user?.username].find(Boolean);
  const firstName = name ? String(name).split(' ')[0] : 'Tu cuenta';

  useEffect(() => {
    if (!open) return undefined;
    const esc = (e) => {
      if (e.key !== 'Escape') return;
      setOpen(false);
      toggle.current?.focus();
    };
    const outside = (e) => { if (!root.current?.contains(e.target)) setOpen(false); };
    window.addEventListener('keydown', esc);
    document.addEventListener('pointerdown', outside);
    return () => {
      window.removeEventListener('keydown', esc);
      document.removeEventListener('pointerdown', outside);
    };
  }, [open]);

  const close = () => setOpen(false);

  return (
    <div className={`acct ${className}`} ref={root} data-open={open ? '' : undefined}>
      <button
        type="button"
        ref={toggle}
        className="acct__toggle"
        onClick={() => setOpen((o) => !o)}
        aria-label={open ? 'Cerrar menú' : 'Abrir menú'}
        aria-expanded={open}
        aria-controls={id}
      >
        {open ? <X size={20} strokeWidth={2.25} aria-hidden="true" /> : <Menu size={20} strokeWidth={2.25} aria-hidden="true" />}
      </button>

      {open && (
        <nav className="acct__pop" id={id} aria-label="Tu cuenta">
          <p className="acct__who"><b>{firstName}</b><span>Cliente GenomIA</span></p>
          <ul>
            <li><Link className="acct__item" to="/profile" onClick={close}><UserRound aria-hidden="true" />Mi cuenta</Link></li>
            <li><Link className="acct__item" to="/" onClick={close}><Globe aria-hidden="true" />Ir al sitio de GenomIA</Link></li>
            {genomin && (
              <li>
                <button type="button" className="acct__item" onClick={() => { close(); genomin.openGenomin(); }}>
                  <MessageCircleQuestion aria-hidden="true" />Pregúntale a Genomin
                </button>
              </li>
            )}
            {onLogout && (
              <>
                <li className="acct__sep" aria-hidden="true" />
                <li>
                  <button type="button" className="acct__item acct__item--danger" onClick={() => { close(); onLogout(); }}>
                    <LogOut aria-hidden="true" />Cerrar sesión
                  </button>
                </li>
              </>
            )}
          </ul>
        </nav>
      )}
    </div>
  );
};

export default AccountMenu;
