"""
Django management command para enriquecer fenotipos de variantes genéticas.

Uso:
    python manage.py enrich_variants
"""

from django.core.management.base import BaseCommand
from genetics.enrichment_variants import enrich_variants_command


class Command(BaseCommand):
    help = "Enriquece fenotipos de variantes genéticas consultando fuentes confiables"

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Simula la ejecución sin hacer cambios',
        )

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS('Iniciando enriquecimiento de variantes genéticas...')
        )
        
        try:
            results = enrich_variants_command()
            
            self.stdout.write(
                self.style.SUCCESS(f'\n✓ Variantes actualizadas: {results["actualizados"]}')
            )
            self.stdout.write(
                self.style.WARNING(f'- Variantes sin cambios: {results["sin_cambios"]}')
            )
            
            if results['errores']:
                self.stdout.write(
                    self.style.ERROR(f'\n✗ Errores encontrados: {len(results["errores"])}')
                )
                for error in results['errores']:
                    self.stdout.write(self.style.ERROR(f'  {error}'))
            
            self.stdout.write(
                self.style.SUCCESS('\n✓ Enriquecimiento completado exitosamente')
            )
        
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'\n✗ Error durante el enriquecimiento: {str(e)}')
            )
