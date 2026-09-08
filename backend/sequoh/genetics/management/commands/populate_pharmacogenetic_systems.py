from django.core.management.base import BaseCommand
from django.db import transaction
from genetics.models import SNP, PharmacogeneticSystem


SYSTEM_RULES = [
    ("Cardiologia", ["cardio", "warfar", "clopidogrel", "estat", "asa", "aspirina", "anticoag", "antiagreg"]),
    ("Salud Mental y Neurologia", ["psiq", "depres", "ansied", "neurol", "ssri", "snri", "parox", "sertral", "fluox", "antipsi"]),
    ("Gastroenterologia", ["gastro", "prazol", "omepraz", "pantopraz", "reflujo", "ulcera"]),
    ("Salud Osea y Reumatologia", ["osea", "hueso", "reuma", "osteop", "vit d", "calcio"]),
    ("Oncologia", ["onco", "tumor", "cancer", "leucem", "quimio", "chemo"]),
]


def resolve_system_id(systems_by_name, snp):
    """Determina el sistema según FK existente o heurística por texto."""
    if snp.pharmacogenetic_system_id:
        return snp.pharmacogenetic_system_id

    text = " ".join([
        str(getattr(snp, 'grupo', '') or ''),
        str(getattr(snp, 'categoria', '') or ''),
        str(getattr(snp, 'fenotipo', '') or '')
    ]).lower()

    for name, keywords in SYSTEM_RULES:
        if any(k in text for k in keywords):
            return systems_by_name.get(name.lower())
    return None


class Command(BaseCommand):
    help = "Asigna pharmacogenetic_system a SNPs de farmacogenetica usando heurística."

    def handle(self, *args, **options):
        with transaction.atomic():
            systems_by_name = {}
            for name, _ in SYSTEM_RULES:
                sys_obj, _ = PharmacogeneticSystem.objects.get_or_create(name=name)
                systems_by_name[name.lower()] = sys_obj.id

            pharm_snps = SNP.objects.filter(
                categoria__icontains="farmaco"
            ) | SNP.objects.filter(grupo__icontains="farmaco")
            updated = 0
            for snp in pharm_snps:
                sys_id = resolve_system_id(systems_by_name, snp)
                if sys_id and snp.pharmacogenetic_system_id != sys_id:
                    snp.pharmacogenetic_system_id = sys_id
                    snp.save(update_fields=["pharmacogenetic_system"])
                    updated += 1

        self.stdout.write(self.style.SUCCESS(f"Actualizados {updated} SNPs con sistema farmacogenetico."))
