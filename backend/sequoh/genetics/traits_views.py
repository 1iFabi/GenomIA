from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from accounts.authentication import JWTAuthentication
from .models import UserSNP, SNP
from .utils import build_rsid_extra_info_map
import random

@method_decorator(csrf_exempt, name='dispatch')
class TraitsAPIView(APIView):
    """
    Retorna los rasgos genéticos del usuario autenticado.
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        
        # Obtener todos los SNPs de rasgos del usuario
        user_snps = UserSNP.objects.filter(
            user=user,
            snp__categoria='rasgos'
        ).select_related('snp')

        snp_list = [us.snp for us in user_snps if us.snp]
        extra_info_map = build_rsid_extra_info_map(snp_list)
        
        traits_list = []
        
        for user_snp in user_snps:
            snp = user_snp.snp
            phenotype_name = (snp.fenotipo or "N/D").strip() or "N/D"
            extra_info = extra_info_map.get((snp.rsid, snp.genotipo, phenotype_name))
            freq_chile = None
            if extra_info and extra_info.freq_chile_percent is not None:
                try:
                    freq_chile = float(extra_info.freq_chile_percent)
                except (TypeError, ValueError):
                    freq_chile = None
            
            magnitud_efecto = float(snp.magnitud_efecto) if snp.magnitud_efecto else 0.0
            percentage = int(min(100, (magnitud_efecto / 5.0) * 100))
            
            # Asignar grupo desde el nuevo campo en la base de datos
            group = snp.grupo or 'Rasgos'

            trait_obj = {
                'id': snp.id,
                'rsid': snp.rsid,
                'genotipo': snp.genotipo,
                'fenotipo': snp.fenotipo,
                'cromosoma': snp.cromosoma,
                'posicion': snp.posicion,
                'magnitud_efecto': magnitud_efecto,
                'group': group,
                'percentage': percentage,
                'nivel_riesgo': snp.nivel_riesgo,
                'freq_chile_percent': freq_chile,
                'phenotype_description': extra_info.phenotype_description if extra_info else None,
            }
            traits_list.append(trait_obj)
        
        return Response({
            'success': True,
            'data': {
                'traits': traits_list
            },
            'total_traits': len(traits_list)
        })
