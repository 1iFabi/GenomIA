const rows = (data, key) => (Array.isArray(data?.modules?.[key]) ? data.modules[key] : []);
const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;
const pct = (p) => `${(p * 100).toLocaleString('es-CL', { minimumFractionDigits: 1, maximumFractionDigits: 1 })}%`;

/** Ancestry components summed by group, largest first: [[label, proportion], ...]. */
export const ancestryGroups = (data) => {
  const groups = new Map();
  for (const r of rows(data, 'global_ancestry')) {
    const key = r.group_label || r.label;
    if (key && Number.isFinite(r.proportion)) groups.set(key, (groups.get(key) || 0) + r.proportion);
  }
  return [...groups].sort((a, b) => b[1] - a[1]);
};

/**
 * One line of the client's own results per module, for the dashboard: never a finding.
 * Monogenic risk shows only how many variants were reviewed (Ley 21.719: a summary
 * surface must not surface a delicate result). Missing data yields null.
 */
export function helixTeasers(data) {
  const out = {};

  const [top] = ancestryGroups(data);
  if (top) out.global_ancestry = { figure: pct(top[1]), caption: `componente ${top[0].toLowerCase()}` };

  const genes = rows(data, 'pharmacogenetics').map((r) => r.gene).filter(Boolean);
  if (genes.length) out.pharmacogenetics = { figure: String(genes.length), caption: `${genes.length === 1 ? 'gen' : 'genes'}: ${genes.slice(0, 3).join(', ')}${genes.length > 3 ? ' y más' : ''}` };

  const traits = rows(data, 'traits');
  if (traits.length) {
    const cats = new Set(traits.map((r) => r.category).filter(Boolean)).size;
    out.traits = { figure: String(traits.length), caption: `${traits.length === 1 ? 'rasgo' : 'rasgos'}${cats ? ` en ${plural(cats, 'categoría', 'categorías')}` : ''}` };
  }

  const poly = rows(data, 'polygenic_risk').length;
  if (poly) out.polygenic_risk = { figure: String(poly), caption: `${poly === 1 ? 'condición comparada' : 'condiciones comparadas'} con la población` };

  const reviewed = data?.variant_summary?.total;
  if (Number.isFinite(reviewed) && reviewed > 0) {
    out.monogenic_risk = { figure: reviewed.toLocaleString('es-CL'), caption: 'variantes revisadas contra ClinVar' };
  }
  return out;
}

/**
 * Short lines Genomin says over the helix, several per module, each a different way of reading the
 * same real figure (the number, what it spans, a question, the way in). Same rule as the teasers:
 * never a finding; monogenic risk has one line, the count.
 */
export function helixReadings(data) {
  const out = {};

  const groups = ancestryGroups(data);
  if (groups.length) {
    const [[name, share], second] = groups;
    out.global_ancestry = [
      `Tu componente principal es ${name.toLowerCase()}: ${pct(share)}.`,
      groups.length > 1 ? `Tu mapa reúne ${groups.length} componentes: ${groups.map(([g]) => g.toLowerCase()).join(', ').replace(/, ([^,]*)$/, ' y $1')}.` : null,
      second ? `¿Te cuento de dónde viene tu ${pct(second[1])} ${second[0].toLowerCase()}?` : null,
      'Tus raíces, continente por continente.',
    ].filter(Boolean);
  }

  const genes = rows(data, 'pharmacogenetics').map((r) => r.gene).filter(Boolean);
  if (genes.length) {
    out.pharmacogenetics = [
      `Leí ${plural(genes.length, 'gen que influye', 'genes que influyen')} en cómo procesas remedios.`,
      `${genes.slice(0, 3).join(', ')}${genes.length > 3 ? ` y ${genes.length - 3} más` : ''}.`,
      `¿Te explico qué hace un gen como el ${genes[0]}?`,
      'Busca un remedio y te digo qué gen lo procesa.',
    ];
  }

  const traits = rows(data, 'traits');
  if (traits.length) {
    const cats = [...new Set(traits.map((r) => r.category).filter(Boolean))];
    out.traits = [
      `Encontré ${plural(traits.length, 'rasgo', 'rasgos')}${cats.length ? ` en ${plural(cats.length, 'categoría', 'categorías')}` : ''}.`,
      cats.length ? `¿Empezamos por ${cats[0].toLowerCase()}?` : null,
      `${plural(traits.length, 'detalle tuyo', 'detalles tuyos')}, ordenados por categoría.`,
    ].filter(Boolean);
  }

  const poly = rows(data, 'polygenic_risk').length;
  if (poly) {
    out.polygenic_risk = [
      `Comparé ${plural(poly, 'condición', 'condiciones')} con la población.`,
      'Es una comparación con otras personas, no un diagnóstico.',
      '¿Te explico cómo se lee esta comparación?',
    ];
  }

  const reviewed = data?.variant_summary?.total;
  if (Number.isFinite(reviewed) && reviewed > 0) {
    out.monogenic_risk = [`Revisé ${reviewed.toLocaleString('es-CL')} variantes contra ClinVar.`];
  }
  return out;
}
