import { describe, expect, it } from 'vitest';
import { buildContinentShapes, groupByContinent } from './continents';

const continentOf = (code) => ({ CL: 'South America', BO: 'South America', ES: 'Europe' })[code];

describe('groupByContinent', () => {
  it('sums rows by geographic continent, largest first, and skips rows without a known country', () => {
    const groups = groupByContinent([
      { country_code: 'ES', proportion: 0.3 },
      { country_code: 'BO', proportion: 0.1 },
      { country_code: 'CL', proportion: 0.4 },
      { proportion: 0.2 },
    ], continentOf);
    expect(groups.map(({ key, label, proportion, rows }) => [key, label, proportion, rows.map((row) => row.country_code)]))
      .toEqual([['South America', 'Sudamérica', 0.5, ['CL', 'BO']], ['Europe', 'Europa', 0.3, ['ES']]]);
  });
});

describe('buildContinentShapes', () => {
  it('keeps a ring that crosses the antimeridian continuous instead of striping the frame', () => {
    const russia = { geometry: { type: 'Polygon', coordinates: [[[170, 65], [-170, 66], [-170, 70], [170, 70], [170, 65]]] } };
    const [shape] = Object.values(buildContinentShapes([russia], () => ({ continent: 'Asia', code: 'RU' }), [
      { key: 'Europe', rows: [] },
    ]));
    const xs = shape.context.match(/-?\d+\.\d/g).filter((_, index) => index % 2 === 0).map(Number);
    expect(Math.max(...xs) - Math.min(...xs)).toBeLessThan(40);
  });
});
