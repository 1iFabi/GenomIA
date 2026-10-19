import { describe, expect, it } from 'vitest';
import { buildMedications, matches, placeOf } from './pharmaco';

const rows = [
  { gene: 'CYP2C19', diplotype: '*1/*2', phenotype: 'Metabolizador intermedio', drugs: ['Clopidogrel', 'Omeprazol'] },
  { gene: 'CYP2D6', diplotype: '*1/*1', phenotype: 'Metabolizador normal', drugs: ['Codeína'] },
  { gene: 'CYP2C9', diplotype: '*1/*3', phenotype: 'Metabolizador intermedio', drugs: ['Warfarina', 'Ibuprofeno'] },
  { gene: 'SLCO1B1', diplotype: '*1/*5', phenotype: 'Función disminuida', drugs: ['Simvastatina'] },
  { gene: 'VKORC1', diplotype: 'G/A', phenotype: 'Sensibilidad intermedia', drugs: ['Warfarina'] },
];

describe('pharmacogenetics by medication', () => {
  it('places every phenotype on its own scale, with normal as the usual stretch', () => {
    expect(placeOf('Metabolizador intermedio')).toEqual({ scale: 'metab', step: 1, usual: false });
    expect(placeOf('Metabolizador normal')).toEqual({ scale: 'metab', step: 2, usual: true });
    expect(placeOf('Función disminuida')).toEqual({ scale: 'func', step: 1, usual: false });
    expect(placeOf('Sensibilidad normal')).toEqual({ scale: 'sens', step: 0, usual: true });
    expect(placeOf('Algo nuevo')).toBeNull();
  });

  it('turns gene rows into medications, the warfarin decided by two genes', () => {
    const { all, talk, same } = buildMedications(rows);
    expect(all.map((m) => m.name)).toEqual(['Clopidogrel', 'Omeprazol', 'Codeína', 'Warfarina', 'Ibuprofeno', 'Simvastatina']);
    expect(all.find((m) => m.name === 'Warfarina').genes.map((g) => g.gene)).toEqual(['CYP2C9', 'VKORC1']);
    expect(same.map((m) => m.name)).toEqual(['Codeína']);
    expect(talk).toHaveLength(5);
  });

  it('writes the plain sentence from the mechanism and the step', () => {
    const say = (name, list = rows) => buildMedications(list).all.find((m) => m.name === name).say;
    expect(say('Clopidogrel')).toBe('Tu cuerpo activa el clopidogrel más despacio que la mayoría, así que podría hacerte menos efecto.');
    expect(say('Codeína')).toBe('Activas la codeína como la mayoría de las personas.');
    expect(say('Warfarina')).toBe('Dos de tus genes la mueven: la eliminas más despacio y tu cuerpo es algo más sensible a ella.');
    expect(say('Simvastatina')).toContain('Entra menos a tu hígado');
    // an unknown phenotype gets no verdict, only the plain fact
    const odd = [{ gene: 'CYP2C19', diplotype: '*1/*9', phenotype: 'Metabolizador incierto', drugs: ['Clopidogrel'] }];
    expect(say('Clopidogrel', odd)).toBe('Tu resultado en CYP2C19 es «Metabolizador incierto». Tu médico puede tenerlo en cuenta.');
    expect(buildMedications(odd).talk).toHaveLength(1);
  });

  it('finds a medication by name or by what it is for, ignoring accents', () => {
    const codeine = buildMedications(rows).all.find((m) => m.name === 'Codeína');
    expect(matches(codeine, 'codeina')).toBe(true);
    expect(matches(codeine, 'tos')).toBe(true);
    expect(matches(codeine, 'colesterol')).toBe(false);
  });
});
