// Turns the API's gene rows into the reader's medication table. Every verdict follows the CPIC recommendation
// for that phenotype (api.cpicpgx.org, read 2026-10-19), written here by hand in plain Spanish; nothing is
// generated, and a phenotype we cannot place gets no verdict.

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

// where most people sit when it is not the scale's middle: most people do not express CYP3A5
const USUAL_STEP = { CYP3A5: 0 };
export const usualStep = (gene, scale) => USUAL_STEP[gene] ?? SCALES[scale].usual;

export const placeOf = (phenotype, gene) => {
  const hit = PHENOTYPES[String(phenotype || '').trim().toLowerCase()];
  return hit ? { scale: hit[0], step: hit[1], usual: hit[1] === usualStep(gene, hit[0]) } : null;
};

export const GENE_PLAIN = {
  CYP2C19: 'Una enzima del hígado que activa algunos remedios y desarma otros.',
  CYP2D6: 'Una enzima del hígado que activa algunos analgésicos y desarma varios antidepresivos.',
  CYP2C9: 'Una enzima del hígado que desarma la warfarina y antiinflamatorios como el ibuprofeno.',
  SLCO1B1: 'Una puerta del hígado por donde entran las estatinas para hacer su trabajo.',
  VKORC1: 'La proteína sobre la que actúa la warfarina para hacer más lenta la coagulación.',
  CYP2B6: 'Una enzima del hígado que desarma el efavirenz y algunos antidepresivos.',
  CYP3A5: 'Una enzima del hígado que desarma el tacrolimus, un remedio para trasplantes.',
  CYP4F2: 'Una enzima que recicla la vitamina K; influye en cuánta warfarina necesitas.',
  DPYD: 'La enzima que desarma el fluorouracilo y la capecitabina, remedios para el cáncer.',
  TPMT: 'Una enzima que desarma la azatioprina y otros remedios parecidos.',
  NUDT15: 'Una enzima que, junto a TPMT, desarma la azatioprina y otros remedios parecidos.',
  UGT1A1: 'Una enzima del hígado que elimina la bilirrubina y algunos remedios, como el atazanavir.',
  G6PD: 'Una enzima que protege a los glóbulos rojos; si falta, algunos remedios pueden dañarlos.',
  'HLA-B': 'Parte de tu sistema de defensas; algunas de sus variantes causan reacciones graves a ciertos remedios.',
  'HLA-A': 'Parte de tu sistema de defensas; una de sus variantes causa reacciones graves a la carbamazepina.',
  RYR1: 'Un canal del músculo; algunas variantes reaccionan mal a ciertos anestésicos.',
  CACNA1S: 'Un canal del músculo que trabaja con RYR1; algunas variantes reaccionan mal a ciertos anestésicos.',
  'MT-RNR1': 'Un gen de las mitocondrias; una variante hace al oído sensible a algunos antibióticos.',
  ABCG2: 'Una bomba que saca la rosuvastatina de las células del intestino y del hígado.',
};
export const genePlain = (gene) => GENE_PLAIN[gene] || 'Un gen que influye en cómo procesas algunos medicamentos.';

// what the guideline asks of this profile: talk = another dose or drug, note = usual start with a later
// adjustment, same = usual dose; miss = a gene it needs is not in the exam, unknown = a phenotype we cannot place
export const VERDICTS = {
  talk: 'Conversar con tu médico',
  note: 'Habitual, con un matiz',
  same: 'Como la mayoría',
  unknown: 'Sin interpretación',
  miss: 'No lo analizamos',
};
export const ORDER = ['talk', 'note', 'same', 'unknown', 'miss'];

const LEVELS = { metab: ['PM', 'IM', 'NM', 'RM', 'UM'], func: ['poor', 'dec', 'normal'], sens: ['normal', 'int', 'high'] };

// CPIC allele function values; a duplication (xN) counts its allele twice
const ALLELE_VALUE = {
  CYP2C9: { '*1': 1, '*2': 0.5, '*3': 0, '*5': 0, '*6': 0, '*8': 0.5, '*11': 0.5 },
  CYP2D6: { '*1': 1, '*2': 1, '*35': 1, '*3': 0, '*4': 0, '*5': 0, '*6': 0, '*9': 0.5, '*10': 0.25, '*17': 0.5, '*29': 0.5, '*41': 0.5 },
};
// without a readable diplotype the score comes from the phenotype; IM takes the lower score, the safer reading
const SCORE_OF_LEVEL = { PM: 0, IM: 1, NM: 2, RM: 2, UM: 3 };

export function activityScore(gene, diplotype) {
  const values = ALLELE_VALUE[gene];
  const alleles = String(diplotype || '').split('/');
  if (!values || alleles.length !== 2) return null;
  let total = 0;
  for (const allele of alleles) {
    const [, star, dup] = allele.trim().match(/^(\*\d+)(x\d+|xN)?$/) || [];
    if (!Object.hasOwn(values, star || '')) return null;
    total += values[star] * (!dup ? 1 : dup === 'xN' ? 2 : Number(dup.slice(1)));
  }
  return total;
}

const TYPED = new Set(['HLA-A', 'HLA-B', 'G6PD', 'RYR1', 'CACNA1S', 'MT-RNR1']);

// a gene row read the way the guideline tables are keyed: a level, and for CYP2D6/CYP2C9 an activity score
function readGene(row) {
  // typed genes have no speed scale: their rules read the result itself and return null when they cannot
  if (TYPED.has(row.gene)) return { row, level: 'typed', score: null };
  const place = placeOf(row.phenotype);
  if (!place) return { row, level: null, score: null };
  const level = LEVELS[place.scale][place.step];
  if (!ALLELE_VALUE[row.gene]) return { row, level, score: null };
  const score = activityScore(row.gene, row.diplotype) ?? SCORE_OF_LEVEL[level];
  // CYP2D6 phenotype bands by score (CPIC 2019 consensus)
  const d6 = row.gene === 'CYP2D6' && (score === 0 ? 'PM' : score <= 1 ? 'IM' : score <= 2.25 ? 'NM' : 'UM');
  return { row, level: d6 || level, score };
}

// --- the guideline, drug family by drug family ---
const byLevel = (gene, table) => (g) => table[g[gene].level] || table[g[gene].level === 'RM' ? 'NM' : ''];
const SAME = (say, cpic = 'Dosis inicial habitual.') => ['same', say, cpic];

const PPI = byLevel('CYP2C19', {
  PM: ['note', 'Lo eliminas mucho más despacio, así que te hace efecto de sobra. Si lo tomas por más de 3 meses, tu médico podría bajar la dosis a la mitad.', 'Dosis inicial habitual. En uso de más de 12 semanas con buen efecto, considerar bajarla 50 %.'],
  IM: ['note', 'Lo eliminas más despacio, así que te hace efecto de sobra. Si lo tomas por más de 3 meses, tu médico podría bajar la dosis a la mitad.', 'Dosis inicial habitual. En uso de más de 12 semanas con buen efecto, considerar bajarla 50 %.'],
  NM: SAME('Lo eliminas como la mayoría de las personas.', 'Dosis inicial habitual. Para H. pylori o esofagitis erosiva, considerar subirla 50–100 %.'),
  RM: SAME('Lo eliminas algo más rápido, pero la guía indica la dosis habitual.', 'Dosis inicial habitual. Para H. pylori o esofagitis erosiva, considerar subirla 50–100 %.'),
  UM: ['talk', 'Lo eliminas muy rápido y podría hacerte poco efecto. La guía sugiere partir con el doble de dosis.', 'Subir la dosis inicial 100 %, en tomas divididas; vigilar el efecto.'],
});
const SSRI_SLOW = ['note', 'La eliminas más despacio que la mayoría. Se parte con la dosis habitual, pero puede bastarte subirla más lento y quedarte en una dosis menor.', 'Dosis inicial habitual; considerar subirla más lento y una dosis de mantención menor.'];
const CITALOPRAM = byLevel('CYP2C19', {
  PM: ['talk', 'La eliminas mucho más despacio y se acumula. La guía sugiere otro antidepresivo o, si se usa, la mitad de la dosis.', 'Considerar un antidepresivo no metabolizado por CYP2C19. Si se usa: dosis inicial menor, subirla más lento y mantención 50 % menor.'],
  IM: SSRI_SLOW,
  NM: SAME('La eliminas como la mayoría de las personas.'),
  RM: ['note', 'La eliminas algo más rápido. Se parte con la dosis habitual; si no te hace efecto, tu médico podría subirla o cambiarla.', 'Dosis inicial habitual; si la respuesta es insuficiente, subir la mantención o cambiar de antidepresivo.'],
  UM: ['talk', 'La eliminas muy rápido y podría hacerte poco efecto. La guía sugiere otro antidepresivo.', 'Considerar un antidepresivo no metabolizado por CYP2C19; si se usa y no alcanza efecto, subir la dosis.'],
});
const SERTRALINE = byLevel('CYP2C19', {
  PM: ['talk', 'La eliminas mucho más despacio. La guía sugiere partir con una dosis más baja.', 'Considerar dosis inicial 50 % menor y subirla más lento, o un antidepresivo no metabolizado por CYP2C19.'],
  IM: SSRI_SLOW,
  NM: SAME('La eliminas como la mayoría de las personas.'),
  RM: SAME('La eliminas algo más rápido, pero la guía indica la dosis habitual.'),
  UM: ['note', 'La eliminas muy rápido. Se parte con la dosis habitual; si no te hace efecto, tu médico podría cambiarla.', 'Dosis inicial habitual; si no hay respuesta, considerar otro antidepresivo.'],
});
const sertraline = (g) => {
  const base = SERTRALINE(g);
  if (!g.CYP2B6 || !base) return base;
  const b6 = g.CYP2B6.level;
  if (!b6) return null;
  if (b6 === 'PM' && base[0] !== 'talk') return ['talk', 'Tu CYP2B6 la elimina más despacio. La guía sugiere partir con una dosis más baja.', 'CYP2B6 lento: considerar dosis inicial menor y subirla más lento.'];
  return base;
};
const CLOPIDOGREL = byLevel('CYP2C19', {
  PM: ['talk', 'Tu cuerpo casi no lo activa, así que podría no protegerte de los coágulos. La guía sugiere otro remedio parecido.', 'Evitar clopidogrel; usar prasugrel o ticagrelor si no hay contraindicación.'],
  IM: ['talk', 'Tu cuerpo lo activa más despacio, así que podría protegerte menos de los coágulos. Tu médico podría preferir otro remedio parecido.', 'Tras un infarto o una angioplastía: evitar la dosis estándar si es posible y usar prasugrel o ticagrelor. En otros usos vasculares, considerar una alternativa.'],
  NM: SAME('Lo activas como la mayoría de las personas.', 'Dosis habitual (75 mg al día).'),
  RM: SAME('Lo activas algo más rápido; la guía indica la dosis habitual.', 'Dosis habitual (75 mg al día).'),
  UM: SAME('Lo activas más rápido; la guía indica la dosis habitual.', 'Dosis habitual (75 mg al día).'),
});
const VORICONAZOLE = byLevel('CYP2C19', {
  PM: ['talk', 'Lo eliminas mucho más despacio y se acumula. La guía sugiere otro antifúngico.', 'Preferir un antifúngico que no dependa de CYP2C19 (isavuconazol, anfotericina B liposomal o posaconazol). Si se usa, dosis menor y control de niveles.'],
  IM: SAME('Lo eliminas algo más despacio, pero la guía indica la dosis habitual.', 'Dosis habitual.'),
  NM: SAME('Lo eliminas como la mayoría de las personas.', 'Dosis habitual.'),
  RM: ['talk', 'Lo eliminas tan rápido que podría no alcanzar a hacer efecto. La guía sugiere otro antifúngico.', 'Preferir isavuconazol, anfotericina B liposomal o posaconazol.'],
  UM: ['talk', 'Lo eliminas tan rápido que podría no alcanzar a hacer efecto. La guía sugiere otro antifúngico.', 'Preferir isavuconazol, anfotericina B liposomal o posaconazol.'],
});

const opioid = (it, name, other) => byLevel('CYP2D6', {
  PM: ['talk', `Tu cuerpo casi no ${it} activa, así que podría no quitarte el dolor. La guía sugiere otro analgésico.`, `Evitar ${name}. Si se necesita un opioide, uno que no sea ${other}.`],
  IM: ['note', `${it === 'la' ? 'La' : 'Lo'} activas más despacio que la mayoría. Se usa la dosis habitual; si no te quita el dolor, tu médico podría cambiar${it}.`, `Dosis habitual según edad o peso; si no hay respuesta, un opioide que no sea ${other}.`],
  NM: SAME(`${it === 'la' ? 'La' : 'Lo'} activas como la mayoría de las personas.`, 'Dosis habitual según edad o peso.'),
  UM: ['talk', `${it === 'la' ? 'La' : 'Lo'} activas muy rápido y su efecto puede ser fuerte y peligroso. La guía sugiere otro analgésico.`, `Evitar ${name} por riesgo de toxicidad. Si se necesita un opioide, uno que no sea ${other}.`],
});
const TAMOXIFEN = byLevel('CYP2D6', {
  PM: ['talk', 'Tu cuerpo casi no lo activa, así que podría protegerte menos. La guía sugiere otra terapia hormonal.', 'Preferir otra terapia hormonal, como un inhibidor de aromatasa (con supresión ovárica en premenopausia).'],
  IM: ['talk', 'Lo activas más despacio, así que podría protegerte menos. La guía sugiere considerar otra terapia hormonal.', 'Considerar un inhibidor de aromatasa; si se usa tamoxifeno, evitar inhibidores de CYP2D6.'],
  NM: SAME('Lo activas como la mayoría. Conviene evitar remedios que frenan CYP2D6, como algunos antidepresivos.', 'Dosis estándar (20 mg al día); evitar inhibidores moderados o fuertes de CYP2D6.'),
  UM: SAME('Lo activas más rápido, y la guía indica la dosis habitual. Conviene evitar remedios que frenan CYP2D6.', 'Dosis estándar (20 mg al día); evitar inhibidores moderados o fuertes de CYP2D6.'),
});
const D6_FAST_ALT = (what) => ['talk', `${what} muy rápido y podría hacerte poco efecto. La guía sugiere otro antidepresivo.`, 'Elegir un antidepresivo no metabolizado principalmente por CYP2D6.'];
const PAROXETINE = byLevel('CYP2D6', {
  PM: ['talk', 'La eliminas mucho más despacio y se acumula. La guía sugiere la mitad de la dosis.', 'Dosis inicial 50 % menor, subirla más lento y mantención 50 % menor.'],
  IM: ['talk', 'La eliminas más despacio. La guía sugiere partir con una dosis más baja y subirla más lento.', 'Considerar dosis inicial menor y subirla más lento.'],
  NM: SAME('La eliminas como la mayoría de las personas.'),
  UM: D6_FAST_ALT('La eliminas'),
});
const VORTIOXETINE = byLevel('CYP2D6', {
  PM: ['talk', 'La eliminas mucho más despacio. La guía sugiere la mitad de la dosis inicial.', 'Partir con 50 % de la dosis (5 mg) y subir hasta 10 mg como máximo, o elegir otro antidepresivo.'],
  IM: SAME('La eliminas algo más despacio, pero la guía indica la dosis habitual.'),
  NM: SAME('La eliminas como la mayoría de las personas.'),
  UM: D6_FAST_ALT('La eliminas'),
});
const NORTRIPTYLINE = byLevel('CYP2D6', {
  PM: ['talk', 'La eliminas mucho más despacio y puede darte más efectos adversos. La guía sugiere otro remedio o la mitad de la dosis.', 'Evitar tricíclicos; si se usa, dosis inicial 50 % menor con control de niveles.'],
  IM: ['talk', 'La eliminas más despacio. La guía sugiere partir con una dosis algo menor.', 'Considerar dosis inicial 25 % menor; ajustar con control de niveles.'],
  NM: SAME('La eliminas como la mayoría de las personas.'),
  UM: ['talk', 'La eliminas muy rápido y podría hacerte poco efecto. La guía sugiere otro remedio.', 'Evitar tricíclicos; si se usa, apuntar a una dosis mayor con control de niveles.'],
});
const antiemetic = (g) => (g.CYP2D6.level === 'UM'
  ? ['talk', 'Lo eliminas tan rápido que podría no quitarte las náuseas. La guía sugiere otro antiemético.', 'Elegir un antiemético no metabolizado por CYP2D6 (por ejemplo, granisetrón).']
  : SAME(g.CYP2D6.level === 'NM' ? 'Lo eliminas como la mayoría de las personas.' : 'Lo eliminas más despacio, pero la guía indica la dosis habitual.', 'Dosis habitual.'));
const atomoxetine = (g) => (g.CYP2D6.score <= 0.5
  ? ['note', 'La eliminas mucho más despacio. Se parte con la dosis habitual, pero se sube más lento.', 'En adultos: partir con 40 mg al día y subir a 80 mg solo si a las 2 semanas no hay respuesta; considerar medir niveles.']
  : SAME(g.CYP2D6.level === 'UM' ? 'La eliminas más rápido, pero la guía indica la dosis habitual.' : 'La eliminas como la mayoría de las personas.', 'En adultos: partir con 40 mg al día y subir a 80 mg a los 3 días.'));
function amitriptyline(g) {
  const d6 = g.CYP2D6.level, c19 = g.CYP2C19.level;
  if (d6 === 'PM') return ['talk', 'La eliminas mucho más despacio y puede darte más efectos adversos. La guía sugiere otro remedio.', 'Evitar amitriptilina; si se usa, dosis inicial 50 % menor con control de niveles.'];
  if (d6 === 'UM') return ['talk', 'La eliminas muy rápido y podría hacerte poco efecto. La guía sugiere otro remedio.', 'Evitar amitriptilina; si se usa, ajustar con control de niveles.'];
  if (c19 === 'PM') return ['talk', 'Uno de tus genes la elimina mucho más despacio. La guía sugiere otro remedio o la mitad de la dosis.', 'Evitar amitriptilina; si se usa, dosis inicial 50 % menor con control de niveles.'];
  if (c19 === 'RM' || c19 === 'UM') return ['talk', 'Uno de tus genes la transforma muy rápido. La guía sugiere otro remedio.', 'Considerar un remedio no metabolizado por CYP2C19; si se usa, control de niveles.'];
  if (d6 === 'IM') return ['talk', 'La eliminas algo más despacio. La guía sugiere partir con una dosis un poco menor.', 'Considerar dosis inicial 25 % menor; control de niveles.'];
  return SAME('Dos de tus genes la mueven y, juntos, dan la dosis habitual.');
}

// NSAIDs and phenytoin read CYP2C9 by activity score: 2 and 1.5 keep the usual dose
const C9_USUAL = (s) => (s === 2 ? 'Lo eliminas como la mayoría de las personas.' : 'Lo eliminas un poco más despacio, pero la guía indica la dosis habitual.');
const NSAID_CPIC = 'Dosis inicial habitual. Como para todos: la menor dosis eficaz por el menor tiempo.';
const NSAID_ALT = ['talk', 'Lo eliminas mucho más despacio y dura mucho en tu cuerpo. La guía sugiere otro antiinflamatorio.', 'Elegir un antiinflamatorio no metabolizado por CYP2C9 o uno de vida media corta.'];
const nsaid = (g) => {
  const s = g.CYP2C9.score;
  if (s >= 1.5) return SAME(C9_USUAL(s), NSAID_CPIC);
  if (s >= 1) return ['note', 'Lo eliminas más despacio. Se parte con la dosis más baja y se sube con cuidado.', 'Partir con la dosis más baja recomendada; subir con precaución.'];
  return ['talk', 'Lo eliminas mucho más despacio y puede acumularse. La guía sugiere una dosis bastante menor.', 'Partir con 25–50 % de la dosis más baja; máximo 25–50 % de la dosis máxima.'];
};
const meloxicam = (g) => {
  const s = g.CYP2C9.score;
  if (s >= 1.5) return SAME(C9_USUAL(s), NSAID_CPIC);
  if (s >= 1) return ['talk', 'Lo eliminas más despacio y dura más en tu cuerpo. La guía sugiere la mitad de la dosis.', 'Partir con 50 % de la dosis más baja; máximo 50 % de la dosis máxima.'];
  return NSAID_ALT;
};
const oxicam = (g) => (g.CYP2C9.score >= 1.5 ? SAME(C9_USUAL(g.CYP2C9.score), NSAID_CPIC) : NSAID_ALT);
const phenytoin = (g) => {
  const s = g.CYP2C9.score;
  if (s >= 1.5) return SAME(C9_USUAL(s).replace('Lo', 'La'), 'Sin ajuste de dosis; seguir con controles de niveles en sangre.');
  return ['talk', 'La eliminas más despacio y puede acumularse. La guía sugiere una dosis de mantención menor.',
    `Dosis de carga habitual; mantención ${s >= 1 ? '25' : '50'} % menor, con control de niveles.`];
};
// DPYD (CPIC 2017, 2024 update): the reader's level decides the fluoropyrimidine
const FLUORO = byLevel('DPYD', {
  PM: ['talk', 'Tu cuerpo casi no desarma este remedio y puede acumularse hasta ser tóxico. La guía sugiere evitarlo.', 'Evitar fluoropirimidinas; si no hay alternativa, dosis muy reducida con control de niveles.'],
  IM: ['talk', 'Desarmas este remedio más despacio y puede acumularse. La guía sugiere partir con una dosis más baja.', 'Reducir la dosis inicial en 50 % y ajustar según tolerancia.'],
  NM: SAME('Desarmas este remedio como la mayoría de las personas.'),
});

// TPMT and NUDT15 (CPIC 2018): the slower of the two decides
const thiopurine = (g) => {
  const levels = [g.TPMT.level, g.NUDT15.level];
  if (levels.includes('PM')) return ['talk', 'Tu cuerpo casi no desarma este remedio y puede bajar mucho tus defensas. La guía sugiere otro remedio o una dosis mucho menor.', 'Considerar alternativa; si se usa, reducir drásticamente la dosis y controlar el hemograma.'];
  if (levels.includes('IM')) return ['talk', 'Desarmas este remedio más despacio y puede bajar tus defensas. La guía sugiere partir con una dosis más baja.', 'Iniciar con 30–80 % de la dosis habitual y ajustar según el hemograma.'];
  return levels.every((level) => level === 'NM') ? SAME('Desarmas este remedio como la mayoría de las personas.') : null;
};

// HLA (CPIC abacavir, allopurinol, carbamazepine/oxcarbazepine, phenytoin): carried, not carried, or unclear (null)
export const carries = (row, allele) => {
  if (row.phenotype?.includes(`Portador de ${row.gene}${allele}`) || row.diplotype?.includes(`${allele} positivo`)) return true;
  return row.phenotype?.trim().toLowerCase() === 'no portador' ? false : null;
};
const SKIN = 'reacciones graves en la piel';
const HLA_AVOID = (name, risk) => ['talk', `Tienes ${name}, que con este remedio se asocia a ${risk}. La guía sugiere no usarlo.`, `${name} positivo: evitar.`];
const hla = (gene, allele, risk) => (g) => {
  const carried = carries(g[gene].row, allele);
  if (carried === null) return null;
  return carried ? HLA_AVOID(gene + allele, risk) : SAME(`No tienes ${gene}${allele}, la variante que con este remedio se asocia a ${risk}.`, 'Uso habitual.');
};
const carbamazepine = (g) => {
  const b = carries(g['HLA-B'].row, '*15:02'), a = carries(g['HLA-A'].row, '*31:01');
  if (b || a) return HLA_AVOID(b ? 'HLA-B*15:02' : 'HLA-A*31:01', SKIN);
  return b === false && a === false
    ? SAME(`No tienes HLA-B*15:02 ni HLA-A*31:01, las variantes que con este remedio se asocian a ${SKIN}.`, 'Uso habitual.') : null;
};
// phenytoin reads HLA-B when the exam has it: a carrier avoids it, otherwise CYP2C9 decides
const phenytoinHla = (g) => {
  if (!g['HLA-B']) return phenytoin(g);
  const carried = carries(g['HLA-B'].row, '*15:02');
  if (carried === null) return null;
  return carried ? HLA_AVOID('HLA-B*15:02', SKIN) : phenytoin(g);
};

// CYP3A5 (CPIC 2015): expressers clear tacrolimus faster
const TACROLIMUS = byLevel('CYP3A5', {
  PM: SAME('Lo desarmas como la mayoría de las personas.'),
  IM: ['talk', 'Lo desarmas más rápido que la mayoría y podría hacerte menos efecto. La guía sugiere partir con una dosis más alta y medir sus niveles.', 'Dosis inicial 1,5 a 2 veces la habitual (máximo 0,3 mg/kg/día), con control de niveles.'],
  NM: ['talk', 'Lo desarmas bastante más rápido que la mayoría y podría hacerte menos efecto. La guía sugiere partir con una dosis más alta y medir sus niveles.', 'Dosis inicial 1,5 a 2 veces la habitual (máximo 0,3 mg/kg/día), con control de niveles.'],
});

// CYP2B6 (CPIC 2019): slower clearance asks for a lower efavirenz dose
const EFAVIRENZ = byLevel('CYP2B6', {
  PM: ['talk', 'Lo eliminas mucho más despacio y se acumula, lo que sube la chance de efectos en el ánimo y el sueño. La guía sugiere una dosis más baja.', 'Considerar 400 o 200 mg al día.'],
  IM: ['talk', 'Lo eliminas más despacio y puede acumularse. La guía sugiere considerar una dosis más baja.', 'Considerar 400 mg al día.'],
  NM: SAME('Lo eliminas como la mayoría de las personas.'),
  UM: SAME('Lo eliminas más rápido, pero la guía indica la dosis habitual.'),
});

// UGT1A1 (CPIC 2015): two *28 copies make jaundice likely, harmless but a common reason to stop
const ATAZANAVIR = byLevel('UGT1A1', {
  PM: ['talk', 'Es probable que te ponga la piel y los ojos amarillos. No es peligroso, pero muchas personas lo dejan por eso. La guía sugiere considerar otro remedio.', 'Alta probabilidad de ictericia: considerar alternativa.'],
  IM: SAME('Lo procesas casi como la mayoría; la chance de piel amarilla es baja.'),
  NM: SAME('Lo procesas como la mayoría de las personas.'),
});

// G6PD (CPIC 2022): a deficient reader risks red blood cell damage
const g6pd = (row) => {
  const text = row.phenotype?.trim().toLowerCase() ?? '';
  if (text === 'actividad normal' || text === 'normal') return 'normal';
  if (text === 'deficiente') return 'def';
  return text.includes('variable') ? 'var' : null;
};
const G6PD_VAR = ['talk', 'Tu resultado de G6PD no es concluyente. La guía sugiere medir la actividad de la enzima antes de usarlo.', 'Medir la actividad de G6PD antes de indicar.'];
const byG6pd = (def, same) => (g) => {
  const level = g6pd(g.G6PD.row);
  if (!level) return null;
  return level === 'normal' ? SAME(same, 'Uso habitual.') : level === 'var' ? G6PD_VAR : def;
};
const RASBURICASE = byG6pd(['talk', 'Te falta la enzima que protege a tus glóbulos rojos, y este remedio puede romperlos. La guía indica no usarlo.', 'Contraindicada en deficiencia de G6PD.'], 'Tu enzima G6PD funciona como en la mayoría; no hay riesgo especial con este remedio.');
const G6PD_CAUTION = ['talk', 'Te falta la enzima que protege a tus glóbulos rojos, y este remedio puede dañarlos. La guía sugiere evitarlo o usarlo con vigilancia.', 'Deficiencia de G6PD: evitar o usar con monitoreo de hemólisis.'];
const G6PD_OK = 'Tu enzima G6PD funciona como en la mayoría; no hay riesgo especial con este remedio.';
const G6PD_DRUG = byG6pd(G6PD_CAUTION, G6PD_OK);

// RYR1 and CACNA1S (CPIC 2018): a susceptible variant makes these anesthetics trigger malignant hyperthermia
const susceptible = (row) => {
  const text = row.phenotype?.trim().toLowerCase() ?? '';
  if (text.includes('susceptible')) return true;
  return text === 'sin variante asociada' ? false : null;
};
const anesthetic = (g) => {
  const r = susceptible(g.RYR1.row), c = susceptible(g.CACNA1S.row);
  if (r || c) return ['talk', 'Tienes una variante que con este anestésico puede causar hipertermia maligna, una reacción grave. La guía indica no usarlo. Conviene avisarlo antes de cualquier cirugía.', 'Susceptibilidad a hipertermia maligna: evitar anestésicos volátiles y succinilcolina.'];
  return r === false && c === false
    ? SAME('No tienes las variantes que con este anestésico causan hipertermia maligna.', 'Uso habitual.') : null;
};

// MT-RNR1 (CPIC 2021): a risk variant makes aminoglycosides damage hearing
const aminoglycoside = (g) => {
  const text = g['MT-RNR1'].row.phenotype?.trim().toLowerCase() ?? '';
  if (text.includes('aumentado')) return ['talk', 'Tienes una variante que con este antibiótico puede dañar tu audición, incluso con una sola dosis. La guía sugiere evitarlo si hay otra opción.', 'Riesgo aumentado de ototoxicidad: evitar aminoglucósidos salvo que no haya alternativa.'];
  return text.includes('habitual') ? SAME('No tienes la variante que con este antibiótico daña la audición.', 'Uso habitual.') : null;
};

const WARFARIN = {
  c9: (s) => (s === 2 ? 'la eliminas como la mayoría' : s >= 1 ? 'la eliminas más despacio' : 'la eliminas mucho más despacio'),
  vk: { normal: 'tu cuerpo responde a ella como la mayoría', int: 'tu cuerpo es algo más sensible a ella', high: 'tu cuerpo es bastante más sensible a ella' },
};
const warfarin = (g) => {
  const cpic = 'Calcular la dosis con un algoritmo que incluye CYP2C9 y VKORC1.';
  const f2 = g.CYP4F2?.level;
  if (g.CYP4F2 && !f2) return null;
  if (g.CYP2C9.score === 2 && g.VKORC1.level === 'normal') {
    return f2 && f2 !== 'normal'
      ? ['note', 'CYP2C9 y VKORC1 funcionan como en la mayoría, pero tu CYP4F2 hace que puedas necesitar algo más de dosis.', 'Algoritmo con CYP2C9 y VKORC1; con CYP4F2*3, aumentar la dosis 5–10 %.']
      : SAME('Tus genes la mueven como en la mayoría de las personas.', cpic);
  }
  return ['talk', `Dos de tus genes la mueven: ${WARFARIN.c9(g.CYP2C9.score)} y ${WARFARIN.vk[g.VKORC1.level]}. Tu dosis puede calcularse con tus genes.`, cpic];
};

const STATIN_SAME = SAME('Entra a tu hígado como en la mayoría de las personas.', 'Dosis habitual según la guía de tu condición.');
const STATIN_ALT = 'Entra menos a tu hígado y queda más en la sangre, lo que sube la chance de dolor muscular. La guía sugiere preferir otra estatina.';
const STATIN_LOW = 'Entra menos a tu hígado y queda más en la sangre. La guía sugiere no partir con dosis altas.';
const STATIN_POOR_LOW = 'Casi no entra a tu hígado y queda en la sangre. La guía sugiere una dosis baja.';
const STATIN_OK = 'Se usa la dosis habitual; tu médico puede estar más atento al dolor muscular si la dosis es alta.';
const statin = (dec, poor) => byLevel('SLCO1B1', { normal: STATIN_SAME, dec, poor });
const SIMVASTATIN = statin(['talk', STATIN_ALT, 'Preferir otra estatina. Si se usa, menos de 20 mg al día.'], ['talk', STATIN_ALT, 'Preferir otra estatina.']);
const LOVASTATIN = statin(['talk', STATIN_ALT, 'Preferir otra estatina. Si se usa, 20 mg o menos al día.'], ['talk', STATIN_ALT, 'Preferir otra estatina.']);
const ATORVASTATIN = statin(['talk', STATIN_LOW, 'Partir con 40 mg o menos al día. Si se necesita más, combinar con otro remedio para el colesterol.'],
  ['talk', STATIN_POOR_LOW, 'Partir con 20 mg o menos al día. Si se necesita más, rosuvastatina o una combinación.']);
const PITAVASTATIN = statin(['talk', STATIN_LOW, 'Partir con 2 mg o menos al día. Si se necesita más, considerar otra estatina o una combinación.'],
  ['talk', STATIN_POOR_LOW, 'Partir con 1 mg al día. Si se necesita más, considerar otra estatina.']);
const PRAVASTATIN = statin(['note', STATIN_OK, 'Dosis habitual; mayor riesgo de dolor muscular sobre 40 mg al día.'], ['talk', STATIN_POOR_LOW, 'Partir con 40 mg o menos al día.']);
const ROSUVASTATIN = statin(['note', STATIN_OK, 'Dosis habitual; mayor riesgo de dolor muscular sobre 20 mg al día.'], ['talk', STATIN_POOR_LOW, 'Partir con 20 mg o menos al día.']);
const rosuvastatin = (g) => {
  const base = ROSUVASTATIN(g);
  if (!g.ABCG2 || !base) return base;
  const abc = g.ABCG2.level;
  if (!abc) return null;
  return abc === 'poor' && base[0] !== 'talk'
    ? ['talk', 'Tu ABCG2 hace que quede más en la sangre. La guía sugiere no partir con dosis altas.', 'ABCG2 función baja: partir con 20 mg o menos al día.'] : base;
};
const fluvastatin = (g) => {
  const s = g.CYP2C9.score, slc = g.SLCO1B1.level;
  if (s === 2) {
    if (slc === 'normal') return STATIN_SAME;
    return slc === 'dec' ? ['note', STATIN_OK, 'Dosis habitual; mayor riesgo de dolor muscular sobre 40 mg al día.'] : ['talk', STATIN_POOR_LOW, 'Partir con 40 mg o menos al día.'];
  }
  if (slc === 'poor' || (slc === 'dec' && s <= 0.5)) {
    return ['talk', 'Dos de tus genes la mueven: entra menos a tu hígado y la eliminas más despacio. La guía sugiere otra estatina.', 'Preferir otra estatina.'];
  }
  return ['talk', slc === 'normal' ? 'La eliminas más despacio y queda más en la sangre. La guía sugiere partir con dosis baja.'
    : 'Dos de tus genes la mueven: entra menos a tu hígado y la eliminas algo más despacio. La guía sugiere partir con dosis baja.',
  `Partir con ${s <= 0.5 || slc === 'dec' ? '20' : '40'} mg o menos al día.`];
};

const HLA = ['HLA-B', 'Con este remedio también importa HLA-B*15:02, que en algunas personas causa reacciones graves en la piel. Tu examen no lo analiza.'];
const ALSO = (gene) => [gene, `También influye ${gene}, que tu examen no analiza.`];
// name, use, genes, rule, a gene that also matters: [gene, note when it is not read]; the rule reads it when it is.
// A drug with rule null has a CPIC guideline we have not written yet: its genes are shown, never a verdict.
const CATALOG = [
  ['Ibuprofeno', 'Dolor, fiebre e inflamación', ['CYP2C9'], nsaid],
  ['Celecoxib', 'Dolor e inflamación', ['CYP2C9'], nsaid],
  ['Flurbiprofeno', 'Dolor de garganta e inflamación', ['CYP2C9'], nsaid],
  ['Lornoxicam', 'Dolor e inflamación', ['CYP2C9'], nsaid],
  ['Meloxicam', 'Dolor articular', ['CYP2C9'], meloxicam],
  ['Piroxicam', 'Dolor articular', ['CYP2C9'], oxicam],
  ['Tenoxicam', 'Dolor articular', ['CYP2C9'], oxicam],
  ['Codeína', 'Dolor y tos', ['CYP2D6'], opioid('la', 'codeína', 'tramadol')],
  ['Tramadol', 'Dolor', ['CYP2D6'], opioid('lo', 'tramadol', 'codeína')],
  ['Clopidogrel', 'Evita coágulos', ['CYP2C19'], CLOPIDOGREL],
  ['Warfarina', 'Anticoagulante', ['CYP2C9', 'VKORC1'], warfarin, ALSO('CYP4F2')],
  ['Simvastatina', 'Colesterol', ['SLCO1B1'], SIMVASTATIN],
  ['Lovastatina', 'Colesterol', ['SLCO1B1'], LOVASTATIN],
  ['Atorvastatina', 'Colesterol', ['SLCO1B1'], ATORVASTATIN],
  ['Pitavastatina', 'Colesterol', ['SLCO1B1'], PITAVASTATIN],
  ['Fluvastatina', 'Colesterol', ['SLCO1B1', 'CYP2C9'], fluvastatin],
  ['Pravastatina', 'Colesterol', ['SLCO1B1'], PRAVASTATIN],
  ['Rosuvastatina', 'Colesterol', ['SLCO1B1'], rosuvastatin, ALSO('ABCG2')],
  ['Sertralina', 'Depresión y ansiedad', ['CYP2C19'], sertraline, ALSO('CYP2B6')],
  ['Citalopram', 'Depresión y ansiedad', ['CYP2C19'], CITALOPRAM],
  ['Escitalopram', 'Depresión y ansiedad', ['CYP2C19'], CITALOPRAM],
  ['Paroxetina', 'Depresión y ansiedad', ['CYP2D6'], PAROXETINE],
  ['Vortioxetina', 'Depresión', ['CYP2D6'], VORTIOXETINE],
  ['Nortriptilina', 'Depresión y dolor crónico', ['CYP2D6'], NORTRIPTYLINE],
  ['Amitriptilina', 'Depresión, dolor crónico y sueño', ['CYP2C19', 'CYP2D6'], amitriptyline],
  ['Omeprazol', 'Acidez y gastritis', ['CYP2C19'], PPI],
  ['Lansoprazol', 'Acidez y gastritis', ['CYP2C19'], PPI],
  ['Pantoprazol', 'Acidez y gastritis', ['CYP2C19'], PPI],
  ['Ondansetrón', 'Náuseas y vómitos', ['CYP2D6'], antiemetic],
  ['Tropisetrón', 'Náuseas y vómitos', ['CYP2D6'], antiemetic],
  ['Fenitoína', 'Epilepsia', ['CYP2C9'], phenytoinHla, HLA],
  ['Fosfenitoína', 'Epilepsia (uso hospitalario)', ['CYP2C9'], phenytoinHla, HLA],
  ['Atomoxetina', 'Déficit atencional', ['CYP2D6'], atomoxetine],
  ['Voriconazol', 'Infecciones por hongos', ['CYP2C19'], VORICONAZOLE],
  ['Tamoxifeno', 'Cáncer de mama', ['CYP2D6'], TAMOXIFEN],
  ['Abacavir', 'VIH', ['HLA-B'], hla('HLA-B', '*57:01', 'una reacción alérgica grave')],
  ['Alopurinol', 'Gota', ['HLA-B'], hla('HLA-B', '*58:01', SKIN)],
  ['Carbamazepina', 'Epilepsia y dolor de nervios', ['HLA-A', 'HLA-B'], carbamazepine],
  ['Oxcarbazepina', 'Epilepsia', ['HLA-B'], hla('HLA-B', '*15:02', SKIN)],
  ['Azatioprina', 'Enfermedades autoinmunes y trasplante', ['TPMT', 'NUDT15'], thiopurine],
  ['Mercaptopurina', 'Leucemia e inflamación intestinal', ['TPMT', 'NUDT15'], thiopurine],
  ['Tioguanina', 'Leucemia', ['TPMT', 'NUDT15'], thiopurine],
  ['Fluorouracilo', 'Cáncer', ['DPYD'], FLUORO],
  ['Capecitabina', 'Cáncer', ['DPYD'], FLUORO],
  ['Tacrolimus', 'Trasplante', ['CYP3A5'], TACROLIMUS],
  ['Efavirenz', 'VIH', ['CYP2B6'], EFAVIRENZ],
  ['Atazanavir', 'VIH', ['UGT1A1'], ATAZANAVIR],
  ['Primaquina', 'Malaria', ['G6PD'], G6PD_DRUG],
  ['Nitrofurantoína', 'Infección urinaria', ['G6PD'], G6PD_DRUG],
  ['Dapsona', 'Infecciones de la piel', ['G6PD'], G6PD_DRUG],
  ['Rasburicasa', 'Ácido úrico en quimioterapia', ['G6PD'], RASBURICASE],
  ['Sevoflurano', 'Anestesia general', ['RYR1', 'CACNA1S'], anesthetic],
  ['Desflurano', 'Anestesia general', ['RYR1', 'CACNA1S'], anesthetic],
  ['Isoflurano', 'Anestesia general', ['RYR1', 'CACNA1S'], anesthetic],
  ['Succinilcolina', 'Relajante muscular en anestesia', ['RYR1', 'CACNA1S'], anesthetic],
  ['Gentamicina', 'Infecciones graves', ['MT-RNR1'], aminoglycoside],
  ['Amikacina', 'Infecciones graves', ['MT-RNR1'], aminoglycoside],
  // CPIC level A, rules not written yet
  ['Ivacaftor', 'Fibrosis quística', ['CFTR'], null],
];

const joinY = (list) => list.join(' y ');

/**
 * The reader's table: every catalog drug with at least one of their genes, its verdict and the plain sentence.
 * Drugs none of whose genes were read go to `untested`, found only by search. A gene that was read is always
 * shown, even where no rule reads it yet.
 */
export function buildTable(rows) {
  const read = Object.fromEntries((rows || []).map((row) => [row.gene, readGene(row)]));
  const meds = [];
  const untested = [];
  for (const [name, use, genes, rule, [also, note] = []] of CATALOG) {
    const have = genes.filter((gene) => read[gene]);
    if (!have.length) { untested.push({ name, gene: joinY(genes) }); continue; }
    // the extra gene, once read, joins the drug's genes and its rule; its "not analyzed" note goes away
    const extra = also && read[also];
    const missing = extra ? null : note;
    const base = { name, use, genes: [...have, ...(extra ? [also] : [])].map((gene) => read[gene].row), missing };
    const lacking = genes.filter((gene) => !read[gene]);
    const odd = have.filter((gene) => !read[gene].level);
    if (lacking.length) {
      meds.push({ ...base, v: 'miss', say: `También depende de ${joinY(lacking)}, que tu examen no incluye. No sabemos cómo te afecta.`, cpic: null });
      continue;
    }
    // a phenotype off the guideline's table gets the plain fact, never a verdict
    const verdict = !odd.length && rule?.(read);
    if (verdict) {
      const [v, say, cpic] = verdict;
      meds.push({ ...base, v, say, cpic });
    } else {
      const shown = odd.length ? odd : have;
      meds.push({ ...base, v: 'unknown', say: `Tu resultado en ${joinY(shown)} es «${shown.map((gene) => read[gene].row.phenotype).join(' / ')}». Tu médico puede tenerlo en cuenta.`, cpic: null });
    }
  }
  meds.sort((a, b) => ORDER.indexOf(a.v) - ORDER.indexOf(b.v) || a.name.localeCompare(b.name, 'es'));
  const counts = Object.fromEntries(ORDER.map((v) => [v, meds.filter((m) => m.v === v).length]));
  return { meds, untested, counts };
}

// search ignores accents and case, and matches the name or what it is for
export const fold = (s) => s.normalize('NFD').replace(/\p{M}/gu, '').toLowerCase();
export const matches = (med, query) => {
  const q = fold(query.trim());
  return !q || [med.name, med.use || ''].some((text) => fold(text).includes(q));
};
