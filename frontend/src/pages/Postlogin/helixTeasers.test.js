import { describe, expect, it } from 'vitest';
import { helixReadings, helixTeasers } from './helixTeasers';

describe('helixReadings', () => {
  it('reads each real figure several ways, but monogenic risk only as its count', () => {
    const r = helixReadings({
      modules: {
        global_ancestry: [{ group_label: 'Amerindio', proportion: 0.57 }, { group_label: 'Europeo', proportion: 0.43 }],
        pharmacogenetics: [{ gene: 'CYP2D6' }],
        monogenic_risk: [{ gene: 'AGRN', clinical_significance: 'Pathogenic' }],
      },
      variant_summary: { total: 1500 },
    });
    expect(r.global_ancestry).toEqual([
      'Tu componente principal es amerindio: 57,0%.',
      'Tu mapa reúne 2 componentes: amerindio y europeo.',
      '¿Te cuento de dónde viene tu 43,0% europeo?',
      'Tus raíces, continente por continente.',
    ]);
    expect(r.pharmacogenetics[0]).toBe('Leí 1 gen que influye en cómo procesas remedios.');
    expect(r.monogenic_risk).toEqual(['Revisé 1.500 variantes contra ClinVar.']);
    expect(JSON.stringify(r)).not.toMatch(/AGRN|Pathogenic/);
    expect(helixReadings(null)).toEqual({});
  });
});

describe('helixTeasers', () => {
  it('summarizes each module from real rows, never a monogenic finding', () => {
    const t = helixTeasers({
      modules: {
        global_ancestry: [
          { label: 'Mapuche', group_label: 'Amerindio', proportion: 0.37 },
          { label: 'Aymara', group_label: 'Amerindio', proportion: 0.15 },
          { label: 'Ibérico', group_label: 'Europeo', proportion: 0.4 },
        ],
        pharmacogenetics: [{ gene: 'CYP2D6' }, { gene: 'CYP2C19' }, { gene: 'CYP2C9' }, { gene: 'SLCO1B1' }],
        traits: [{ category: 'Metabolismo' }, { category: 'Metabolismo' }, { category: 'Cognición' }],
        polygenic_risk: [{}, {}],
        monogenic_risk: [{ gene: 'AGRN', clinical_significance: 'Pathogenic' }],
      },
      variant_summary: { total: 1500 },
    });
    expect(t.global_ancestry).toEqual({ figure: '52,0%', caption: 'componente amerindio' });
    expect(t.pharmacogenetics).toEqual({ figure: '4', caption: 'genes: CYP2D6, CYP2C19, CYP2C9 y más' });
    expect(t.traits).toEqual({ figure: '3', caption: 'rasgos en 2 categorías' });
    expect(t.polygenic_risk).toEqual({ figure: '2', caption: 'condiciones comparadas con la población' });
    expect(t.monogenic_risk).toEqual({ figure: '1.500', caption: 'variantes revisadas contra ClinVar' });
    expect(JSON.stringify(t)).not.toMatch(/AGRN|Pathogenic/);
  });

  it('gives nothing for missing data', () => {
    expect(helixTeasers(null)).toEqual({});
    expect(helixTeasers({ modules: { traits: 'x' } })).toEqual({});
  });
});
