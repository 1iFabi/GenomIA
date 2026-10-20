import tempfile
from pathlib import Path

from django.contrib.auth.models import User
from django.test import TestCase

from genoma.client_results import populate_client_results
from genoma.models import Population
from genoma.population_catalog import Catalog, load_catalog, reported_units

# A subset of genomia-ancestry/data/genomia_populations.tsv, with one excluded row.
CATALOG_FIXTURE = Path(__file__).parent / 'fixtures' / 'test_populations.tsv'
# The planned Indigenous Chilean reference, which turns on the country view.
CHILEAN_REFERENCE = ('CHL_TEST\treference\tAMR_ANDES\tno\tReferencia chilena\tCL\tCL\tmeasured\tpropio'
                     '\topen\t\t\tCL\n')


def catalog_with_chilean_reference(folder):
    path = Path(folder) / 'catalog.tsv'
    path.write_text(CATALOG_FIXTURE.read_text(encoding='utf-8') + CHILEAN_REFERENCE, encoding='utf-8')
    return path


class PopulationCatalogTests(TestCase):
    def write(self, text):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        path = Path(folder.name) / 'catalog.tsv'
        path.write_text(text, encoding='utf-8')
        return path

    def test_loads_open_rows_with_hierarchy_and_never_the_excluded_ones(self):
        self.assertEqual(load_catalog(CATALOG_FIXTURE), {'loaded': 17, 'retired': 0})
        self.assertFalse(Population.objects.filter(code='MAPUCHE').exists())
        andes = Population.objects.get(code='AMR_ANDES')
        self.assertEqual((andes.name, andes.parent_population.code), ('Andino', 'AMR'))
        self.assertEqual(andes.metadata['region_countries'], ['PE', 'BO', 'CL'])
        self.assertEqual({unit.code: group.code for unit, group in reported_units()}, {
            'AMR_ANDES': 'AMR', 'AMR_AMAZON': 'AMR', 'IBS': 'EUR', 'TSI': 'EUR', 'YRI': 'AFR', 'CHB': 'EAS',
            'MID_LEVANT': 'MID', 'OCE': 'OCE'})
        catalog = Catalog()
        described = catalog.describe(andes)
        self.assertEqual(described['measured_against'], ['Boliviano andino', 'Quechua'])
        self.assertEqual(described['sampled_countries'], ['PE', 'BO'])
        self.assertIn('sur de Chile', described['note'])
        self.assertIsNone(catalog.describe(Population.objects.get(code='IBS'))['note'])
        self.assertEqual([p.code for p in catalog.leaves(andes)], ['Bolivian', 'Quechua'])
        self.assertEqual([p.code for p in catalog.leaves(Population.objects.get(code='OCE'))], ['OCE'])
        self.assertEqual(Population.objects.get(code='Quechua').metadata['country'], 'PE')
        self.assertFalse(catalog.country_view())

    def test_country_view_turns_on_only_with_an_indigenous_chilean_reference(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        load_catalog(catalog_with_chilean_reference(folder.name))
        self.assertTrue(Catalog().country_view())

    def test_reloading_retires_rows_that_left_the_catalog(self):
        load_catalog(CATALOG_FIXTURE)
        lines = CATALOG_FIXTURE.read_text(encoding='utf-8').splitlines()
        self.assertEqual(load_catalog(self.write('\n'.join(l for l in lines if not l.startswith('TSI\t')))),
                         {'loaded': 16, 'retired': 1})
        self.assertNotIn('TSI', [unit.code for unit, _ in reported_units()])

    def test_rejects_a_broken_catalog_without_touching_the_database(self):
        header = CATALOG_FIXTURE.read_text(encoding='utf-8').splitlines()[0]
        broken = {
            'columna faltante': header.replace('\tcountry', '') + '\n',
            'padre inexistente': header + '\nIBS\treference\tEUR\tyes\tIbérico\tES\tES\tproposal\t1000G\topen\t\t\tES\n',
            'país no ISO': header + '\nOCE\tgroup\t\tyes\tOceánico\tPG\tPapua\tproposal\tHO\topen\t\t\t\n',
            'country fuera de reference': header + '\nOCE\tgroup\t\tyes\tOceánico\tPG\tPG\tproposal\tHO\topen\t\t\tPG\n',
        }
        for case, text in broken.items():
            with self.subTest(case), self.assertRaises(ValueError):
                load_catalog(self.write(text))
        self.assertFalse(Population.objects.exists())

    def test_results_need_the_catalog(self):
        with self.assertRaisesMessage(ValueError, 'load_populations'):
            populate_client_results(User.objects.create_user(username='no-catalog'), 1)
