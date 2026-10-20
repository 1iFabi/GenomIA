import { describe, expect, it } from 'vitest';
import { buildContinentShapes, groupByContinent } from './continents';

const continentOf = (code) => ({ CL: 'South America', BO: 'South America', ES: 'Europe' })[code];

describe('groupByContinent', () => {
  it('lists each unit once per continent with its countries there underneath', () => {
    const groups = groupByContinent([
      { population: 'IBS', label: 'Ibérico', region_countries: ['ES'], proportion: 0.3 },
      { population: 'AMR_ANDES', label: 'Andino', region_countries: ['CL', 'BO', 'XX'], proportion: 0.4 },
      { population: 'AMR_AMAZON', label: 'Amazónico', region_countries: ['BO'], proportion: 0.1 },
    ], continentOf, (code) => `país ${code}`);
    expect(groups.map(({ key, proportion, countries, rows }) => [
      key, proportion, countries, rows.map((row) => `${row.population}:${row.places.map((place) => place.name)}`)]))
      .toEqual([
        ['South America', 0.5, 2, ['AMR_ANDES:país CL,país BO', 'AMR_AMAZON:país BO']],
        ['Europe', 0.3, 1, ['IBS:país ES']],
      ]);
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
