from django.core.management.base import BaseCommand
from genetics.models import SNP
import json


class Command(BaseCommand):
    help = "Exporta todos los SNPs a JSON para análisis exhaustivo"

    def handle(self, *args, **options):
        snps = SNP.objects.all().order_by('rsid', 'genotipo')
        
        data = []
        for snp in snps:
            data.append({
                'id': snp.id,
                'rsid': snp.rsid,
                'genotipo': snp.genotipo,
                'fenotipo': snp.fenotipo,
                'categoria': snp.categoria,
                'cromosoma': snp.cromosoma,
                'posicion': snp.posicion,
                'alelo_referencia': snp.alelo_referencia,
                'alelo_alternativo': snp.alelo_alternativo,
                'nivel_riesgo': snp.nivel_riesgo,
                'magnitud_efecto': float(snp.magnitud_efecto) if snp.magnitud_efecto else None,
                'fuente_base_datos': snp.fuente_base_datos,
                'tipo_evidencia': snp.tipo_evidencia,
                'fecha_actualizacion': snp.fecha_actualizacion,
            })
        
        # Guardar a archivo JSON
        with open('all_snps_export.json', 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        self.stdout.write(self.style.SUCCESS(f'\n✓ Exportados {len(data)} SNPs a all_snps_export.json'))
        
        # Análisis rápido
        problematic = [s for s in data if 'Variante genética' in (s['fenotipo'] or '') or 
                       'Medida antropométrica' in (s['fenotipo'] or '') or
                       not s['fenotipo'] or not s['categoria']]
        
        self.stdout.write(f'\n⚠️ Registros problemáticos: {len(problematic)}')
        self.stdout.write(f'\n📋 RSIDs únicos problemáticos:')
        
        rsids_problematic = sorted(set([s['rsid'] for s in problematic]))
        for rsid in rsids_problematic:
            self.stdout.write(f'  - {rsid}')
