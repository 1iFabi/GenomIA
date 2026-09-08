import os
import django
import sys

# Agregar el directorio padre al path para poder importar los settings
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sequoh.settings')
django.setup()

from genetics.models import PharmacogeneticSystem, SNP
from django.db.models import Q

SYSTEMS_DATA = [
    {
        "name": "Cardiología",
        "description": "Fármacos cardiovasculares, anticoagulantes, antiplaquetarios, estatinas y beta-bloqueadores.",
        # Keywords: Drugs + Genes
        "keywords": [
            "warfarin", "warfarina", 
            "clopidogrel", 
            "simvastatin", "simvastatina", "atorvastatin", 
            "acacenocumarol",
            "vkcor1", "vkorc1", 
            "cyp2c9", # Warfarina (principal), aunque metaboliza otros, su mayor impacto clínico es cardio
            "slco1b1", 
            "adrb1", "adrb2", # Beta receptors (Cardio/Pulmonar - asignado a Cardio por afinidad sistémica)
            "f5", "f2", # Factores coagulación
            "ace", # Angiotensina
            "nos3"
        ]
    },
    {
        "name": "Salud Mental y Neurología",
        "description": "Antidepresivos, antipsicóticos, ansiolíticos, antiepilépticos, tratamiento del dolor y opioides.",
        "keywords": [
            "sertraline", "sertralina", 
            "citalopram", "escitalopram", 
            "fluoxetine", "fluoxetina",
            "paroxetine", "paroxetina",
            "venlafaxine", "venlafaxina",
            "amitriptyline", "amitriptilina",
            "risperidone", "risperidona", 
            "haloperidol", "aripiprazole",
            "diazepam", "clobazam",
            "codeine", "codeina", 
            "tramadol", "morphine", "morfina", "opioid",
            "carbamazepine", "carbamazepina", "phenytoin", "fenitoina",
            "cyp2d6", # El gen clave en psiquiatría
            "cyp2c19", # Antidepresivos (aunque también clopidogrel/omeprazol, ver lógica de desempate)
            "comt", "oprm1", "ankk1", "drd2", "Htr2a", "Htr2c",
            "hla-b*15:02", "hla-a*31:01" # Carbamazepina
        ]
    },
    {
        "name": "Gastroenterología",
        "description": "Inhibidores de la bomba de protones (IBP), tratamientos para H. pylori e inmunosupresores de trasplante hepático/renal.",
        "keywords": [
            "omeprazole", "omeprazol", 
            "lansoprazole", "lansoprazol", 
            "pantoprazole", "pantoprazol", 
            "esomeprazole", "esomeprazol",
            "tacrolimus", 
            "cyp3a5", # Tacrolimus
            "cyp3a4",
            "nod2"
        ]
    },
    {
        "name": "Salud Ósea y Reumatología",
        "description": "Tratamientos para gota, artritis reumatoide, osteoporosis y enfermedades autoinmunes.",
        "keywords": [
            "allopurinol", "alopurinol",
            "methotrexate", "metotrexato",
            "azathioprine", "azatioprina",
            "thioguanine", "tioguanina",
            "mercaptopurine", "mercaptopurina",
            "infliximab", "adalimumab",
            "hla-b*58:01", # Alopurinol
            "tpmt", "nudt15", # Tiopurinas
            "mthfr" # Metotrexato (a veces)
        ]
    },
    {
        "name": "Oncología",
        "description": "Quimioterapia y terapias dirigidas para diversos tipos de cáncer.",
        "keywords": [
            "tamoxifen", "tamoxifeno",
            "fluorouracil", "5-fu", "capecitabine", "capecitabina",
            "irinotecan", 
            "cisplatin", "cisplatino",
            "dpyd", "ugt1a1", "gstp1"
        ]
    }
]

def run():
    print("Iniciando clasificación masiva de Farmacogenética...")
    
    # 1. Asegurar que los sistemas existan
    systems_map = {}
    for sys_data in SYSTEMS_DATA:
        obj, _ = PharmacogeneticSystem.objects.get_or_create(
            name=sys_data["name"],
            defaults={"description": sys_data["description"]}
        )
        systems_map[sys_data["name"]] = obj

    # 2. Obtener todos los SNPs de farmacogenética
    # Filtramos por categoría que contenga 'farmaco' (case insensitive)
    pharm_snps = SNP.objects.filter(categoria__icontains='farmaco')
    print(f"Total SNPs encontrados en categoría 'Farmacogenética': {pharm_snps.count()}")

    count_assigned = 0
    count_unassigned = 0

    for snp in pharm_snps:
        text = (f"{snp.fenotipo} {snp.rsid} {snp.grupo} {snp.explanation if hasattr(snp, 'explanation') else ''}").lower()
        
        assigned_system = None
        
        # --- LÓGICA DE CLASIFICACIÓN ---
        
        # 1. ONCOLOGÍA (Prioridad alta por toxicidad)
        if any(k in text for k in SYSTEMS_DATA[4]["keywords"]): # keywords index 4 is Oncología
             # Verificar excepciones (ej: CYP2D6 es oncología solo si menciona tamoxifeno)
             if "tamoxifeno" in text or "tamoxifen" in text or "cancer" in text or "quimio" in text or "irinotecan" in text or "fluorouracil" in text:
                 assigned_system = systems_map["Oncología"]

        # 2. CARDIOLOGÍA (Warfarina, Clopidogrel, Estatinas)
        if not assigned_system:
             if "warfarin" in text or "clopidogrel" in text or "statin" in text or "estatina" in text or "acacenocumarol" in text:
                 assigned_system = systems_map["Cardiología"]
             elif "cyp2c9" in text: # Asumir cardio si es general CYP2C9 (warfarina es lo más común)
                 assigned_system = systems_map["Cardiología"]
             elif "slco1b1" in text or "vkorc1" in text:
                 assigned_system = systems_map["Cardiología"]
             elif "adrb" in text: # Beta receptors
                 assigned_system = systems_map["Cardiología"]

        # 3. GASTROENTEROLOGÍA (Omeprazol, Tacrolimus)
        if not assigned_system:
             if "omeprazol" in text or "lansoprazol" in text or "tacrolimus" in text or "proton" in text or "gastric" in text or "reflujo" in text:
                 assigned_system = systems_map["Gastroenterología"]
             elif "cyp3a5" in text: # Tacrolimus driver
                 assigned_system = systems_map["Gastroenterología"]

        # 4. SALUD ÓSEA Y REUMATOLOGÍA (Alopurinol, Inmunosupresores no trasplante)
        if not assigned_system:
             if "allopurinol" in text or "alopurinol" in text or "gout" in text or "gota" in text or "rheumat" in text or "reumat" in text or "artritis" in text:
                 assigned_system = systems_map["Salud Ósea y Reumatología"]
             elif "tpmt" in text or "nudt15" in text: # Tiopurinas (usadas en reuma/IBD/leucemia - asignamos a Reuma por defecto si no es cancer explicito)
                 assigned_system = systems_map["Salud Ósea y Reumatología"]
             elif "mthfr" in text and ("methotrexate" in text or "metotrexato" in text):
                 assigned_system = systems_map["Salud Ósea y Reumatología"]

        # 5. SALUD MENTAL Y NEUROLOGÍA (El resto de CYP2D6, CYP2C19 si no es clopidogrel/omeprazol)
        if not assigned_system:
             # Keywords explicitas
             if any(k in text for k in ["depress", "depres", "ansied", "anxiet", "psychot", "psicot", "epilep", "pain", "dolor", "opioid", "codein", "sertralin", "citalopram", "venlafaxin"]):
                 assigned_system = systems_map["Salud Mental y Neurología"]
             # Genes drivers por defecto
             elif "cyp2d6" in text: # Si no fue tamoxifeno, es mental/neuro
                 assigned_system = systems_map["Salud Mental y Neurología"]
             elif "cyp2c19" in text: # Si no fue clopidogrel (cardio) ni omeprazol (gastro) -> Antidepresivos
                 assigned_system = systems_map["Salud Mental y Neurología"]
             elif "comt" in text or "oprm1" in text:
                 assigned_system = systems_map["Salud Mental y Neurología"]

        # 6. Fallback / Default
        # Si aun no tiene sistema pero es "Farmacogenética", forzamos asignación basada en heurística final
        if not assigned_system:
             # Si menciona CYP3A4 y no se asignó -> Gastro (metabolismo general) o Cardio.
             if "cyp3a4" in text:
                 assigned_system = systems_map["Gastroenterología"]
             # Si menciona HLA-B -> Reuma (o Neuro si es carbamazepina, pero eso debio caer arriba)
             elif "hla-b" in text:
                 assigned_system = systems_map["Salud Ósea y Reumatología"]
             # Default último recurso: Salud Mental (es la categoría más amplia en farmacogenética comercial)
             # O mejor, lo reportamos como no asignado para revisión manual si es crítico, 
             # pero el usuario pidió "TODOS".
             else:
                 # Asignación por descarte a "Salud Mental y Neurología" ya que suele tener más volumen
                 # O "Cardiología" si suena a gen vascular.
                 # Dejaremos Salud Mental como el bucket "catch-all" para CYP oscuros si no hay mejor pista.
                 assigned_system = systems_map["Salud Mental y Neurología"]
                 print(f"WARNING: Forzando asignación de '{snp.rsid}' ({snp.fenotipo}) a Salud Mental.")

        # Guardar
        if assigned_system:
            snp.pharmacogenetic_system = assigned_system
            snp.save()
            count_assigned += 1
        else:
            count_unassigned += 1
            print(f"ERROR: No se pudo clasificar {snp.rsid} - {snp.fenotipo}")

    print(f"\nResumen: {count_assigned} asignados, {count_unassigned} sin asignar.")

if __name__ == '__main__':
    run()
