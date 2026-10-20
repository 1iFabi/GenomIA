import { describe, expect, it } from 'vitest';
import { QUESTIONS, bucket, byGene, certainty, certaintyWhy, consequence, rank, significanceOf } from './monogenic';

describe('monogenic risk', () => {
  it('sends each variant to the one question its inheritance and copies answer', () => {
    expect(bucket({ inheritance: null, zygosity: 'heterocigoto' })).toBe('conversar');
    expect(bucket({ inheritance: 'AD', zygosity: 'heterocigoto' })).toBe('salud');
    expect(bucket({ inheritance: 'AR', zygosity: 'homocigoto' })).toBe('salud');
    expect(bucket({ inheritance: 'AR', zygosity: 'heterocigoto' })).toBe('transmitir');
    expect(bucket({ inheritance: 'XL', zygosity: 'heterocigoto' })).toBe('conversar');
  });

  it('orders known inheritance first and two copies before one', () => {
    const variants = [
      { inheritance: null, zygosity: 'heterocigoto' },
      { inheritance: 'AR', zygosity: 'heterocigoto' },
      { inheritance: 'AR', zygosity: 'homocigoto' },
    ];
    expect(variants.sort((a, b) => rank(a) - rank(b)).map((v) => [v.inheritance, v.zygosity])).toEqual([
      ['AR', 'homocigoto'], ['AR', 'heterocigoto'], [null, 'heterocigoto'],
    ]);
  });

  it('reads the review status stars as the certainty of the call', () => {
    expect(certainty(4)).toBe('Evidencia bien establecida');
    expect(certainty(3)).toBe('Evidencia bien establecida');
    expect(certainty(2)).toBe('Evidencia moderada');
    expect(certainty(1)).toBe('Revisión limitada');
    expect(certainty(0)).toBe('Revisión limitada');
    expect(certainty(undefined)).toBe('Revisión limitada');
  });

  it('writes the consequence for the question, with two copies read as expressed', () => {
    const homo = { inheritance: 'AR', zygosity: 'homocigoto' };
    expect(consequence({ inheritance: 'AD', zygosity: 'heterocigoto' }, 'salud')).toContain('Con una copia basta');
    expect(consequence(homo, 'salud')).toContain('las dos copias alteradas');
    expect(consequence({ inheritance: 'AR', zygosity: 'heterocigoto' }, 'transmitir')).toContain('Tu salud no cambia');
    expect(consequence({ inheritance: null }, 'conversar')).toContain('no tenemos curado');
  });

  it('keeps one question per bucket and spells the classifications as the reader sees them', () => {
    expect(Object.keys(QUESTIONS)).toEqual(['salud', 'transmitir', 'conversar']);
    expect(QUESTIONS.salud.not).toContain('No significa');
    expect(significanceOf('Pathogenic/Likely_pathogenic')).toBe('Patogénica / Probablemente patogénica');
    expect(significanceOf('risk_factor')).toBe('risk factor');
    expect(significanceOf(null)).toBe('');
  });

  it('explains the stars and groups variants of one gene into one row, best variant first', () => {
    expect(certaintyWhy(4)).toContain('panel de expertos');
    expect(certaintyWhy(2)).toContain('Varios laboratorios');
    expect(certaintyWhy(0)).toContain('un solo laboratorio');
    const groups = byGene([
      { variant_id: 'a', gene: 'AGRN', inheritance: 'AR', zygosity: 'heterocigoto' },
      { variant_id: 'b', gene: 'B3GALT6', inheritance: 'AR', zygosity: 'homocigoto' },
      { variant_id: 'c', gene: 'AGRN', inheritance: 'AR', zygosity: 'homocigoto' },
      { variant_id: 'd', gene: '', inheritance: null, zygosity: 'heterocigoto' },
    ]);
    expect(groups.map((g) => g.map((v) => v.variant_id))).toEqual([['b'], ['c', 'a'], ['d']]);
  });
});
