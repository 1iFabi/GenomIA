import { describe, expect, it } from 'vitest';
import { slotAt, spinPath, trips } from './helixFrames';

describe('spinPath', () => {
  it('plays one stretch forward and backward', () => {
    const fwd = spinPath(0, 1);
    expect(fwd).toHaveLength(25);
    expect(fwd[0]).toBe('seq_0-1_000.webp');
    expect(fwd.at(-1)).toBe('seq_0-1_024.webp');
    expect(spinPath(1, 0)).toEqual([...fwd].reverse());
  });

  it('goes straight to any module on its own trip, never through the ones between', () => {
    const far = spinPath(4, 0);
    expect(far).toHaveLength(25);
    expect(far[0]).toBe('seq_0-4_024.webp');
    expect(far.at(-1)).toBe('seq_0-4_000.webp');
    expect(spinPath(2, 2)).toEqual([]);
  });
});

describe('trips', () => {
  it('lists every pair once, neighbours first', () => {
    const t = trips(5);
    expect(t).toHaveLength(10);
    expect(t.slice(0, 4)).toEqual(['seq_0-1', 'seq_1-2', 'seq_2-3', 'seq_3-4']);
    expect(t.at(-1)).toBe('seq_0-4');
  });
});

describe('slotAt', () => {
  it('picks the neighbour peeking at the top or bottom, else the stretch on show', () => {
    expect(slotAt(0.05, 2, 5)).toBe(1);
    expect(slotAt(0.5, 2, 5)).toBe(2);
    expect(slotAt(0.95, 2, 5)).toBe(3);
    expect(slotAt(0.05, 0, 5)).toBe(0);
    expect(slotAt(0.95, 4, 5)).toBe(4);
  });
});
