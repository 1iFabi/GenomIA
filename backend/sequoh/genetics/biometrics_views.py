from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from accounts.authentication import JWTAuthentication
from .models import UserSNP
from .utils import build_rsid_extra_info_map
import random
import sys


@method_decorator(csrf_exempt, name='dispatch')
class BiometricsAPIView(APIView):
    """
    Devuelve biometrías simplificadas:
    - matrix 4x3 para mantener compatibilidad
    - variants: lista rsid por rsid del usuario
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        print(f"BiometricsAPIView: Fetching data for user {user.id} ({user.email})", file=sys.stdout)

        from django.db.models import Q

        biom_filter = Q(snp__categoria__icontains="biometr") | Q(snp__grupo__icontains="biometr")
        user_snps = (
            UserSNP.objects.filter(user=user)
            .filter(biom_filter)
            .select_related('snp')
        )

        snp_pool = []
        for us in user_snps:
            if us.snp:
                snp_pool.append(us.snp)
        extra_info_map = build_rsid_extra_info_map(snp_pool)

        has_real_data = len(snp_pool) > 0
        print(f"BiometricsAPIView: Found {len(snp_pool)} SNPs for user {user.id}", file=sys.stdout)

        def compute_impact(snp_obj):
            """Devuelve (nivel_impacto, magnitud_float) de forma segura."""
            try:
                magnitude = float(snp_obj.magnitud_efecto) if snp_obj.magnitud_efecto is not None else 0.0
            except (ValueError, TypeError):
                magnitude = 0.0

            if magnitude >= 3.5:
                return 'high', magnitude
            if magnitude >= 2.0:
                return 'medium', magnitude
            return 'low', magnitude

        rows = ["Metabolismo", "Cardiovascular", "Nutricion", "Deporte"]
        columns = ["Riesgo", "Eficiencia", "Sensibilidad"]

        matrix = []

        random.seed(user.id)
        if has_real_data:
            random.shuffle(snp_pool)

        pool_index = 0
        variants = []

        if has_real_data:
            for snp in snp_pool:
                impact_level, magnitude = compute_impact(snp)
                phenotype_name = (snp.fenotipo or "N/D").strip() or "N/D"
                extra_info = extra_info_map.get((snp.rsid, snp.genotipo, phenotype_name))
                freq_chile = None
                if extra_info and extra_info.freq_chile_percent is not None:
                    try:
                        freq_chile = float(extra_info.freq_chile_percent)
                    except (TypeError, ValueError):
                        freq_chile = None
                variants.append({
                    "rsid": snp.rsid,
                    "genotipo": snp.genotipo,
                    "fenotipo": snp.fenotipo,
                    "categoria": snp.categoria,
                    "grupo": snp.grupo,
                    "cromosoma": snp.cromosoma,
                    "posicion": snp.posicion,
                    "magnitud_efecto": magnitude,
                    "nivel_riesgo": snp.nivel_riesgo,
                    "impact": impact_level,
                    "explanation": snp.fenotipo or f"Variante {snp.rsid}",
                    "freq_chile_percent": freq_chile,
                    "phenotype_description": extra_info.phenotype_description if extra_info else None,
                })

            for row_idx, row in enumerate(rows):
                row_data = {"name": row, "cells": []}
                for col_idx, col in enumerate(columns):
                    snp = snp_pool[pool_index % len(snp_pool)]
                    pool_index += 1

                    impact_level, magnitude = compute_impact(snp)

                    if col == "Riesgo":
                        context = "Predisposicion genetica base"
                    elif col == "Eficiencia":
                        context = "Velocidad de procesamiento"
                    else:
                        context = "Respuesta a estimulos"

                    explanation = f"{context}: {snp.rsid}"

                    cell_data = {
                        "column": col,
                        "impact": impact_level,
                        "explanation": explanation,
                    }
                    row_data["cells"].append(cell_data)
                matrix.append(row_data)

        return Response({
            "success": True,
            "data": {
                "rows": rows,
                "columns": columns,
                "matrix": matrix,
                "variants": variants,
            }
        })
