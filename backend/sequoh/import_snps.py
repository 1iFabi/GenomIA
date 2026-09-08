#!/usr/bin/env python
"""
Script to import SNP data from CSV file into the database.
Deletes all existing SNPs and replaces them with new data.
"""

import os
import sys
import django
import csv
from decimal import Decimal
from pathlib import Path

# Add the backend project to the path
backend_path = Path(__file__).parent
sys.path.insert(0, str(backend_path))

# Add the project directories to the path
sequoh_path = backend_path / 'sequoh'
sys.path.insert(0, str(backend_path))
sys.path.insert(0, str(sequoh_path))

# Change to sequoh directory and configure Django
os.chdir(str(sequoh_path))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sequoh.settings')
django.setup()

from genetics.models import SNP

def import_snps_from_csv(csv_file_path):
    """
    Import SNPs from CSV file after deleting all existing records.
    """
    
    csv_path = Path(csv_file_path)
    if not csv_path.exists():
        print(f"[ERROR] CSV file not found at {csv_file_path}")
        return False
    
    print(f"[*] Starting SNP import from: {csv_file_path}\n")
    
    # Step 1: Delete all existing SNPs
    print("[DELETE] Deleting existing SNPs...")
    existing_count = SNP.objects.count()
    SNP.objects.all().delete()
    print(f"[OK] Deleted {existing_count} existing SNPs")
    
    # Step 2: Read and parse CSV
    print("\n[READ] Reading CSV file...")
    snps_to_import = []
    failed_rows = []
    
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        print(f"[OK] CSV file read with utf-8 encoding")
        
        # Skip header (line 1 contains column names)
        for line_num, line in enumerate(lines[1:], start=2):
            try:
                # Remove line number prefix (format: "123|data")
                if '|' in line:
                    _, csv_content = line.split('|', 1)
                else:
                    csv_content = line
                
                # Parse CSV line
                reader = csv.reader([csv_content.strip()])
                row = next(reader)
                
                if len(row) < 14:
                    failed_rows.append((line_num, "Not enough fields", row))
                    continue
                
                # Extract fields (CSV columns after the pipe delimiter)
                try:
                    snp_id = int(row[0]) if row[0] else None
                    rs_id = row[1].strip() if row[1] else ""
                    genotipo = row[2].strip() if row[2] else ""
                    fenotipo = row[3].strip() if row[3] else ""
                    categoria = row[4].strip() if row[4] else None
                    alelo_alternativo = row[5].strip() if row[5] else None
                    alelo_referencia = row[6].strip() if row[6] else None
                    cromosoma = row[7].strip() if row[7] else None
                    posicion = int(row[8]) if row[8] else None
                    fecha_actualizacion = row[9].strip() if row[9] else None
                    fuente_base_datos = row[10].strip() if row[10] else None
                    magnitud_efecto_str = row[11].strip() if row[11] else None
                    nivel_riesgo = row[12].strip() if row[12] else None
                    tipo_evidencia = row[13].strip() if row[13] else None
                    
                    # Ancestry data - Continent
                    continente = row[14].strip() if len(row) > 14 and row[14] else None
                    af_continente_str = row[15].strip() if len(row) > 15 and row[15] else None
                    fuente_continente = row[16].strip() if len(row) > 16 and row[16] else None
                    poblacion_continente = row[17].strip() if len(row) > 17 and row[17] else None
                    
                    # Ancestry data - Country
                    pais = row[18].strip() if len(row) > 18 and row[18] else None
                    af_pais_str = row[19].strip() if len(row) > 19 and row[19] else None
                    fuente_pais = row[20].strip() if len(row) > 20 and row[20] else None
                    poblacion_pais = row[21].strip() if len(row) > 21 and row[21] else None
                    
                    # Skip rows with empty critical fields
                    if not rs_id or not genotipo:
                        failed_rows.append((line_num, "Missing rsID or genotipo", row))
                        continue
                    
                    # Convert magnitud_efecto to Decimal
                    magnitud_efecto = None
                    if magnitud_efecto_str:
                        try:
                            magnitud_efecto = Decimal(magnitud_efecto_str)
                        except:
                            pass
                    
                    # Convert ancestry frequency fields to Decimal
                    af_continente = None
                    if af_continente_str:
                        try:
                            af_continente = Decimal(af_continente_str)
                        except:
                            pass
                    
                    af_pais = None
                    if af_pais_str:
                        try:
                            af_pais = Decimal(af_pais_str)
                        except:
                            pass
                    
                    snp = SNP(
                        rsid=rs_id,
                        genotipo=genotipo,
                        fenotipo=fenotipo,
                        categoria=categoria,
                        alelo_alternativo=alelo_alternativo,
                        alelo_referencia=alelo_referencia,
                        cromosoma=cromosoma,
                        posicion=posicion,
                        fecha_actualizacion=fecha_actualizacion,
                        fuente_base_datos=fuente_base_datos,
                        magnitud_efecto=magnitud_efecto,
                        nivel_riesgo=nivel_riesgo,
                        tipo_evidencia=tipo_evidencia,
                        # Ancestry data - Continent
                        continente=continente,
                        af_continente=af_continente,
                        fuente_continente=fuente_continente,
                        poblacion_continente=poblacion_continente,
                        # Ancestry data - Country
                        pais=pais,
                        af_pais=af_pais,
                        fuente_pais=fuente_pais,
                        poblacion_pais=poblacion_pais
                    )
                    snps_to_import.append(snp)
                    
                except ValueError as e:
                    failed_rows.append((line_num, f"Value error: {str(e)}", row))
                    continue
                
            except Exception as e:
                failed_rows.append((line_num, f"Parse error: {str(e)}", line))
                continue
        
        print(f"[OK] Parsed {len(snps_to_import)} valid SNP records")
        
        if failed_rows:
            print(f"[WARN] {len(failed_rows)} rows skipped due to errors")
        
        # Step 3: Bulk create SNPs in database
        if snps_to_import:
            print(f"\n[IMPORT] Importing {len(snps_to_import)} SNPs into database...")
            created_snps = SNP.objects.bulk_create(snps_to_import, batch_size=100)
            print(f"[OK] Successfully imported {len(created_snps)} SNPs")
            
            # Verify
            total_snps = SNP.objects.count()
            print(f"\n[STATS] Final database state:")
            print(f"   Total SNPs in database: {total_snps}")
            print(f"   Expected from CSV: {len(snps_to_import)}")
            
            if total_snps == len(snps_to_import):
                print("[OK] Import completed successfully!")
                return True
            else:
                print(f"[WARN] Expected {len(snps_to_import)} but found {total_snps} in database")
                return False
        else:
            print("[ERROR] No valid SNPs found in CSV file")
            return False
        
    except Exception as e:
        print(f"[ERROR] Error during import: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    # Use the CSV file path from the command or default path
    csv_file = sys.argv[1] if len(sys.argv) > 1 else r'C:\Users\fabia\OneDrive\Escritorio\PDS\pds\backend\sequoh'
    
    success = import_snps_from_csv(csv_file)
    sys.exit(0 if success else 1)
