from django.core.management.base import BaseCommand, CommandError

from genoma.gene_inheritance import CATALOG, build_catalog


class Command(BaseCommand):
    help = ('Genera genoma/data/gene_inheritance.tsv desde el CSV de ClinGen Gene-Disease Validity '
            '(https://search.clinicalgenome.org/kb/gene-validity/download). Solo AD/AR con evidencia válida.')

    def add_arguments(self, parser):
        parser.add_argument('--path', required=True, help='Ruta al CSV descargado de ClinGen.')

    def handle(self, *args, path, **options):
        try:
            kept = build_catalog(path)
        except (OSError, ValueError) as error:
            raise CommandError(str(error)) from error
        self.stdout.write(self.style.SUCCESS(f'{kept} curaciones gen-enfermedad en {CATALOG}.'))
