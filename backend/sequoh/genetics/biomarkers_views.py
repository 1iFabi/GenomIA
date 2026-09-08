from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Q
from accounts.authentication import JWTAuthentication
from .models import UserSNP, SNP
from .utils import build_rsid_extra_info_map
import sys


@method_decorator(csrf_exempt, name='dispatch')
class BiomarkersAPIView(APIView):
    """
    Retorna biomarcadores (SNPs) del usuario filtrando categoria/grupo que contenga 'biomarc'.
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        print(f"BiomarkersAPIView: Fetching biomarkers for user {user.id} ({user.email})", file=sys.stdout)

        biom_filter = Q(snp__categoria__icontains="biomarc") | Q(snp__grupo__icontains="biomarc")
        user_snps = (
            UserSNP.objects.filter(user=user)
            .filter(biom_filter)
            .select_related("snp")
        )
        snp_list = [us.snp for us in user_snps if us.snp]
        extra_info_map = build_rsid_extra_info_map(snp_list)

        # Contar total global de biomarcadores disponibles en la base de datos
        global_filter = Q(categoria__icontains="biomarc") | Q(grupo__icontains="biomarc")
        global_total = SNP.objects.filter(global_filter).count()

        biomarkers = []
        risk_counts = {"bajo": 0, "medio": 0, "alto": 0}

        for us in user_snps:
            snp = us.snp
            if not snp:
                continue

            try:
                magnitude = float(snp.magnitud_efecto) if snp.magnitud_efecto is not None else None
            except (ValueError, TypeError):
                magnitude = None

            risk = (snp.nivel_riesgo or "").strip().lower()
            if risk in risk_counts:
                risk_counts[risk] += 1

            phenotype_name = (snp.fenotipo or "N/D").strip() or "N/D"
            extra_info = extra_info_map.get((snp.rsid, snp.genotipo, phenotype_name))
            frequency_val = None
            if extra_info and extra_info.freq_chile_percent is not None:
                try:
                    frequency_val = float(extra_info.freq_chile_percent)
                except (TypeError, ValueError):
                    frequency_val = None

            biomarkers.append({
                "id": snp.rsid,
                "rsid": snp.rsid,
                "gene": snp.grupo or snp.categoria or "NA",
                "name": snp.fenotipo or "Biomarcador",
                "chromosome": snp.cromosoma or "",
                "position": snp.posicion,
                "userGenotype": snp.genotipo,
                "alleles": {
                    "ref": snp.alelo_referencia,
                    "alt": snp.alelo_alternativo,
                },
                "userResult": {
                    "genotype": snp.genotipo,
                    "phenotype": snp.fenotipo,
                    "risk": risk or "medio",
                    "magnitude": magnitude,
                    "frequency": frequency_val,
                    "phenotype_description": extra_info.phenotype_description if extra_info else None,
                    "continent": snp.continente,
                    "country": snp.pais,
                },
                "freq_chile_percent": frequency_val,
                "phenotype_description": extra_info.phenotype_description if extra_info else None,
                "allGenotypes": [
                    {
                        "genotype": snp.genotipo,
                        "phenotype": snp.fenotipo,
                        "risk": (risk or "medio"),
                        "frequency": frequency_val,
                    }
                ],
            })

        return Response({
            "success": True,
            "total": len(biomarkers),
            "global_total": global_total,
            "risk_distribution": risk_counts,
            "biomarkers": biomarkers,
        })
