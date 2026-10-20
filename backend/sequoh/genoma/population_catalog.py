"""Population catalog. The source of truth is genomia-ancestry/data/genomia_populations.tsv (open panels only);
`load_populations` copies it into Population, and results read labels and countries from there."""
import csv
import re
from pathlib import Path

from django.conf import settings
from django.db import transaction

from genoma.models import Population

CATALOG = 'genomia-ancestry'
CATALOG_FILE = Path('data') / 'genomia_populations.tsv'
LEVELS = ('group', 'cluster', 'reference')
COLUMNS = ('code', 'level', 'parent', 'reported', 'label_es', 'sampled_countries', 'region_countries',
           'region_status', 'panels', 'status', 'notes', 'client_note', 'country')
ISO2 = re.compile(r'[A-Z]{2}')
# The country view needs an Indigenous Chilean reference; without one every client would read "Chile 0%".
COUNTRY_VIEW_KEY = ('AMR', 'CL')


def default_catalog_path():
    if not settings.GENOMIA_ANCESTRY_DIR:
        raise ValueError('Define GENOMIA_ANCESTRY_DIR (carpeta del repo genomia-ancestry) o usa --path.')
    return Path(settings.GENOMIA_ANCESTRY_DIR) / CATALOG_FILE


def _countries(value, code):
    countries = [country for country in value.split(',') if country]
    if not all(ISO2.fullmatch(country) for country in countries):
        raise ValueError(f'{code}: países no ISO alfa-2 en "{value}".')
    return countries


def read_catalog(path):
    """Validated open rows, parents before children."""
    with open(path, encoding='utf-8', newline='') as handle:
        reader = csv.DictReader(handle, delimiter='\t')
        missing = set(COLUMNS) - set(reader.fieldnames or ())
        if missing:
            raise ValueError(f'Faltan columnas en el catálogo: {", ".join(sorted(missing))}.')
        rows = list(reader)
    codes = [row['code'] for row in rows]
    if len(codes) != len(set(codes)):
        raise ValueError('El catálogo tiene códigos repetidos.')
    open_rows = [row for row in rows if row['status'] == 'open']
    levels = {row['code']: row['level'] for row in open_rows}
    for row in rows:
        code = row['code']
        if row['status'] not in ('open', 'excluded') or row['level'] not in LEVELS \
                or row['reported'] not in ('yes', 'no'):
            raise ValueError(f'{code}: status, level o reported inválido.')
        if row['status'] == 'excluded':
            continue
        parent_level = levels.get(row['parent'])
        if row['level'] == 'group' and row['parent'] or row['level'] != 'group' and (
                parent_level is None or LEVELS.index(parent_level) >= LEVELS.index(row['level'])):
            raise ValueError(f'{code}: padre "{row["parent"]}" inválido.')
        if row['reported'] == 'yes' and not _countries(row['region_countries'], code):
            raise ValueError(f'{code}: una unidad reportada necesita region_countries.')
        if row['country'] and (row['level'] != 'reference' or not ISO2.fullmatch(row['country'])):
            raise ValueError(f'{code}: country debe ser un ISO alfa-2 y solo en filas reference.')
    return sorted(open_rows, key=lambda row: LEVELS.index(row['level']))


def load_catalog(path):
    """Upsert the open rows; rows that left the catalog stay (results point to them) but are retired."""
    rows = read_catalog(path)
    with transaction.atomic():
        saved = {}
        for row in rows:
            code = row['code']
            saved[code], _ = Population.objects.update_or_create(code=code, defaults={
                'name': row['label_es'], 'description': row['notes'] or None,
                'parent_population': saved.get(row['parent']),
                'geographic_region': row['region_countries'] or None, 'is_internal': False, 'is_masked': False,
                'metadata': {
                    'catalog': CATALOG, 'level': row['level'], 'reported': row['reported'] == 'yes',
                    'sampled_countries': _countries(row['sampled_countries'], code),
                    'region_countries': _countries(row['region_countries'], code),
                    'region_status': row['region_status'], 'panels': row['panels'],
                    'client_note': row['client_note'] or None, 'country': row['country'] or None,
                },
            })
        stale = Population.objects.filter(metadata__catalog=CATALOG).exclude(code__in=saved)
        for population in stale:
            population.metadata = {**population.metadata, 'reported': False, 'retired': True}
            population.save(update_fields=['metadata'])
    return {'loaded': len(saved), 'retired': len(stale)}


class Catalog:
    """The loaded catalog and its hierarchy, read in one query."""

    def __init__(self):
        self.by_pk = {p.pk: p for p in Population.objects.filter(metadata__catalog=CATALOG)
                      if not p.metadata.get('retired')}
        self.children = {}
        for p in self.by_pk.values():
            self.children.setdefault(p.parent_population_id, []).append(p)

    def __contains__(self, population):
        return population is not None and population.pk in self.by_pk

    def _up(self, population, stop):
        while not stop(population):
            population = self.by_pk[population.parent_population_id]
        return population

    def group_of(self, population):
        return self._up(population, lambda p: p.metadata['level'] == 'group')

    def unit_of(self, population):
        """The reported unit a population is shown under (itself when it is one)."""
        return self._up(population, lambda p: p.metadata['reported'])

    def units(self):
        return sorted((p for p in self.by_pk.values() if p.metadata['reported']), key=lambda p: p.code)

    def leaves(self, unit):
        """What a result is generated for: a unit's references, or the unit itself when it has none."""
        references = [p for p in self.children.get(unit.pk, []) if p.metadata['level'] == 'reference']
        return sorted(references, key=lambda p: p.code) or [unit]

    def country_view(self):
        group, country = COUNTRY_VIEW_KEY
        return any(p.metadata.get('country') == country and self.group_of(p).code == group
                   for p in self.by_pk.values())

    def describe(self, unit):
        """A unit's catalog fields for a result row."""
        group, meta = self.group_of(unit), unit.metadata
        return {'group': group.code, 'group_label': group.name, 'level': meta['level'],
                'region_countries': meta['region_countries'], 'sampled_countries': meta['sampled_countries'],
                'region_status': meta['region_status'],
                'measured_against': sorted(p.name for p in self.leaves(unit) if p != unit),
                'note': group.metadata.get('client_note')}


def reported_units():
    """(unit, continental group) for every unit shown with a percentage, by code; empty until loaded."""
    catalog = Catalog()
    return [(unit, catalog.group_of(unit)) for unit in catalog.units()]
