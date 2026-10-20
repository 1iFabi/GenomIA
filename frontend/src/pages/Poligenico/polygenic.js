// Plain words for the polygenic page. A percentile is the reader's place among 100 people, never a chance.

// What weighs as much as the score or more, per backend condition code; general facts, no advice.
export const ALSO = {
  diabetes_tipo_2: 'El peso, la actividad física, la edad y si tus padres o hermanos la tienen.',
  enfermedad_coronaria: 'La presión, el colesterol, fumar, la edad y si alguien cercano en tu familia la tuvo joven.',
  hipertension: 'La sal, el peso, el alcohol, la edad y la historia de tu familia.',
  cancer_mama: 'La edad, la historia de tu familia y variantes de un solo gen como BRCA1 o BRCA2, que se revisan en Monogénico.',
  alzheimer: 'La edad, la historia de tu familia y la presión y el azúcar a lo largo de la vida.',
};
const ALSO_ANY = 'La historia de tu familia, la edad y tus hábitos.';
export const alsoFor = (condition) => ALSO[condition] ?? ALSO_ANY;

export const CATEGORY_PLAIN = {
  Elevado: 'Más alto que la mayoría',
  Promedio: 'Cerca del promedio',
  Bajo: 'Más bajo que la mayoría',
};

// people out of 100 below the reader, kept between 1 and 99 so it never reads "0" or "100 de cada 100"
export const below = (percentile) => Math.min(99, Math.max(1, Math.round(percentile)));

// Standard normal helpers for drawing the reader's place on the bell.
const erf = (x) => {
  const t = 1 / (1 + 0.3275911 * Math.abs(x));
  const y = 1 - ((((1.061405429 * t - 1.453152027) * t + 1.421413741) * t - 0.284496736) * t + 0.254829592)
    * t * Math.exp(-x * x);
  return x >= 0 ? y : -y;
};
const cdf = (z) => 0.5 * (1 + erf(z / Math.SQRT2));
export const zOf = (percentile) => {
  const q = Math.min(0.995, Math.max(0.005, percentile / 100));
  let lo = -4;
  let hi = 4;
  for (let i = 0; i < 40; i += 1) {
    const mid = (lo + hi) / 2;
    if (cdf(mid) < q) lo = mid; else hi = mid;
  }
  return (lo + hi) / 2;
};
