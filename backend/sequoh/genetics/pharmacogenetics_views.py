import unicodedata
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q
from accounts.authentication import JWTAuthentication
from .models import UserSNP, PharmacogeneticSystem
from .utils import build_rsid_extra_info_map


def _normalize(text: str) -> str:
    """Lowercase, remove diacritics and collapse spaces."""
    if not text:
        return ""
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return " ".join(text.lower().split())


def _hash_color_index(text: str, modulo: int) -> int:
    h = 0
    for ch in text:
        h = ((h << 5) - h) + ord(ch)
        h &= 0xFFFFFFFF
    return abs(h) % max(1, modulo)


class PharmacogeneticsAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        systems = list(PharmacogeneticSystem.objects.all().order_by("id"))
        base_palette = ['#F48FB1', '#00BCD4', '#9C27B0', '#3F51B5', '#FF5722', '#4CAF50', '#FFC107']
        fallback_palette = ['#0ea5e9', '#f97316', '#22c55e', '#a855f7', '#6366f1', '#14b8a6', '#f43f5e', '#f59e0b']

        # Colores indexados por nombre normalizado
        system_color_by_name = {}
        system_color_by_id = {}
        for idx, sys in enumerate(systems):
            key = _normalize(sys.name)
            color = base_palette[idx % len(base_palette)]
            system_color_by_name[key] = color
            system_color_by_id[sys.id] = color
        system_color_by_name['otros'] = '#607D8B'

        heuristics = [
            ('Cardiologia', ['cardio', 'warfar', 'clopidogrel', 'estat', 'asa', 'aspirina', 'anticoag', 'antiagreg']),
            ('Salud Mental y Neurologia', ['psiq', 'depres', 'ansied', 'neurol', 'ssri', 'snri', 'parox', 'sertral', 'fluox', 'antipsi']),
            ('Gastroenterologia', ['gastro', 'prazol', 'omepraz', 'pantopraz', 'reflujo', 'ulcera']),
            ('Salud Osea y Reumatologia', ['osea', 'hueso', 'reuma', 'osteop', 'vit d', 'calcio']),
            ('Oncologia', ['onco', 'tumor', 'cancer', 'leucem', 'quimio', 'chemo']),
        ]
        heuristics_norm = [(_normalize(name), [k.lower() for k in keys]) for name, keys in heuristics]
        # Asegurar color para heurísticas aunque no existan sistemas en DB
        for name_norm, _ in heuristics_norm:
            if name_norm not in system_color_by_name:
                idx = len(system_color_by_name)
                system_color_by_name[name_norm] = base_palette[idx % len(base_palette)]

        pharm_filter = Q(snp__categoria__icontains='farmaco') | Q(snp__grupo__icontains='farmaco')
        user_snps = (
            UserSNP.objects.filter(user=user)
            .filter(pharm_filter)
            .select_related('snp', 'snp__pharmacogenetic_system')
        )
        snp_list = [us.snp for us in user_snps if us.snp]
        extra_info_map = build_rsid_extra_info_map(snp_list)

        best_by_key = {}

        def resolve_system(snp):
            # 1) FK explícita
            if snp.pharmacogenetic_system_id:
                s = next((x for x in systems if x.id == snp.pharmacogenetic_system_id), None)
                if s:
                    name = s.name
                    norm = _normalize(name)
                    color = system_color_by_id.get(s.id) or system_color_by_name.get(norm, '#607D8B')
                    return norm, name, s.description or f"Analisis de farmacos para {name}", color

            # 2) Heurística
            raw_parts = [
                str(getattr(snp, 'grupo', '') or ''),
                str(getattr(snp, 'categoria', '') or ''),
                str(getattr(snp, 'fenotipo', '') or '')
            ]
            text_norm = _normalize(" ".join(raw_parts))
            for name_norm, keys in heuristics_norm:
                if any(k in text_norm for k in keys):
                    color = system_color_by_name.get(name_norm) or fallback_palette[_hash_color_index(name_norm, len(fallback_palette))]
                    pretty = name_norm.title()
                    return name_norm, pretty, f"Analisis de farmacos para {pretty}", color

            # 3) Usar categoria/grupo como sistema dinámico para evitar colapsar en "Otros"
            cat = (snp.categoria or snp.grupo or "Otros").strip() or "Otros"
            name_norm = _normalize(cat)
            color = system_color_by_name.get(name_norm) or fallback_palette[_hash_color_index(name_norm, len(fallback_palette))]
            return name_norm or 'otros', cat or 'Otros', cat or 'Farmacos sin sistema asignado', color

        for us in user_snps:
            snp = us.snp
            if not snp:
                continue

            phenotype_name = (snp.fenotipo or "N/D").strip() or "N/D"
            extra_info = extra_info_map.get((snp.rsid, snp.genotipo, phenotype_name))
            freq_chile = None
            if extra_info and extra_info.freq_chile_percent is not None:
                try:
                    freq_chile = float(extra_info.freq_chile_percent)
                except (TypeError, ValueError):
                    freq_chile = None

            raw = (snp.fenotipo or "").strip()
            name = raw.split("(")[0].strip() or snp.rsid or "Farmaco"

            sys_key, sys_name, sys_desc, sys_color = resolve_system(snp)

            try:
                magn = float(snp.magnitud_efecto) if snp.magnitud_efecto is not None else 1.5
            except Exception:
                magn = 1.5
            percentage = max(1, min(100, int((magn / 3.0) * 100)))

            dedup_key = (sys_key, snp.rsid or "", snp.genotipo or "")
            current = best_by_key.get(dedup_key)
            if current is None or magn > current["magnitud"]:
                best_by_key[dedup_key] = {
                    "name": name,
                    "percentage": percentage,
                    "rsid": snp.rsid,
                    "cromosoma": snp.cromosoma,
                    "posicion": str(snp.posicion or ""),
                    "genotipo": snp.genotipo,
                    "magnitud": magn,
                    "fenotipo": raw or name,
                    "freq_chile_percent": freq_chile,
                    "phenotype_description": extra_info.phenotype_description if extra_info else None,
                    "system_key": sys_key,
                    "system_name": sys_name,
                    "system_desc": sys_desc,
                    "system_color": sys_color,
                }

        buckets = {}
        for data in best_by_key.values():
            buckets.setdefault(data["system_key"], []).append(data)

        result = []
        for sys_key, drugs in buckets.items():
            if not drugs:
                continue
            meta = drugs[0]
            result.append({
                "name": meta.get("system_name", "Otros"),
                "role": meta.get("system_desc", "Farmacos sin sistema asignado"),
                "color": meta.get("system_color", system_color_by_name.get(sys_key, '#607D8B')),
                "drugs": drugs,
            })

        return Response({"success": True, "data": result})
