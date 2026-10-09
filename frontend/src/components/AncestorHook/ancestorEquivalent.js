const GENERATIONS = { 1: 'tus 2 padres', 2: 'tus 4 abuelos', 3: 'tus 8 bisabuelos', 4: 'tus 16 tatarabuelos' };
const MAX_GENERATION = 8;

// Each generation back halves the expected share, so p ≈ ancestors/2^n. Take the first generation that fills a whole
// ancestor, rounded to halves, then fold even counts back (2 of 32 reads better as 1 of 16).
export const ancestorEquivalent = (proportion) => {
  let generation = 2; // Halves of 2 parents are too coarse (60% would read as 50%); parents only come from folding.
  while (generation < MAX_GENERATION && proportion * 2 ** generation < 1) generation += 1;
  let share = Math.round(proportion * 2 ** generation * 2) / 2;
  while (generation > 1 && share >= 2 && share % 2 === 0) {
    generation -= 1;
    share /= 2;
  }
  const total = 2 ** generation;
  const whole = Math.floor(share);
  const amount = share === 0 ? 'menos de 1' : `${whole || ''}${share % 1 ? '½' : ''}`;
  const who = GENERATIONS[generation] ?? `tus ${total} ancestros de hace ${generation} generaciones`;
  return { generation, total, lit: whole, partial: share % 1 ? 0.5 : 0, phrase: `≈ ${amount} de ${who}` };
};
