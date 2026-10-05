import React, { useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import './CountryInsightPopover.css';

const hasValue = (value) => value !== null && value !== undefined && value !== '';

const formatNumber = (value, decimals = 2) => {
  const number = Number(value);
  return Number.isFinite(number) ? number.toFixed(decimals) : String(value);
};

const formatAlleleFrequency = (value) => {
  const number = Number(value);
  if (!Number.isFinite(number)) return String(value);
  const percentage = number <= 1 ? number * 100 : number;
  return `${percentage.toFixed(2)}%`;
};

const getContinentLabel = (value) => ({
  Africa: 'África',
  Asia: 'Asia',
  Europe: 'Europa',
  Oceania: 'Oceanía',
  'North America': 'América del Norte',
  'South America': 'América del Sur',
})[value] || value;

const CountryInsightPopover = ({
  country,
  anchorPoint,
  isMobile = false,
  onClose,
  openedByKeyboard = false,
  returnFocusRef,
  portalTarget = document.body,
}) => {
  const popoverRef = useRef(null);
  const closeButtonRef = useRef(null);
  const previousFocusRef = useRef(null);
  const returnFocusTargetRef = useRef(null);
  const previousPortalTargetRef = useRef(portalTarget);
  returnFocusTargetRef.current = returnFocusRef?.current || null;
  const [isVisible, setIsVisible] = useState(false);
  const [isDetailsOpen, setIsDetailsOpen] = useState(false);
  const [desktopPosition, setDesktopPosition] = useState({
    top: 16,
    left: 16,
    transformOrigin: 'center top',
  });
  const titleId = useId().replace(/:/g, '');
  const detailsId = `${titleId}-details`;
  const countryName = country?.name || 'País sin nombre';
  const countryIso2 = country?.isoCode || country?.countryInfo?.code;
  const flagUrl = countryIso2
    ? `https://flagcdn.com/w80/${String(countryIso2).toLowerCase()}.png`
    : null;
  const percentage = Number(country?.percentage);

  const detailFields = [
    {
      key: 'continent',
      label: 'Continente',
      value: hasValue(country?.continent) ? getContinentLabel(country.continent) : null,
    },
    {
      key: 'variant_count',
      label: 'Variantes analizadas',
      value: hasValue(country?.variant_count) ? formatNumber(country.variant_count, 0) : null,
    },
    {
      key: 'avg_allele_frequency',
      label: 'Frecuencia alélica promedio',
      value: hasValue(country?.avg_allele_frequency)
        ? formatAlleleFrequency(country.avg_allele_frequency)
        : null,
    },
  ];
  const details = detailFields.filter((detail) => hasValue(detail.value));
  const unavailableDetails = detailFields
    .filter((detail) => !hasValue(detail.value))
    .map((detail) => detail.label);

  useEffect(() => {
    previousFocusRef.current = document.activeElement;

    if (openedByKeyboard) {
      setIsVisible(true);
      closeButtonRef.current?.focus();
      return undefined;
    }

    const frame = window.requestAnimationFrame(() => {
      setIsVisible(true);
      closeButtonRef.current?.focus();
    });

    return () => window.cancelAnimationFrame(frame);
  }, [openedByKeyboard]);

  useEffect(() => {
    return () => {
      const focusTarget = returnFocusTargetRef.current || previousFocusRef.current;
      if (focusTarget && focusTarget.isConnected) {
        window.requestAnimationFrame(() => focusTarget.focus?.());
      }
    };
  }, [returnFocusRef]);

  useEffect(() => {
    setIsDetailsOpen(false);
  }, [country?.isoCode, country?.name]);

  useEffect(() => {
    const handleKeyDown = (event) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        event.stopPropagation();
        onClose();
        return;
      }

      if (event.key === 'Tab' && popoverRef.current) {
        const focusableElements = [...popoverRef.current.querySelectorAll('button:not([disabled])')];
        const firstElement = focusableElements[0];
        const lastElement = focusableElements[focusableElements.length - 1];

        if (!firstElement || !lastElement) return;
        if (event.shiftKey && document.activeElement === firstElement) {
          event.preventDefault();
          lastElement.focus();
        } else if (!event.shiftKey && document.activeElement === lastElement) {
          event.preventDefault();
          firstElement.focus();
        }
      }
    };

    const handlePointerDown = (event) => {
      if (!popoverRef.current?.contains(event.target)) onClose();
    };

    document.addEventListener('keydown', handleKeyDown);
    document.addEventListener('pointerdown', handlePointerDown);
    document.addEventListener('click', handlePointerDown);

    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      document.removeEventListener('pointerdown', handlePointerDown);
      document.removeEventListener('click', handlePointerDown);
    };
  }, [onClose]);

  useEffect(() => {
    if (!isMobile) return undefined;

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, [isMobile]);

  const updateDesktopPosition = useCallback(() => {
    if (!anchorPoint || !popoverRef.current) return;

    const margin = 16;
    const gap = 14;
    const currentAnchor = anchorPoint;
    const { width, height } = popoverRef.current.getBoundingClientRect();
    const viewportWidth = window.innerWidth;
    const viewportHeight = window.innerHeight;
    const preferredLeft = currentAnchor.x + gap;
    const preferredTop = currentAnchor.y + gap;
    const opensRight = preferredLeft + width <= viewportWidth - margin;
    const opensBelow = preferredTop + height <= viewportHeight - margin;
    const left = opensRight
      ? preferredLeft
      : Math.max(margin, currentAnchor.x - width - gap);
    const top = opensBelow
      ? preferredTop
      : Math.max(margin, currentAnchor.y - height - gap);
    const originX = Math.max(0, Math.min(width, currentAnchor.x - left));
    const originY = Math.max(0, Math.min(height, currentAnchor.y - top));

    setDesktopPosition({
      left,
      top,
      transformOrigin: `${originX}px ${originY}px`,
    });
  }, [anchorPoint]);

  useLayoutEffect(() => {
    if (previousPortalTargetRef.current === portalTarget) return;
    previousPortalTargetRef.current = portalTarget;
    closeButtonRef.current?.focus();
  }, [portalTarget]);

  useLayoutEffect(() => {
    updateDesktopPosition();

    const handleViewportChange = () => updateDesktopPosition();
    window.addEventListener('resize', handleViewportChange);
    window.addEventListener('scroll', handleViewportChange, true);

    return () => {
      window.removeEventListener('resize', handleViewportChange);
      window.removeEventListener('scroll', handleViewportChange, true);
    };
  }, [isDetailsOpen, portalTarget, updateDesktopPosition]);

  if (!country || !anchorPoint) return null;

  const percentageLabel = Number.isFinite(percentage)
    ? `${percentage.toFixed(1)}%`
    : 'Sin porcentaje';
  const popoverClassName = [
    'country-insight-popover',
    isMobile ? 'country-insight-popover--mobile' : '',
    isVisible ? 'country-insight-popover--visible' : '',
    openedByKeyboard ? 'country-insight-popover--instant' : '',
  ].filter(Boolean).join(' ');

  return createPortal(
    <>
      <div
        className={`country-insight-popover__backdrop ${isVisible ? 'country-insight-popover__backdrop--visible' : ''} ${openedByKeyboard ? 'country-insight-popover__backdrop--instant' : ''}`}
        aria-hidden="true"
        onPointerDown={onClose}
      />
      <section
        ref={popoverRef}
        className={popoverClassName}
        role="dialog"
        aria-modal={isMobile ? 'true' : 'false'}
        aria-labelledby={`${titleId}-title`}
        aria-describedby={`${titleId}-summary`}
        style={desktopPosition}
        onPointerDown={(event) => event.stopPropagation()}
        onClick={(event) => event.stopPropagation()}
      >
        <header className="country-insight-popover__header">
          {flagUrl && (
            <img
              key={countryIso2}
              className="country-insight-popover__flag"
              src={flagUrl}
              alt=""
              onError={(event) => {
                event.currentTarget.hidden = true;
              }}
            />
          )}
          <div className="country-insight-popover__heading">
            <span className="country-insight-popover__label">País</span>
            <h2 id={`${titleId}-title`}>{countryName}</h2>
          </div>
        </header>

        <div
          className="country-insight-popover__percentage"
          aria-label={`Porcentaje de ascendencia: ${percentageLabel}`}
        >
          <span className="country-insight-popover__percentage-label">Estimación de ancestría</span>
          <strong>{percentageLabel}</strong>
        </div>

        <p id={`${titleId}-summary`} className="country-insight-popover__summary">
          Estimación basada en los datos analizados para tu perfil.
        </p>

        <div className="country-insight-popover__details">
          <button
            className="country-insight-popover__details-toggle"
            type="button"
            aria-expanded={isDetailsOpen}
            aria-controls={detailsId}
            onClick={() => setIsDetailsOpen((open) => !open)}
          >
            <span>{isDetailsOpen ? 'Ocultar datos disponibles' : 'Ver datos disponibles'}</span>
            <span className="country-insight-popover__details-mark" aria-hidden="true">
              {isDetailsOpen ? '−' : '+'}
            </span>
          </button>
          <div
            id={detailsId}
            className={`country-insight-popover__details-panel ${isDetailsOpen ? 'country-insight-popover__details-panel--open' : ''}`}
            aria-hidden={!isDetailsOpen}
          >
            <div className="country-insight-popover__details-inner">
              {details.length > 0 && (
                <dl className="country-insight-popover__details-list">
                  {details.map((detail) => (
                    <div className="country-insight-popover__detail-row" key={detail.key}>
                      <dt>{detail.label}</dt>
                      <dd>{detail.value}</dd>
                    </div>
                  ))}
                </dl>
              )}
              {unavailableDetails.length > 0 && (
                <p className="country-insight-popover__empty-details">
                  No disponible en los datos analizados: {unavailableDetails.join(', ')}.
                </p>
              )}
            </div>
          </div>
        </div>

        <footer className="country-insight-popover__footer">
          <button
            ref={closeButtonRef}
            className="country-insight-popover__close"
            type="button"
            onClick={onClose}
          >
            Cerrar
          </button>
        </footer>
      </section>
    </>,
    portalTarget
  );
};

export default CountryInsightPopover;
