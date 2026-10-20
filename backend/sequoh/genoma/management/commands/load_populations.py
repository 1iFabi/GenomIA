from django.core.management.base import BaseCommand, CommandError

from genoma.population_catalog import default_catalog_path, load_catalog


class Command(BaseCommand):
    help = ('Carga el catálogo de poblaciones de ancestría desde genomia-ancestry/data/genomia_populations.tsv '
            '(GENOMIA_ANCESTRY_DIR) o desde --path. Solo filas "open"; se puede repetir.')

    def add_arguments(self, parser):
        parser.add_argument('--path', help='Ruta al TSV; por defecto el de GENOMIA_ANCESTRY_DIR.')

    def handle(self, *args, path, **options):
        try:
            summary = load_catalog(path or default_catalog_path())
        except (OSError, ValueError) as error:
            raise CommandError(str(error)) from error
        self.stdout.write(self.style.SUCCESS(
            f"{summary['loaded']} poblaciones cargadas, {summary['retired']} retiradas del reporte."))
