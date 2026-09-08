from django.core.management.base import BaseCommand
from genetics.models import SNP

class Command(BaseCommand):
    help = 'Populates the "grupo" field for existing trait SNPs based on their fenotipo.'

    def handle(self, *args, **kwargs):
        self.stdout.write('Starting to populate trait groups...')

        # Keyword-based mapping for more flexible group assignment
        group_keywords = {
            'Apariencia Física': ['ojos', 'piel', 'cabello', 'calvicie', 'pecas', 'pigmentación'],
            'Metabolismo': ['lactosa', 'cafeína', 'alcohol', 'vitamina', 'lactasa'],
            'Rendimiento Físico y Sensorial': ['resistencia', 'muscular', 'dolor', 'sabor', 'cerumen', 'atlético'],
            'Cognición': ['memoria', 'cognitiva', 'dopamina', 'TDAH', 'impulsividad'],
            'Bienestar y Salud': ['social', 'ánimo', 'melanoma', 'adicciones', 'nicotínica', 'alcoholismo', 'ansiedad', 'depresión', 'sueño', 'anandamida', 'empatía', 'sociabilidad', 'secretor'],
        }

        # Get all SNPs that are traits
        trait_snps = SNP.objects.filter(categoria='rasgos')
        
        updated_count = 0
        
        for snp in trait_snps:
            assigned_group = None
            fenotipo_lower = snp.fenotipo.lower()
            
            for group, keywords in group_keywords.items():
                if any(keyword in fenotipo_lower for keyword in keywords):
                    assigned_group = group
                    break
            
            if assigned_group:
                if snp.grupo != assigned_group:
                    snp.grupo = assigned_group
                    snp.save()
                    updated_count += 1
                    self.stdout.write(self.style.SUCCESS(f'Updated SNP {snp.rsid} ({snp.fenotipo}) to group "{assigned_group}"'))
                else:
                    self.stdout.write(self.style.NOTICE(f'SNP {snp.rsid} already in correct group "{assigned_group}"'))
            else:
                self.stdout.write(self.style.WARNING(f'No group found for SNP {snp.rsid} ({snp.fenotipo}). It will remain in its current group or null.'))

        self.stdout.write(self.style.SUCCESS(f'\nPopulation complete. Updated {updated_count} SNPs.'))
