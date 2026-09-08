import React from 'react';
import '../../styles/modals.css';

/**
 * Shared modal shell. Renders the exact `.modal-*` markup used across all
 * auth/account modals so class names and DOM structure stay identical.
 * `overlayClass` / `modalClass` let each modal keep its existing wrapper class
 * (e.g. `.forgot-password-modal` vs `.delete-account-modal`).
 */
const ModalShell = ({
  overlayClass = 'forgot-password-overlay',
  modalClass = 'forgot-password-modal',
  maxWidth,
  title,
  onClose,
  ariaLabel = 'Cerrar modal',
  showClose = true,
  children,
}) => {
  return (
    <div className={overlayClass}>
      <div className={modalClass} style={maxWidth ? { maxWidth } : undefined}>
        {/* Header */}
        <div className="modal-header">
          <h2 className="modal-title">{title}</h2>
          {showClose && (
            <button
              className="modal-close-btn"
              onClick={onClose}
              aria-label={ariaLabel}
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
          )}
        </div>

        {/* Content */}
        <div className="modal-content">{children}</div>
      </div>
    </div>
  );
};

export default ModalShell;
