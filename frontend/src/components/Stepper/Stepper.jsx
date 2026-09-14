import React, { useState, Children, useRef, useLayoutEffect } from 'react';
import { motion as Motion, AnimatePresence, useReducedMotion } from 'motion/react';

import './Stepper.css';

export default function Stepper({
  children,
  initialStep = 1,
  onStepChange = () => {},
  onFinalStepCompleted = () => {},
  validateStep = () => true,
  stepCircleContainerClassName = '',
  stepContainerClassName = '',
  contentClassName = '',
  footerClassName = '',
  backButtonProps = {},
  nextButtonProps = {},
  backButtonText = 'Back',
  nextButtonText = 'Continue',
  disableStepIndicators = false,
  isSubmitting = false,
  isNextDisabled = false,
  renderStepIndicator,
  onKeyDown,
  ...rest
}) {
  const [currentStep, setCurrentStep] = useState(initialStep);
  const [direction, setDirection] = useState(0);
  const shouldReduceMotion = useReducedMotion() === true;
  const submissionInProgressRef = useRef(false);
  const validationInProgressRef = useRef(false);
  const stepsArray = Children.toArray(children);
  const totalSteps = stepsArray.length;
  const isCompleted = currentStep > totalSteps;
  const isLastStep = currentStep === totalSteps;

  const updateStep = newStep => {
    setCurrentStep(newStep);
    if (newStep > totalSteps) {
      // Finalización controlada desde handleComplete
      // No invocar onFinalStepCompleted aquí para permitir cancelación asíncrona
    } else {
      onStepChange(newStep);
    }
  };

  const handleBack = () => {
    if (isNextDisabled || validationInProgressRef.current) return;
    if (currentStep > 1) {
      setDirection(-1);
      updateStep(currentStep - 1);
    }
  };

  const handleNext = async () => {
    if (isSubmitting || isNextDisabled || validationInProgressRef.current || isLastStep) return;

    validationInProgressRef.current = true;
    try {
      // Validar el paso actual antes de avanzar; puede requerir una petición asíncrona.
      if (await validateStep(currentStep)) {
        setDirection(1);
        updateStep(currentStep + 1);
      }
    } finally {
      validationInProgressRef.current = false;
    }
  };

  const handleComplete = async () => {
    if (isSubmitting || submissionInProgressRef.current) return;

    submissionInProgressRef.current = true;
    try {
      // Validar el último paso antes de completar
      if (await validateStep(currentStep)) {
        // Permitir que el consumidor cancele la finalización devolviendo false
        try {
          const result = onFinalStepCompleted();
          const proceed = typeof result === 'boolean' ? result : (typeof result?.then === 'function' ? await result : true);
          if (proceed !== false) {
            setDirection(1);
            updateStep(totalSteps + 1);
          }
        } catch {
          // Si hay excepción, no finalizar
        }
      }
    } finally {
      submissionInProgressRef.current = false;
    }
  };

  // Permitir avanzar/completar con Enter desde cualquier input del paso.
  // Se ignora Enter en textareas (saltos de línea) y en botones (para no
  // duplicar el click nativo del botón enfocado).
  const handleEnterKey = (e) => {
    if (e.key === 'Enter' && e.target.tagName === 'INPUT') {
      e.preventDefault();
      if (isLastStep) {
        handleComplete();
      } else {
        void handleNext();
      }
    }
  };

  return (
    <div
      className="outer-container"
      {...rest}
      aria-busy={isSubmitting || rest['aria-busy']}
      onKeyDown={(e) => {
        handleEnterKey(e);
        onKeyDown?.(e);
      }}
    >
      <div className={`step-circle-container step-${currentStep} ${stepCircleContainerClassName}`}>
        <div className={`step-indicator-row ${stepContainerClassName}`}>
          {stepsArray.map((_, index) => {
            const stepNumber = index + 1;
            const isNotLastStep = index < totalSteps - 1;
            return (
              <React.Fragment key={stepNumber}>
                {renderStepIndicator ? (
                  renderStepIndicator({
                    step: stepNumber,
                    currentStep,
                    onStepClick: clicked => {
                      setDirection(clicked > currentStep ? 1 : -1);
                      updateStep(clicked);
                    }
                  })
                ) : (
                  <StepIndicator
                    step={stepNumber}
                    disableStepIndicators={disableStepIndicators}
                    reducedMotion={shouldReduceMotion}
                    currentStep={currentStep}
                    onClickStep={clicked => {
                      setDirection(clicked > currentStep ? 1 : -1);
                      updateStep(clicked);
                    }}
                  />
                )}
                {isNotLastStep && (
                  <StepConnector
                    isComplete={currentStep > stepNumber}
                    reducedMotion={shouldReduceMotion}
                  />
                )}
              </React.Fragment>
            );
          })}
        </div>

        <StepContentWrapper
          isCompleted={isCompleted}
          currentStep={currentStep}
          direction={direction}
          reducedMotion={shouldReduceMotion}
          className={`step-content-default ${contentClassName}`}
        >
          {stepsArray[currentStep - 1]}
        </StepContentWrapper>

        {!isCompleted && (
          <div className={`footer-container ${footerClassName}`}>
            <div className={`footer-nav ${currentStep !== 1 ? 'spread' : 'end'}`}>
              {currentStep !== 1 && (
                <button
                  onClick={handleBack}
                  className={`back-button ${currentStep === 1 ? 'inactive' : ''}`}
                  {...backButtonProps}
                  disabled={isSubmitting || isNextDisabled || backButtonProps.disabled}
                  type="button"
                >
                  {backButtonText}
                </button>
              )}
              <button
                onClick={isLastStep ? handleComplete : handleNext}
                className="next-button"
                {...nextButtonProps}
                disabled={isSubmitting || isNextDisabled || nextButtonProps.disabled}
                type="button"
              >
                {isSubmitting ? 'Procesando...' : (isLastStep ? 'Registrar' : nextButtonText)}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function StepContentWrapper({ isCompleted, currentStep, direction, children, className, reducedMotion }) {
  const [parentHeight, setParentHeight] = useState(0);

  return (
    <Motion.div
      className={className}
      style={{ position: 'relative', overflow: 'visible' }}
      animate={{ height: isCompleted ? 0 : parentHeight }}
      transition={reducedMotion ? { duration: 0 } : { type: 'spring', duration: 0.4 }}
    >
      <AnimatePresence initial={false} mode="sync" custom={direction}>
        {!isCompleted && (
          <SlideTransition
            key={currentStep}
            direction={direction}
            reducedMotion={reducedMotion}
            onHeightReady={h => setParentHeight(h)}
          >
            {children}
          </SlideTransition>
        )}
      </AnimatePresence>
    </Motion.div>
  );
}

function SlideTransition({ children, direction, onHeightReady, reducedMotion }) {
  const containerRef = useRef(null);

  useLayoutEffect(() => {
    const container = containerRef.current;
    if (!container) return undefined;

    const reportHeight = () => onHeightReady(container.offsetHeight);
    reportHeight();

    if (typeof ResizeObserver === 'undefined') return undefined;

    const observer = new ResizeObserver(reportHeight);
    observer.observe(container);
    return () => observer.disconnect();
  }, [onHeightReady]);

  return (
    <Motion.div
      ref={containerRef}
      custom={direction}
      variants={reducedMotion ? reducedStepVariants : stepVariants}
      initial="enter"
      animate="center"
      exit="exit"
      transition={reducedMotion ? { duration: 0 } : { duration: 0.4 }}
      style={{ position: 'absolute', left: 0, right: 0, top: 0 }}
    >
      {children}
    </Motion.div>
  );
}

const stepVariants = {
  enter: dir => ({
    x: dir >= 0 ? '-100%' : '100%',
    opacity: 0
  }),
  center: {
    x: '0%',
    opacity: 1
  },
  exit: dir => ({
    x: dir >= 0 ? '50%' : '-50%',
    opacity: 0
  })
};

const reducedStepVariants = {
  enter: { x: '0%', opacity: 1 },
  center: { x: '0%', opacity: 1 },
  exit: { x: '0%', opacity: 1 }
};

const stepIndicatorVariants = {
  inactive: { scale: 1, backgroundColor: '#e2e8f0', color: '#94a3b8' },
  active: { scale: 1, backgroundColor: '#4A90E2', color: '#4A90E2' },
  complete: { scale: 1, backgroundColor: '#4A90E2', color: '#ffffff' }
};

const reducedStepIndicatorVariants = {
  inactive: { backgroundColor: '#e2e8f0', color: '#94a3b8' },
  active: { backgroundColor: '#4A90E2', color: '#4A90E2' },
  complete: { backgroundColor: '#4A90E2', color: '#ffffff' }
};

export function Step({ children }) {
  return <div className="step-default">{children}</div>;
}

function StepIndicator({ step, currentStep, onClickStep, disableStepIndicators, reducedMotion }) {
  const status = currentStep === step ? 'active' : currentStep < step ? 'inactive' : 'complete';

  const handleClick = () => {
    if (step !== currentStep && !disableStepIndicators) onClickStep(step);
  };

  const ariaLabel = disableStepIndicators
    ? `Paso ${step}, deshabilitado`
    : status === 'active'
      ? `Paso ${step}, actual`
      : status === 'complete'
        ? `Paso ${step}, completado`
        : `Ir al paso ${step}`;

  return (
    <Motion.button
      type="button"
      onClick={handleClick}
      className="step-indicator"
      animate={status}
      initial={false}
      disabled={disableStepIndicators}
      aria-current={status === 'active' ? 'step' : undefined}
      aria-label={ariaLabel}
      style={{ cursor: disableStepIndicators ? 'default' : 'pointer' }}
    >
      <Motion.div
        variants={reducedMotion ? reducedStepIndicatorVariants : stepIndicatorVariants}
        transition={reducedMotion ? { duration: 0 } : { duration: 0.3 }}
        className="step-indicator-inner"
      >
        {status === 'complete' ? (
          <CheckIcon className="check-icon" reducedMotion={reducedMotion} />
        ) : status === 'active' ? (
          <div className="active-dot" />
        ) : (
          <span className="step-number">{step}</span>
        )}
      </Motion.div>
    </Motion.button>
  );
}

function StepConnector({ isComplete, reducedMotion }) {
  const lineVariants = {
    incomplete: { width: 0, backgroundColor: 'transparent' },
    complete: { width: '100%', backgroundColor: '#4A90E2' }
  };

  return (
    <div className="step-connector">
      <Motion.div
        className="step-connector-inner"
        variants={lineVariants}
        initial={false}
        animate={isComplete ? 'complete' : 'incomplete'}
        transition={reducedMotion ? { duration: 0 } : { duration: 0.4 }}
      />
    </div>
  );
}

function CheckIcon({ reducedMotion = false, ...props }) {
  return (
    <svg {...props} fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
      {reducedMotion ? (
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M5 13l4 4L19 7"
        />
      ) : (
        <Motion.path
          initial={{ pathLength: 0 }}
          animate={{ pathLength: 1 }}
          transition={{ delay: 0.1, type: 'tween', ease: 'easeOut', duration: 0.3 }}
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M5 13l4 4L19 7"
        />
      )}
    </svg>
  );
}
