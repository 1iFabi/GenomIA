from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from accounts.authentication import JWTAuthentication
from .models import UserSNP, SNP
from .utils import build_rsid_extra_info_map
from collections import defaultdict
import re


@method_decorator(csrf_exempt, name='dispatch')
class DiseasesAPIView(APIView):
    """
    Retorna las enfermedades y sus SNPs asociados al usuario autenticado.
    Agrupa por enfermedad y prioriza por nivel de riesgo.
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def _extract_gene_name(self, fenotipo):
        """
        Extrae el nombre del gen del campo fenotipo.
        Busca patrones como 'GENE_NAME increased' o 'GENE_NAME decreased'
        """
        if not fenotipo:
            return 'Unknown'
        
        # Buscar palabras en mayúsculas al principio (típico nombre de gen)
        match = re.match(r'^([A-Z][A-Z0-9\-]*)', fenotipo.strip())
        if match:
            return match.group(1)
        
        # Si no encuentra patrón, devolver Unknown
        return 'Unknown'

    def get(self, request):
        user = request.user
        
        # Obtener todos los SNPs de enfermedades del usuario
        # La categoría en BD es "enfermedades" en minúsculas
        user_snps = UserSNP.objects.filter(
            user=user,
            snp__categoria='enfermedades'
        ).select_related('snp')

        snp_list = [us.snp for us in user_snps if us.snp]
        extra_info_map = build_rsid_extra_info_map(snp_list)
        
        # Organizar SNPs por prioridad basado en nivel_riesgo
        # Clasificación simple: Alto, Intermedio, Bajo
        snps_by_priority = {
            'alta': [],      # Alto
            'media': [],     # Intermedio
            'baja': []       # Bajo
        }
        
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
            
            # Usar nivel_riesgo y magnitud_efecto
            nivel_riesgo = snp.nivel_riesgo or 'Bajo'
            magnitud_efecto = float(snp.magnitud_efecto) if snp.magnitud_efecto else 0.0
            
            # Extraer nombre del gen del fenotipo
            gen_name = self._extract_gene_name(snp.fenotipo)
            
            snp_obj = {
                'rsid': snp.rsid,
                'genotipo': snp.genotipo,
                'fenotipo': snp.fenotipo,
                'cromosoma': snp.cromosoma,
                'posicion': snp.posicion,
                'gen': gen_name,
                'nivel_riesgo': nivel_riesgo,
                'magnitud_efecto': magnitud_efecto,
                'fuente': snp.fuente_base_datos,
                'tipo_evidencia': snp.tipo_evidencia,
                'freq_chile_percent': freq_chile,
                'phenotype_description': extra_info.phenotype_description if extra_info else None,
            }
            
            # Clasificar por prioridad basado en nivel_riesgo
            # Solo considerar: Alto, Intermedio, Bajo
            nivel_lower = nivel_riesgo.lower()
            
            if 'alto' in nivel_lower:
                snps_by_priority['alta'].append(snp_obj)
            elif 'intermedi' in nivel_lower:
                snps_by_priority['media'].append(snp_obj)
            else:
                # Bajo y cualquier otro
                snps_by_priority['baja'].append(snp_obj)
        
        # Ordenar cada categoría por magnitud de efecto descendente
        for priority in snps_by_priority:
            snps_by_priority[priority].sort(
                key=lambda x: x['magnitud_efecto'],
                reverse=True
            )
        
        return Response({
            'success': True,
            'data': snps_by_priority,
            'total_snps': len(user_snps)
        })
    
