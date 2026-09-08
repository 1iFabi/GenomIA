from django.core.management.base import BaseCommand
from django.db.models import Count
from genetics.models import SNP

class Command(BaseCommand):
    help = 'Normaliza los nombres de continentes y países en la tabla SNP.'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Iniciando la normalización de nombres...'))

        # --- Definir mapeos de corrección ---
        continent_map = {
            'americas': 'América',
            'américas': 'América',
            'america': 'América',
            'africa': 'África',
            'àfrica': 'África',
            'europe': 'Europa',
            'asia': 'Asia',
            'oceania': 'Oceanía',
            'asia oriental': 'Asia Oriental',
        }

        special_continent_map = {
            'Àfrica': 'África',
        }

        country_map = {
            'united states': 'Estados Unidos',
            'united kingdom': 'Reino Unido',
            'peru': 'Perú',
            'puerto rico': 'Puerto Rico',
        }

        special_country_map = {
            'PerÀº': 'Perú',
            'Peràº': 'Perú',
        }

        # --- Normalización de Continentes ---
        updated_continent_count = 0
        distinct_continents = SNP.objects.values_list('continente', flat=True).distinct()

        for name in distinct_continents:
            if not name:
                continue
            
            original_name = name
            normalized_name = None

            if original_name in special_continent_map:
                normalized_name = special_continent_map[original_name]
            else:
                normalized_name_lower = name.strip().lower()
                if normalized_name_lower in continent_map:
                    normalized_name = continent_map[normalized_name_lower]
                else:
                    potential_name = name.strip().title()
                    if potential_name != original_name:
                        normalized_name = potential_name

            if normalized_name and normalized_name != original_name:
                self.stdout.write(f"Continente: '{original_name}' -> '{normalized_name}'")
                updated_count = SNP.objects.filter(continente=original_name).update(continente=normalized_name)
                updated_continent_count += updated_count

        if updated_continent_count > 0:
            self.stdout.write(self.style.SUCCESS(f'✓ Se actualizaron {updated_continent_count} registros de continentes.'))
        else:
            self.stdout.write(self.style.NOTICE('No se necesitaron actualizaciones en los nombres de continentes.'))

        # --- Normalización de Países ---
        updated_country_count = 0
        distinct_countries = SNP.objects.values_list('pais', flat=True).distinct()

        for name in distinct_countries:
            if not name:
                continue

            original_name = name
            normalized_name = None

            if original_name in special_country_map:
                normalized_name = special_country_map[original_name]
            else:
                normalized_name_lower = name.strip().lower()
                if normalized_name_lower in country_map:
                    normalized_name = country_map[normalized_name_lower]
                else:
                    potential_name = name.strip().title()
                    if potential_name != original_name:
                        normalized_name = potential_name

            if normalized_name and normalized_name != original_name:
                self.stdout.write(f"País: '{original_name}' -> '{normalized_name}'")
                updated_count = SNP.objects.filter(pais=original_name).update(pais=normalized_name)
                updated_country_count += updated_count

        if updated_country_count > 0:
            self.stdout.write(self.style.SUCCESS(f'✓ Se actualizaron {updated_country_count} registros de países.'))
        else:
            self.stdout.write(self.style.NOTICE('No se necesitaron actualizaciones en los nombres de países.'))

        self.stdout.write(self.style.SUCCESS('\nNormalización completada.'))
