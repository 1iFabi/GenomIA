import csv
import os
from decimal import Decimal
from django.core.management.base import BaseCommand
from genetics.models import SNP


class Command(BaseCommand):
    help = 'Importa datos de SNPs desde un archivo CSV'

    def add_arguments(self, parser):
        parser.add_argument(
            'csv_file',
            type=str,
            help='Ruta al archivo CSV con los datos de SNPs'
        )

    def handle(self, *args, **options):
        csv_file_path = options['csv_file']

        if not os.path.exists(csv_file_path):
            self.stdout.write(
                self.style.ERROR(f'El archivo {csv_file_path} no existe.')
            )
            return

        # Limpiar la tabla antes de importar
        SNP.objects.all().delete()
        self.stdout.write(
            self.style.SUCCESS('Tabla SNP vaciada.')
        )

        snps_creados = 0
        snps_errores = 0

        try:
            with open(csv_file_path, 'r', encoding='utf-8-sig') as csvfile:
                reader = csv.DictReader(csvfile)
                
                for row_num, row in enumerate(reader, start=2):  # Comenzar en 2 porque fila 1 es headers
                    try:
                        genotipo_raw = row.get('genotipo', '').strip()
                        genotipo_normalizado = genotipo_raw
                        if '/' in genotipo_normalizado:
                            alelos = sorted([a.strip() for a in genotipo_normalizado.split('/') if a.strip()])
                            genotipo_normalizado = "/".join(alelos)

                        # Mapear campos CSV a modelo
                        snp = SNP(
                            rsid=row.get('rs_id', '').strip(),
                            genotipo=genotipo_normalizado,
                            fenotipo=row.get('fenotipo', '').strip(),
                            categoria=row.get('categoria', '').strip() or None,
                            grupo=row.get('grupo_rasgos', '').strip() or None,
                            cromosoma=row.get('cromosoma', '').strip() or None,
                            posicion=int(row.get('posicion', 0)) if row.get('posicion', '').strip() else None,
                            alelo_referencia=row.get('alelo_referencia', '').strip() or None,
                            alelo_alternativo=row.get('alelo_alternativo', '').strip() or None,
                            nivel_riesgo=row.get('nivel_riesgo', '').strip() or None,
                            magnitud_efecto=Decimal(row.get('magnitud_efecto', '0')) if row.get('magnitud_efecto', '').strip() else None,
                            fuente_base_datos=row.get('fuente_base_datos', '').strip() or None,
                            tipo_evidencia=row.get('tipo_evidencia', '').strip() or None,
                            fecha_actualizacion=row.get('fecha_actualizacion', '').strip() or None,
                            continente=row.get('continente', '').strip() or None,
                            af_continente=Decimal(row.get('af_continente', '0')) if row.get('af_continente', '').strip() else None,
                            fuente_continente=row.get('fuente_continente', '').strip() or None,
                            poblacion_continente=row.get('poblacion_continente', '').strip() or None,
                            pais=row.get('pais', '').strip() or None,
                            af_pais=Decimal(row.get('af_pais', '0')) if row.get('af_pais', '').strip() else None,
                            fuente_pais=row.get('fuente_pais', '').strip() or None,
                            poblacion_pais=row.get('poblacion_pais', '').strip() or None,
                        )
                        snp.save()
                        snps_creados += 1

                    except Exception as e:
                        snps_errores += 1
                        self.stdout.write(
                            self.style.ERROR(
                                f'Error en fila {row_num}: {str(e)}'
                            )
                        )

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error al leer el archivo: {str(e)}')
            )
            return

        self.stdout.write(
            self.style.SUCCESS(
                f'\nImportación completada:\n'
                f'  - SNPs creados: {snps_creados}\n'
                f'  - Errores: {snps_errores}'
            )
        )
