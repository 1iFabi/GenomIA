// Turns the API's gene rows into what a reader asks about: their medications. Every phrase is written
// here by hand, per mechanism and step; nothing is generated, and an unknown phenotype gets no verdict.

// The three scales the phenotypes really live on. `usual` is the expected middle, never a prize.
export const SCALES = {
  metab: { steps: ['Lento', 'Intermedio', 'Normal', 'Rápido', 'Ultrarrápido'], usual: 2 },
  func: { steps: ['Baja', 'Disminuida', 'Normal'], usual: 2 },
  sens: { steps: ['Normal', 'Intermedia', 'Alta'], usual: 0 },
};

const PHENOTYPES = {
  'metabolizador lento': ['metab', 0], 'metabolizador pobre': ['metab', 0],
  'metabolizador intermedio': ['metab', 1], 'metabolizador normal': ['metab', 2],
  'metabolizador rápido': ['metab', 3], 'metabolizador ultrarrápido': ['metab', 4],
  'función baja': ['func', 0], 'función disminuida': ['func', 1], 'función normal': ['func', 2],
  'sensibilidad normal': ['sens', 0], 'sensibilidad intermedia': ['sens', 1], 'sensibilidad alta': ['sens', 2],
};

export const placeOf = (phenotype) => {
  const hit = PHENOTYPES[String(phenotype || '').trim().toLowerCase()];
  return hit ? { scale: hit[0], step: hit[1], usual: hit[1] === SCALES[hit[0]].usual } : null;
};

export const GENE_PLAIN = {
  CYP2C19: 'Una enzima del hígado que activa algunos remedios y desarma otros.',
  CYP2D6: 'Una enzima del hígado que convierte la codeína y el tramadol en su forma activa.',
  CYP2C9: 'Una enzima del hígado que desarma la warfarina y antiinflamatorios como el ibuprofeno.',
  SLCO1B1: 'Una puerta del hígado por donde entran las estatinas para hacer su trabajo.',
  VKORC1: 'La proteína sobre la que actúa la warfarina para hacer más lenta la coagulación.',
};
export const genePlain = (gene) => GENE_PLAIN[gene] || 'Un gen que influye en cómo procesas algunos medicamentos.';

// how each medication meets its gene: the body activates it, clears it, or lets it into the liver
const DRUGS = {
  Clopidogrel: { use: 'Evita coágulos', the: 'el', how: 'activate' },
  Omeprazol: { use: 'Acidez', the: 'el', how: 'clear' },
  Sertralina: { use: 'Ánimo y ansiedad', the: 'la', how: 'clear' },
  Codeína: { use: 'Dolor y tos', the: 'la', how: 'activate' },
  Tramadol: { use: 'Dolor', the: 'el', how: 'activate' },
  Tamoxifeno: { use: 'Cáncer de mama', the: 'el', how: 'activate' },
  Warfarina: { use: 'Anticoagulante', the: 'la', how: 'clear' },
  Ibuprofeno: { use: 'Dolor e inflamación', the: 'el', how: 'clear' },
  Simvastatina: { use: 'Colesterol', the: 'la', how: 'enter' },
  Atorvastatina: { use: 'Colesterol', the: 'la', how: 'enter' },
};

const SAYS = {
  activate: [
    (d) => `Tu cuerpo casi no activa ${d}, así que podría hacerte poco efecto.`,
    (d) => `Tu cuerpo activa ${d} más despacio que la mayoría, así que podría hacerte menos efecto.`,
    (d) => `Activas ${d} como la mayoría de las personas.`,
    (d) => `Activas ${d} más rápido que la mayoría, así que su efecto puede ser más fuerte.`,
    (d) => `Activas ${d} mucho más rápido que la mayoría; su efecto puede ser bastante más fuerte.`,
  ],
  clear: [
    (d) => `Eliminas ${d} mucho más despacio que la mayoría: tiende a acumularse en tu cuerpo.`,
    (d) => `Eliminas ${d} más despacio que la mayoría: tiende a quedarse más tiempo en tu cuerpo.`,
    (d) => `Eliminas ${d} como la mayoría de las personas.`,
    (d) => `Eliminas ${d} más rápido que la mayoría, así que podría durarte menos.`,
    (d) => `Eliminas ${d} muy rápido; podría hacerte poco efecto.`,
  ],
  enter: [
    () => 'Casi no entra a tu hígado y queda en la sangre; con dosis altas sube bastante la chance de dolor muscular.',
    () => 'Entra menos a tu hígado y queda más en la sangre; con dosis altas sube la chance de dolor muscular.',
    () => 'Entra a tu hígado como en la mayoría de las personas.',
  ],
};
// Warfarina: two genes, one sentence
const WARFARIN = {
  CYP2C9: ['la eliminas mucho más despacio', 'la eliminas más despacio', 'la eliminas como la mayoría', 'la eliminas más rápido', 'la eliminas mucho más rápido'],
  VKORC1: ['tu cuerpo responde a ella como la mayoría', 'tu cuerpo es algo más sensible a ella', 'tu cuerpo es bastante más sensible a ella'],
};
// the shorter labels on the two lines that meet at the warfarin
export const WARFARIN_SHORT = {
  CYP2C9: WARFARIN.CYP2C9,
  VKORC1: ['respondes como la mayoría', 'eres algo más sensible', 'eres bastante más sensible'],
};

function sayFor(name, genes) {
  const drug = DRUGS[name];
  const placed = genes.map((gene) => ({ gene, place: placeOf(gene.phenotype) }));
  if (placed.some(({ place }) => !place)) {
    return `Tu resultado en ${genes.map((g) => g.gene).join(' y ')} es «${genes.map((g) => g.phenotype).join(' / ')}». Tu médico puede tenerlo en cuenta.`;
  }
  if (name === 'Warfarina' && genes.length > 1) {
    const parts = placed.map(({ gene, place }) => WARFARIN[gene.gene]?.[place.step]).filter(Boolean);
    if (parts.length === genes.length) {
      return placed.every(({ place }) => place.usual)
        ? 'Dos de tus genes la mueven, y ambos funcionan como en la mayoría de las personas.'
        : `Dos de tus genes la mueven: ${parts.join(' y ')}.`;
    }
  }
  const { gene, place } = placed[0];
  const lines = drug && SAYS[drug.how];
  if (lines && lines[place.step] && (drug.how === 'enter') === (place.scale === 'func')) {
    return lines[place.step](`${drug.the} ${name.toLowerCase()}`);
  }
  return place.usual
    ? `Tu ${gene.gene} funciona como en la mayoría de las personas para este medicamento.`
    : `Tu ${gene.gene} es «${gene.phenotype.toLowerCase()}»: puede cambiar cómo te hace efecto.`;
}

// medication -> the genes that decide it, split into what to talk over with a doctor and what is as usual
export function buildMedications(rows) {
  const byName = new Map();
  for (const row of rows || []) {
    for (const name of row.drugs || []) {
      const med = byName.get(name) || { name, genes: [] };
      med.genes.push(row);
      byName.set(name, med);
    }
  }
  const meds = [...byName.values()].map((med) => {
    const places = med.genes.map((g) => placeOf(g.phenotype));
    return {
      ...med,
      use: DRUGS[med.name]?.use || '',
      say: sayFor(med.name, med.genes),
      usual: places.every((place) => place?.usual),
    };
  });
  return { talk: meds.filter((m) => !m.usual), same: meds.filter((m) => m.usual), all: meds };
}

// search ignores accents and case, and also matches what a medication is for
const fold = (s) => s.normalize('NFD').replace(/\p{M}/gu, '').toLowerCase();
export const matches = (med, query) => !query.trim() || fold(med.name).includes(fold(query.trim())) || fold(med.use).includes(fold(query.trim()));
