"""Mode of inheritance per gene and disease, from ClinGen Gene-Disease Validity (public download at
https://search.clinicalgenome.org/kb/gene-validity). `build_gene_inheritance` turns that CSV into
data/gene_inheritance.tsv, which is versioned with the code and read here.

Only curations backed by Definitive, Strong or Moderate evidence count. A gene can carry one mode per
disease (BRCA2: AD cancer predisposition, AR Fanconi anemia), so a variant is matched by its ClinVar
disease (MONDO id) first, and by the gene alone only when every curation of the gene agrees. Anything
else, or a mode other than AD/AR (X-linked needs the client's sex), has no answer: the page sends the
variant to "conversar", never to the client's own health nor to "only for your children"."""
import csv
import re
from functools import lru_cache
from pathlib import Path

CATALOG = Path(__file__).parent / 'data' / 'gene_inheritance.tsv'
VALID = {'Definitive', 'Strong', 'Moderate'}
MODES = {'AD', 'AR'}
MONDO = re.compile(r'MONDO:(MONDO:\d+)')


def build_catalog(source, target=CATALOG):
    """Writes gene, MONDO disease and mode from a ClinGen gene-validity CSV; returns the curations kept."""
    with open(source, encoding='utf-8', newline='') as handle:
        rows = list(csv.reader(handle))
    created = next((row[0] for row in rows if row and row[0].startswith('FILE CREATED:')), 'FILE CREATED: ?')
    try:
        header = next(i for i, row in enumerate(rows) if row and row[0] == 'GENE SYMBOL')
    except StopIteration:
        raise ValueError('No es un CSV de ClinGen gene-validity: falta la fila "GENE SYMBOL".') from None
    columns = rows[header]
    kept = set()
    for row in rows[header + 1:]:
        record = dict(zip(columns, row))
        gene = record.get('GENE SYMBOL', '')
        if gene and not gene.startswith('+') and record.get('CLASSIFICATION') in VALID and record.get('MOI'):
            kept.add((gene, record.get('DISEASE ID (MONDO)', ''), record['MOI']))
    if not kept:
        raise ValueError('El CSV no trae ninguna curación con evidencia válida.')
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, 'w', encoding='utf-8', newline='') as handle:
        handle.write(f'# ClinGen Gene-Disease Validity, {created}\n')
        writer = csv.writer(handle, delimiter='\t', lineterminator='\n')
        writer.writerow(('gene', 'mondo', 'moi'))
        writer.writerows(sorted(kept))
    inheritance_catalog.cache_clear()
    return len(kept)


@lru_cache(maxsize=1)
def inheritance_catalog():
    """gene → [(mondo, moi), ...]"""
    if not CATALOG.exists():
        return {}
    catalog = {}
    with open(CATALOG, encoding='utf-8', newline='') as handle:
        for row in csv.DictReader((line for line in handle if not line.startswith('#')), delimiter='\t'):
            catalog.setdefault(row['gene'], []).append((row['mondo'], row['moi']))
    return catalog


def mondo_ids(clndisdb):
    """MONDO ids in a ClinVar CLNDISDB value ('MONDO:MONDO:0011450,MedGen:C0000|...')."""
    return set(MONDO.findall(str(clndisdb or '')))


def inheritance(gene, diseases=()):
    """'AD', 'AR' or None when the variant's disease and its gene give no single AD/AR mode."""
    curations = inheritance_catalog().get(gene or '', [])
    modes = {moi for mondo, moi in curations if mondo in diseases} or {moi for _, moi in curations}
    return next(iter(modes)) if len(modes) == 1 and modes <= MODES else None
