// The three questions a pathogenic variant can answer. Which one it lands on is decided by how its gene is
// inherited and how many copies carry the variant; anything uncured stays in "conversar", never in the
// reader's own health. Texts are the product's words, not generated.
export const QUESTIONS = {
  salud: {
    q: '¿Puede afectar mi salud?',
    sub: 'Por su herencia y tus copias, puede expresarse en ti.',
    not: 'No significa que vayas a desarrollar la condición: muchas variantes no se expresan en todas las personas. Tampoco reemplaza un estudio clínico.',
  },
  transmitir: {
    q: '¿Puedo transmitirlo?',
    sub: 'Una copia en un gen recesivo: eres portador.',
    not: 'No significa que tengas ni vayas a tener la condición. Tus hijos solo podrían tenerla si la otra persona es portadora del mismo gen.',
  },
  conversar: {
    q: '¿Qué conviene conversar?',
    sub: 'Herencia aún no curada.',
    not: 'No significa que sea grave ni que sea benigno: significa que preferimos no interpretarlo por ti.',
  },
};

export const MOI_TEXT = { AD: 'Autosómica dominante', AR: 'Autosómica recesiva' };
// What the mode of inheritance means for the reader, in one sentence.
export const MOI_PLAIN = {
  AD: 'Basta una copia alterada para que pueda expresarse.',
  AR: 'Hacen falta las dos copias alteradas para que se exprese.',
};

export const bucket = (v) => {
  if (!v.inheritance) return 'conversar';
  if (v.inheritance === 'AD' || v.zygosity === 'homocigoto') return 'salud';
  return v.inheritance === 'AR' ? 'transmitir' : 'conversar';
};

// Known inheritance first; inside it, two copies before one. Penetrance would come before both, but the
// backend does not deliver it.
export const rank = (v) => (v.inheritance ? 0 : 2) + (v.zygosity === 'homocigoto' ? 0 : 1);

export const consequence = (v, key) => {
  if (key === 'transmitir') return 'Tu salud no cambia por esta variante. Es información útil si planificas tener hijos.';
  if (key === 'conversar') return 'Aún no tenemos curado cómo se hereda este gen, así que no la ubicamos en tu salud ni en la de tus hijos.';
  return v.zygosity === 'homocigoto'
    ? 'Tienes las dos copias alteradas. Esto puede expresarse en tu salud; un especialista puede indicarte qué controles corresponden.'
    : 'Con una copia basta para que este gen aumente el riesgo. Existen controles preventivos específicos; conviene verlos con un especialista.';
};

export const certainty = (stars) => (stars >= 3 ? 'Evidencia bien establecida'
  : stars === 2 ? 'Evidencia moderada' : 'Revisión limitada');

// What ClinVar's review stars stand for, said without the stars.
export const certaintyWhy = (stars) => (stars >= 3 ? 'La revisó un panel de expertos o una guía clínica.'
  : stars === 2 ? 'Varios laboratorios coinciden en la clasificación.'
    : 'La clasificó un solo laboratorio, sin revisión de otros.');

// One row per gene: its variants sorted by rank, genes in the order of their best variant.
export const byGene = (variants) => {
  const genes = new Map();
  [...variants].sort((a, b) => rank(a) - rank(b)).forEach((v) => {
    const key = v.gene || v.variant_id;
    genes.set(key, [...(genes.get(key) ?? []), v]);
  });
  return [...genes.values()];
};

const SIGNIFICANCE = { Pathogenic: 'Patogénica', Likely_pathogenic: 'Probablemente patogénica' };
export const significanceOf = (value) => value?.split('/')
  .map((part) => SIGNIFICANCE[part] ?? part.replaceAll('_', ' ')).join(' / ') ?? '';
