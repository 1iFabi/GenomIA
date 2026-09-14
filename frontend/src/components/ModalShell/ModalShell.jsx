import React, { useEffect, useId, useRef } from 'react';
import '../../styles/modals.css';

/**
 * Shared modal shell. Renders the exact `.modal-*` markup used across all
 * auth/account modals so class names and DOM structure stay identical.
 * `overlayClass` / `modalClass` let each modal keep its existing wrapper class
 * (e.g. `.forgot-password-modal` vs `.delete-account-modal`).
 */
const focusableSelector = [
  'a[href]',
  'area[href]',
  'button:not([disabled])',
  'input:not([disabled]):not([type="hidden"])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',');

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
  const modalRef = useRef(null);
  const closeButtonRef = useRef(null);
  const previousActiveElementRef = useRef(null);
  const onCloseRef = useRef(onClose);
  const titleId = `modal-title-${useId().replace(/:/g, '')}`;

  onCloseRef.current = onClose;

  useEffect(() => {
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
        onCloseRef.current?.();
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
  }, []);

  const handleBackdropClick = (event) => {
    if (event.target === event.currentTarget) {
      onCloseRef.current?.();
    }
  };

  return (
    <div className={overlayClass} onClick={handleBackdropClick}>
      <div
        ref={modalRef}
        className={modalClass}
        style={maxWidth ? { maxWidth } : undefined}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex="-1"
      >
        {/* Header */}
        <div className="modal-header">
          <h2 id={titleId} className="modal-title">{title}</h2>
          {showClose && (
            <button
              ref={closeButtonRef}
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
