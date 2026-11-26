// Plain Spanish for the admin's activity trail and the service stages.
export const STAGE_NAMES = {
  WAITING_SAMPLE: 'Esperando muestra',
  SAMPLE_RECEIVED: 'Muestra recibida',
  PROCESSING: 'En proceso',
  COMPLETED: 'Completado',
};

const OUTCOMES = { match: 'Coincide', no_match: 'No coincide' };

export const outcomeText = (outcome) => (outcome ? OUTCOMES[outcome] ?? outcome : '');

export const describeEvent = ({ kind, action, actor, subject }) => {
  if (kind === 'genetic') {
    if (action === 'ancestry_cohort') return 'Abrió la cohorte de ancestría';
    return actor?.id === subject?.id ? 'Abrió sus resultados' : 'Abrió los resultados de otra persona';
  }
  if (kind === 'reception') return action === 'verify_rut' ? 'Verificó un RUT' : 'Buscó un cliente por Sample ID';
  return `Movió el servicio a ${STAGE_NAMES[action] ?? action}`;
};

const DATE = new Intl.DateTimeFormat('es-CL', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });

export const formatWhen = (iso) => (iso ? DATE.format(new Date(iso)) : '');
