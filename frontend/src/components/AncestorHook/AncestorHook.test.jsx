import { describe, expect, it } from 'vitest';
import { ancestorEquivalent } from './ancestorEquivalent';

describe('ancestorEquivalent', () => {
  it.each([
    [0.5, '≈ 1 de tus 2 padres'],
    [0.6, '≈ 2½ de tus 4 abuelos'],
    [0.37, '≈ 1½ de tus 4 abuelos'],
    [0.262, '≈ 1 de tus 4 abuelos'],
    [0.062, '≈ 1 de tus 16 tatarabuelos'],
    [0.027, '≈ 1½ de tus 64 ancestros de hace 6 generaciones'],
    [0.004, '≈ 1 de tus 256 ancestros de hace 8 generaciones'],
    [0.002, '≈ ½ de tus 256 ancestros de hace 8 generaciones'],
    [0.0003, '≈ menos de 1 de tus 256 ancestros de hace 8 generaciones'],
  ])('reads %s as "%s"', (proportion, phrase) => {
    expect(ancestorEquivalent(proportion).phrase).toBe(phrase);
  });

  it('lights whole ancestors and marks a half', () => {
    expect(ancestorEquivalent(0.37)).toMatchObject({ generation: 2, total: 4, lit: 1, partial: 0.5 });
  });
});
