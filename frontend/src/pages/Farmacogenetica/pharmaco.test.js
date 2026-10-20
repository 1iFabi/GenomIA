import { describe, expect, it } from 'vitest';
import { activityScore, buildTable, matches, placeOf } from './pharmaco';

const rows = [
  { gene: 'CYP2C19', diplotype: '*1/*2', phenotype: 'Metabolizador intermedio' },
  { gene: 'CYP2D6', diplotype: '*1/*1', phenotype: 'Metabolizador normal' },
  { gene: 'CYP2C9', diplotype: '*1/*2', phenotype: 'Metabolizador intermedio' },
  { gene: 'SLCO1B1', diplotype: '*1/*5', phenotype: 'Función disminuida' },
  { gene: 'VKORC1', diplotype: 'G/A', phenotype: 'Sensibilidad intermedia' },
];
const med = (name, list = rows) => buildTable(list).meds.find((m) => m.name === name);

describe('pharmacogenetics table', () => {
  it('places every phenotype on its own scale, with normal as the usual stretch', () => {
    expect(placeOf('Metabolizador intermedio')).toEqual({ scale: 'metab', step: 1, usual: false });
    expect(placeOf('Función disminuida')).toEqual({ scale: 'func', step: 1, usual: false });
    expect(placeOf('Sensibilidad normal')).toEqual({ scale: 'sens', step: 0, usual: true });
    expect(placeOf('Algo nuevo')).toBeNull();
  });

  it('scores CYP2D6 and CYP2C9 diplotypes the CPIC way, a duplication counting twice', () => {
    expect(activityScore('CYP2C9', '*1/*2')).toBe(1.5);
    expect(activityScore('CYP2C9', '*1/*3')).toBe(1);
    expect(activityScore('CYP2D6', '*1/*1xN')).toBe(3);
    expect(activityScore('CYP2D6', '*1/*99')).toBeNull();
  });

  it('gives the simulated profile the CPIC verdicts: 7 to talk over, 8 with a nuance, 20 as usual', () => {
    const { meds, counts, untested } = buildTable(rows);
    expect(meds).toHaveLength(35);
    expect(counts).toMatchObject({ talk: 7, note: 8, same: 20 });
    expect(meds.filter((m) => m.v === 'talk').map((m) => m.name)).toEqual(
      ['Atorvastatina', 'Clopidogrel', 'Fluvastatina', 'Lovastatina', 'Pitavastatina', 'Simvastatina', 'Warfarina']);
    expect(untested.map((m) => m.name)).toContain('Abacavir');
  });

  it('follows the activity score, not only the phenotype word', () => {
    // both are "Metabolizador intermedio", but *1/*3 scores 1 and asks for the lowest NSAID dose
    expect(med('Ibuprofeno').v).toBe('same');
    expect(med('Ibuprofeno', [{ gene: 'CYP2C9', diplotype: '*1/*3', phenotype: 'Metabolizador intermedio' }]).v).toBe('note');
    expect(med('Piroxicam', [{ gene: 'CYP2C9', diplotype: '*1/*3', phenotype: 'Metabolizador intermedio' }]).v).toBe('talk');
    const fast = [{ gene: 'CYP2D6', diplotype: '*1/*1xN', phenotype: 'Metabolizador ultrarrápido' }];
    expect(med('Codeína', fast).v).toBe('talk');
    expect(med('Tamoxifeno', fast).v).toBe('same');
  });

  it('writes the sentence and the guideline for both genes of the warfarin', () => {
    const warfarin = med('Warfarina');
    expect(warfarin.say).toBe('Dos de tus genes la mueven: la eliminas más despacio y tu cuerpo es algo más sensible a ella. Tu dosis puede calcularse con tus genes.');
    expect(warfarin.cpic).toContain('CYP2C9 y VKORC1');
    expect(warfarin.missing).toContain('CYP4F2');
  });

  it('never gives a verdict it cannot back: a missing gene or an unplaced phenotype says so', () => {
    const onlyC9 = [{ gene: 'CYP2C9', diplotype: '*1/*1', phenotype: 'Metabolizador normal' }];
    expect(med('Warfarina', onlyC9)).toMatchObject({ v: 'miss', cpic: null });
    expect(med('Warfarina', onlyC9).say).toContain('VKORC1');
    const odd = [{ gene: 'SLCO1B1', diplotype: '*1/*14', phenotype: 'Función aumentada' }];
    expect(med('Simvastatina', odd)).toMatchObject({ v: 'unknown', cpic: null });
    expect(med('Simvastatina', odd).say).toBe('Tu resultado en SLCO1B1 es «Función aumentada». Tu médico puede tenerlo en cuenta.');
  });

  it('finds a medication by name or use, ignoring accents', () => {
    const codeine = med('Codeína');
    expect(matches(codeine, 'codeina')).toBe(true);
    expect(matches(codeine, 'tos')).toBe(true);
    expect(matches(med('Omeprazol'), 'LOSEC')).toBe(false);
    expect(matches(codeine, 'colesterol')).toBe(false);
  });

  it('shows a gene it has no rule for yet, never as "not analyzed" and never with a verdict', () => {
    const cftr = { gene: 'CFTR', diplotype: 'G551D/F508del', phenotype: 'Variante de respuesta' };
    const ivacaftor = med('Ivacaftor', [...rows, cftr]);
    expect(ivacaftor).toMatchObject({ v: 'unknown', cpic: null, use: 'Fibrosis quística' });
    expect(ivacaftor.say).toBe('Tu resultado en CFTR es «Variante de respuesta». Tu médico puede tenerlo en cuenta.');
    expect(buildTable(rows).untested.map((m) => m.name)).toContain('Ivacaftor');
    expect(buildTable(rows).untested.find((m) => m.name === 'Carbamazepina').gene).toBe('HLA-A y HLA-B');
  });

  it('reads a companion gene when the exam has it, and drops its "not analyzed" note', () => {
    const gene = (g, phenotype, diplotype = '') => ({ gene: g, diplotype, phenotype });
    expect(med('Rosuvastatina').missing).toContain('ABCG2');
    const rosuva = med('Rosuvastatina', [...rows, gene('ABCG2', 'Función baja', 'A/A')]);
    expect(rosuva).toMatchObject({ v: 'talk', missing: null });
    expect(rosuva.genes.map((g) => g.gene)).toEqual(['SLCO1B1', 'ABCG2']);
    expect(med('Rosuvastatina', [...rows, gene('ABCG2', 'Función disminuida', 'C/A')]).v).toBe(med('Rosuvastatina').v);
    const normal = [gene('CYP2C9', 'Metabolizador normal', '*1/*1'), gene('VKORC1', 'Sensibilidad normal', 'G/G')];
    expect(med('Warfarina', normal).v).toBe('same');
    expect(med('Warfarina', [...normal, gene('CYP4F2', 'Función disminuida', '*1/*3')]).v).toBe('note');
    expect(med('Warfarina', [...normal, gene('CYP4F2', 'Indeterminado')]).v).toBe('unknown');
    const c19 = gene('CYP2C19', 'Metabolizador normal', '*1/*1');
    expect(med('Sertralina', [c19]).v).toBe('same');
    expect(med('Sertralina', [c19, gene('CYP2B6', 'Metabolizador lento', '*6/*6')]).v).toBe('talk');
  });

  it('reads CYP3A5, CYP2B6, UGT1A1, G6PD, RYR1 with CACNA1S and MT-RNR1 the CPIC way', () => {
    const gene = (g, phenotype) => ({ gene: g, diplotype: '', phenotype });
    expect(med('Tacrolimus', [gene('CYP3A5', 'Metabolizador lento')]).v).toBe('same');
    expect(med('Tacrolimus', [gene('CYP3A5', 'Metabolizador intermedio')]).say).toContain('dosis más alta');
    expect(placeOf('Metabolizador lento', 'CYP3A5').usual).toBe(true);
    expect(placeOf('Metabolizador lento', 'CYP2C19').usual).toBe(false);
    expect(med('Efavirenz', [gene('CYP2B6', 'Metabolizador intermedio')]).v).toBe('talk');
    expect(med('Efavirenz', [gene('CYP2B6', 'Metabolizador normal')]).v).toBe('same');
    expect(med('Atazanavir', [gene('UGT1A1', 'Metabolizador lento')]).say).toContain('amarillos');
    expect(med('Atazanavir', [gene('UGT1A1', 'Metabolizador intermedio')]).v).toBe('same');

    expect(med('Rasburicasa', [gene('G6PD', 'Deficiente')]).say).toContain('no usarlo');
    expect(med('Primaquina', [gene('G6PD', 'Deficiencia variable')]).say).toContain('medir la actividad');
    expect(med('Dapsona', [gene('G6PD', 'Actividad normal')]).v).toBe('same');
    expect(med('Nitrofurantoína', [gene('G6PD', 'Raro')]).v).toBe('unknown');

    const none = [gene('RYR1', 'Sin variante asociada'), gene('CACNA1S', 'Sin variante asociada')];
    expect(med('Sevoflurano', none).v).toBe('same');
    expect(med('Succinilcolina', [none[0], gene('CACNA1S', 'Susceptible a hipertermia maligna')]).say).toContain('hipertermia maligna');
    expect(med('Isoflurano', [none[0]]).v).toBe('miss');

    expect(med('Gentamicina', [gene('MT-RNR1', 'Riesgo aumentado de sordera')]).say).toContain('audición');
    expect(med('Amikacina', [gene('MT-RNR1', 'Riesgo habitual')]).v).toBe('same');
    expect(buildTable(rows).meds.concat(buildTable(rows).untested).map((m) => m.name)).not.toContain('Hidralazina');
  });

  it('reads DPYD, TPMT with NUDT15, and the HLA alleles the CPIC way', () => {
    const gene = (g, phenotype, diplotype = '') => ({ gene: g, diplotype, phenotype });
    expect(med('Fluorouracilo', [gene('DPYD', 'Metabolizador normal')]).v).toBe('same');
    expect(med('Capecitabina', [gene('DPYD', 'Metabolizador intermedio')]).say).toContain('dosis más baja');
    expect(med('Fluorouracilo', [gene('DPYD', 'Metabolizador lento')]).say).toContain('evitarlo');
    const thio = (tpmt, nudt) => med('Azatioprina', [gene('TPMT', tpmt), gene('NUDT15', nudt)]);
    expect(thio('Metabolizador normal', 'Metabolizador normal').v).toBe('same');
    expect(thio('Metabolizador normal', 'Metabolizador intermedio').say).toContain('dosis más baja');
    expect(thio('Metabolizador lento', 'Metabolizador normal').say).toContain('otro remedio');
    expect(med('Azatioprina', [gene('TPMT', 'Metabolizador normal')]).v).toBe('miss');

    const negative = gene('HLA-B', 'No portador', '*57:01, *58:01 y *15:02 negativos');
    expect(med('Abacavir', [negative]).v).toBe('same');
    expect(med('Abacavir', [gene('HLA-B', 'Portador de HLA-B*57:01', '*57:01 positivo')]).say).toContain('Tienes HLA-B*57:01');
    expect(med('Alopurinol', [gene('HLA-B', 'Portador de HLA-B*58:01', '*58:01 positivo')]).v).toBe('talk');
    // a carrier of another allele says nothing about *15:02: no verdict rather than a guess
    expect(med('Oxcarbazepina', [gene('HLA-B', 'Portador de HLA-B*58:01', '*58:01 positivo')]).v).toBe('unknown');
    const hlaA = gene('HLA-A', 'Portador de HLA-A*31:01', '*31:01 positivo');
    expect(med('Carbamazepina', [negative, hlaA]).say).toContain('Tienes HLA-A*31:01');
    expect(med('Carbamazepina', [negative, gene('HLA-A', 'No portador', '*31:01 negativo')]).v).toBe('same');

    // phenytoin: HLA-B*15:02 overrides CYP2C9; without it CYP2C9 decides and HLA-B adds no caveat
    const b1502 = gene('HLA-B', 'Portador de HLA-B*15:02', '*15:02 positivo');
    expect(med('Fenitoína', [...rows, b1502]).say).toContain('Tienes HLA-B*15:02');
    const plain = med('Fenitoína', [...rows, negative]);
    expect(plain).toMatchObject({ v: 'same', missing: null });
    expect(plain.genes.map((g) => g.gene)).toEqual(['CYP2C9', 'HLA-B']);
    expect(med('Fenitoína').missing).toContain('Tu examen no lo analiza');
  });
});
