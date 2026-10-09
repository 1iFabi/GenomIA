import { describe, expect, it } from 'vitest';
import { normalizeRut } from './rut';

describe('normalizeRut', () => {
  it('accepts valid check digits with or without dots and normalizes K', () => {
    expect(normalizeRut('12.345.678-5')).toBe('12345678-5');
    expect(normalizeRut('7654321-6')).toBe('7654321-6');
    expect(normalizeRut(' 10000013-k ')).toBe('10000013-K');
  });

  it('rejects wrong check digits and malformed input', () => {
    for (const value of ['12345678-K', '12345678', 'abc', '', null]) {
      expect(normalizeRut(value)).toBeNull();
    }
  });
});
