import { describe, expect, it } from 'vitest';
import { STAGE_NAMES, describeEvent, outcomeText } from './activityText';

const person = (id) => ({ id, name: `P${id}`, email: `p${id}@x.cl` });

describe('describeEvent', () => {
  it('names a client opening their own results, and someone opening another person\'s', () => {
    expect(describeEvent({ kind: 'genetic', action: 'results', actor: person(1), subject: person(1) })).toBe('Abrió sus resultados');
    expect(describeEvent({ kind: 'genetic', action: 'results', actor: person(2), subject: person(1) })).toBe('Abrió los resultados de otra persona');
    expect(describeEvent({ kind: 'genetic', action: 'ancestry_cohort', actor: person(1), subject: person(1) })).toBe('Abrió la cohorte de ancestría');
  });

  it('names reception look-ups and status changes', () => {
    expect(describeEvent({ kind: 'reception', action: 'search' })).toBe('Buscó un cliente por Sample ID');
    expect(describeEvent({ kind: 'reception', action: 'verify_rut' })).toBe('Verificó un RUT');
    expect(describeEvent({ kind: 'status', action: 'PROCESSING' })).toBe('Movió el servicio a En proceso');
    expect(describeEvent({ kind: 'status', action: 'OTRA' })).toBe('Movió el servicio a OTRA');
  });

  it('spells out the outcome, passing unknown ones through', () => {
    expect(outcomeText('match')).toBe('Coincide');
    expect(outcomeText('no_match')).toBe('No coincide');
    expect(outcomeText('denied')).toBe('denied');
    expect(outcomeText(null)).toBe('');
  });

  it('keeps the four stage names in order', () => {
    expect(Object.values(STAGE_NAMES)).toEqual(['Esperando muestra', 'Muestra recibida', 'En proceso', 'Completado']);
  });
});
