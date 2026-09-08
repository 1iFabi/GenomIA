"""
Comando de gestión Django para cargar datos de SNPs desde genomic_database.csv

Uso:
    python manage.py load_genomic_data [--csv-path RUTA] [--clear] [--dry-run]

Opciones:
    --csv-path: Ruta al archivo CSV (por defecto: ../../genomic_database.csv)
    --clear: Elimina todos los SNPs existentes antes de cargar
    --dry-run: Simula la carga sin modificar la base de datos
"""

import csv
import os
from decimal import Decimal, InvalidOperation
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from genetics.models import SNP


class Command(BaseCommand):
    help = 'Carga datos de SNPs desde genomic_database.csv'

    def add_arguments(self, parser):
        parser.add_argument(
            '--csv-path',
            type=str,
            default='../../genomic_database.csv',
            help='Ruta al archivo CSV de datos genómicos'
        )
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Eliminar todos los SNPs existentes antes de cargar'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Simular la carga sin modificar la base de datos'
        )

    def handle(self, *args, **options):
        csv_path = options['csv_path']
        clear = options['clear']
        dry_run = options['dry_run']

        # Resolver ruta absoluta
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__)))))
        csv_full_path = os.path.join(base_dir, csv_path)

        if not os.path.exists(csv_full_path):
            raise CommandError(f'El archivo CSV no existe: {csv_full_path}')

        self.stdout.write(self.style.SUCCESS(f'\n📁 Cargando desde: {csv_full_path}'))

        if dry_run:
            self.stdout.write(self.style.WARNING('⚠️  MODO DRY-RUN: No se modificará la base de datos\n'))

        # Limpiar datos existentes si se solicita
        if clear and not dry_run:
            count = SNP.objects.count()
            SNP.objects.all().delete()
            self.stdout.write(self.style.WARNING(f'🗑️  Eliminados {count} SNPs existentes\n'))

        # Procesar CSV
        created_count = 0
        updated_count = 0
        error_count = 0
        errors = []

        try:
            with open(csv_full_path, 'r', encoding='utf-8-sig') as csvfile:
                # Leer primera línea para detectar formato
                first_line = csvfile.readline()
                csvfile.seek(0)
                
                # El CSV tiene un formato especial con comillas dobles escapadas
                # Necesitamos procesarlo manualmente
                reader = csv.reader(csvfile)
                headers = next(reader)  # Saltar encabezados
                
                self.stdout.write(f'📊 Procesando registros...\n')

                with transaction.atomic():
                    for row_num, row in enumerate(reader, start=2):
                        try:
                            # Nuevo formato CSV con todas las columnas:
                            # id, rs_id, genotipo, fenotipo, categoria, alelo_alternativo, alelo_referencia,
                            # cromosoma, posicion, fecha_actualizacion, fuente_base_datos, magnitud_efecto,
                            # nivel_riesgo, tipo_evidencia, continente, af_continente, fuente_continente,
                            # poblacion_continente, pais, af_pais, fuente_pais, poblacion_pais
                            
                            if len(row) < 14:
                                raise ValueError(f'Formato inválido: esperados 14+ campos, encontrados {len(row)}')
                            
                            # Mapear las columnas del nuevo CSV
                            rsid = row[1]              # rs_id
                            genotipo = row[2]         # genotipo
                            fenotipo = row[3]         # fenotipo
                            categoria = row[4]        # categoria
                            alelo_alt = row[5]        # alelo_alternativo
                            alelo_ref = row[6]        # alelo_referencia
                            cromosoma = row[7]        # cromosoma
                            posicion_str = row[8]     # posicion
                            fecha = row[9]            # fecha_actualizacion
                            fuente = row[10]          # fuente_base_datos
                            magnitud_efecto_str = row[11]  # magnitud_efecto
                            nivel_riesgo = row[12]    # nivel_riesgo
                            tipo_evidencia = row[13]  # tipo_evidencia
                            
                            # Datos opcionales de ancestría
                            continente = row[14] if len(row) > 14 else None
                            af_continente_str = row[15] if len(row) > 15 else None
                            fuente_continente = row[16] if len(row) > 16 else None
                            poblacion_continente = row[17] if len(row) > 17 else None
                            pais = row[18] if len(row) > 18 else None
                            af_pais_str = row[19] if len(row) > 19 else None
                            fuente_pais = row[20] if len(row) > 20 else None
                            poblacion_pais = row[21] if len(row) > 21 else None

                            # Convertir tipos
                            try:
                                posicion = int(posicion_str) if posicion_str and posicion_str.strip() else None
                            except ValueError:
                                posicion = None

                            try:
                                magnitud_efecto = Decimal(magnitud_efecto_str) if magnitud_efecto_str and magnitud_efecto_str.strip() else None
                            except (ValueError, InvalidOperation):
                                magnitud_efecto = None
                            
                            # Convertir datos de ancestría
                            try:
                                af_continente = Decimal(af_continente_str) if af_continente_str and af_continente_str.strip() else None
                            except (ValueError, InvalidOperation):
                                af_continente = None
                            
                            try:
                                af_pais = Decimal(af_pais_str) if af_pais_str and af_pais_str.strip() else None
                            except (ValueError, InvalidOperation):
                                af_pais = None

                            # Crear o actualizar SNP
                            if not dry_run:
                                snp, created = SNP.objects.update_or_create(
                                    rsid=rsid,
                                    genotipo=genotipo,
                                    defaults={
                                        'fenotipo': fenotipo,
                                        'categoria': categoria,
                                        'cromosoma': cromosoma,
                                        'posicion': posicion,
                                        'alelo_referencia': alelo_ref,
                                        'alelo_alternativo': alelo_alt,
                                        'nivel_riesgo': nivel_riesgo,
                                        'magnitud_efecto': magnitud_efecto,
                                        'fuente_base_datos': fuente,
                                        'tipo_evidencia': tipo_evidencia,
                                        'fecha_actualizacion': fecha,
                                        'continente': continente,
                                        'af_continente': af_continente,
                                        'fuente_continente': fuente_continente,
                                        'poblacion_continente': poblacion_continente,
                                        'pais': pais,
                                        'af_pais': af_pais,
                                        'fuente_pais': fuente_pais,
                                        'poblacion_pais': poblacion_pais,
                                    }
                                )
                                
                                if created:
                                    created_count += 1
                                else:
                                    updated_count += 1
                            else:
                                # En dry-run solo contar
                                created_count += 1

                            # Mostrar progreso cada 10 registros
                            if (created_count + updated_count) % 10 == 0:
                                self.stdout.write(
                                    f'  ✓ Procesados: {created_count + updated_count} registros',
                                    ending='\r'
                                )

                        except Exception as e:
                            error_count += 1
                            error_msg = f'Error en línea {row_num}: {str(e)}'
                            errors.append(error_msg)
                            if error_count <= 5:  # Mostrar solo los primeros 5 errores
                                self.stdout.write(self.style.ERROR(f'  ✗ {error_msg}'))

        except Exception as e:
            raise CommandError(f'Error al procesar el archivo CSV: {str(e)}')

        # Resumen final
        self.stdout.write('\n')
        self.stdout.write(self.style.SUCCESS('═' * 60))
        self.stdout.write(self.style.SUCCESS('  📊 RESUMEN DE CARGA'))
        self.stdout.write(self.style.SUCCESS('═' * 60))
        
        if not dry_run:
            self.stdout.write(self.style.SUCCESS(f'  ✓ SNPs creados:      {created_count}'))
            self.stdout.write(self.style.SUCCESS(f'  ↻ SNPs actualizados: {updated_count}'))
        else:
            self.stdout.write(self.style.WARNING(f'  → SNPs a crear:      {created_count}'))
        
        if error_count > 0:
            self.stdout.write(self.style.ERROR(f'  ✗ Errores:           {error_count}'))
            if error_count > 5:
                self.stdout.write(self.style.WARNING(f'    (Mostrando solo los primeros 5 errores)'))
        
        self.stdout.write(self.style.SUCCESS('═' * 60))
        
        if not dry_run:
            total = SNP.objects.count()
            self.stdout.write(self.style.SUCCESS(f'\n  🎉 Total de SNPs en base de datos: {total}\n'))
        else:
            self.stdout.write(self.style.WARNING('\n  ⚠️  Ejecuta sin --dry-run para aplicar cambios\n'))
