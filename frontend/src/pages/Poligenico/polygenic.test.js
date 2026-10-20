import { describe, expect, it } from 'vitest';
import { alsoFor, below, zOf } from './polygenic';

describe('polygenic words', () => {
  it('counts the people below the reader and never 0 or 100 of them', () => {
    expect([below(0.2), below(99.9), below(41.4)]).toEqual([1, 99, 41]);
  });

  it('falls back to general factors for an unknown condition', () => {
    expect(alsoFor('alzheimer')).toContain('edad');
    expect(alsoFor('nueva')).toBe('La historia de tu familia, la edad y tus hábitos.');
  });

  it('maps a percentile to its z score', () => {
    expect(zOf(50)).toBeCloseTo(0, 4);
    expect(zOf(84.13)).toBeCloseTo(1, 2);
    expect(zOf(0)).toBeLessThan(-2.5);
  });
});
