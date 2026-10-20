import tempfile
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from django.test import SimpleTestCase

from genoma import gene_inheritance

CSV = """FILE CREATED: 2026-10-19
GENE SYMBOL,DISEASE ID (MONDO),CLASSIFICATION,MOI
GENA,MONDO:0000001,Definitive,AD
GENA,MONDO:0000002,Strong,AR
GENB,MONDO:0000003,Moderate,AD
GENXL,MONDO:0000004,Definitive,XL
GENC,MONDO:0000005,Limited,AD
+D,MONDO:0000006,Definitive,AD
"""


@contextmanager
def catalog_at(target):
    """Points the module at `target` and drops the memoized catalog around the block."""
    with patch.object(gene_inheritance, 'CATALOG', Path(target)):
        gene_inheritance.inheritance_catalog.cache_clear()
        try:
            yield
        finally:
            gene_inheritance.inheritance_catalog.cache_clear()


class GeneInheritanceTests(SimpleTestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.csv = Path(folder.name) / 'clingen.csv'
        self.csv.write_text(CSV, encoding='utf-8')
        self.tsv = Path(folder.name) / 'gene_inheritance.tsv'

    def test_build_catalog_keeps_valid_curations_and_writes_every_mode(self):
        self.assertEqual(gene_inheritance.build_catalog(self.csv, target=self.tsv), 4)
        lines = self.tsv.read_text(encoding='utf-8').splitlines()
        self.assertEqual(lines[0], '# ClinGen Gene-Disease Validity, FILE CREATED: 2026-10-19')
        self.assertEqual(lines[1], 'gene\tmondo\tmoi')
        self.assertEqual(set(lines[2:]), {
            'GENA\tMONDO:0000001\tAD', 'GENA\tMONDO:0000002\tAR',
            'GENB\tMONDO:0000003\tAD', 'GENXL\tMONDO:0000004\tXL',
        })

    def test_build_catalog_rejects_a_file_without_clingen_curations(self):
        self.csv.write_text('something,else\n', encoding='utf-8')
        with self.assertRaises(ValueError):
            gene_inheritance.build_catalog(self.csv, target=self.tsv)

    def test_matches_the_variant_disease_before_the_gene(self):
        gene_inheritance.build_catalog(self.csv, target=self.tsv)
        with catalog_at(self.tsv):
            self.assertEqual(gene_inheritance.inheritance('GENA', {'MONDO:0000002'}), 'AR')
            self.assertEqual(gene_inheritance.inheritance('GENA', {'MONDO:0000001'}), 'AD')

    def test_uses_the_gene_mode_only_when_every_curation_agrees(self):
        gene_inheritance.build_catalog(self.csv, target=self.tsv)
        with catalog_at(self.tsv):
            self.assertEqual(gene_inheritance.inheritance('GENB'), 'AD')
            self.assertIsNone(gene_inheritance.inheritance('GENA'))
            self.assertIsNone(gene_inheritance.inheritance('GENA', {'MONDO:0999999'}))
            self.assertIsNone(gene_inheritance.inheritance('GENXL'))
            self.assertIsNone(gene_inheritance.inheritance('GENUNCURATED'))

    def test_mondo_ids_reads_every_id_in_a_clinvar_disease_field(self):
        self.assertEqual(gene_inheritance.mondo_ids('MONDO:MONDO:0011450,MedGen:C0000|MONDO:MONDO:0000002'),
                         {'MONDO:0011450', 'MONDO:0000002'})
        self.assertEqual(gene_inheritance.mondo_ids(None), set())
