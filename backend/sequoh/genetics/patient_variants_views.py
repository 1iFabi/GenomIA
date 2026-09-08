from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.contrib.auth import get_user_model
from accounts.authentication import JWTAuthentication
from .models import UserSNP, SNP
from accounts.roles import is_admin_or_analyst

User = get_user_model()


@method_decorator(csrf_exempt, name='dispatch')
class PatientVariantsAPIView(APIView):
    """
    Retorna todas las variantes genéticas asociadas a un paciente específico.
    Solo accesible para administradores.
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, user_id):
        # Verificar que el usuario autenticado es admin/staff
        if not is_admin_or_analyst(request.user):
            return Response({
                'success': False,
                'error': 'No tienes permisos para acceder a esta información'
            }, status=403)
        
        # Verificar que el usuario existe
        try:
            patient = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Usuario no encontrado'
            }, status=404)
        
        # Obtener todas las variantes del usuario
        user_snps = UserSNP.objects.filter(
            user=patient
        ).select_related('snp').order_by('-snp__magnitud_efecto', 'snp__cromosoma', 'snp__posicion')
        
        # Formatear datos
        variants = []
        for user_snp in user_snps:
            snp = user_snp.snp
            variants.append({
                'rsid': snp.rsid,
                'cromosoma': snp.cromosoma,
                'posicion': snp.posicion,
                'genotipo': snp.genotipo,
                'fenotipo': snp.fenotipo,
                'categoria': snp.categoria,
                'alelo_referencia': snp.alelo_referencia,
                'alelo_alternativo': snp.alelo_alternativo,
                'nivel_riesgo': snp.nivel_riesgo,
                'magnitud_efecto': float(snp.magnitud_efecto) if snp.magnitud_efecto else 0.0,
                'fuente_base_datos': snp.fuente_base_datos,
                'tipo_evidencia': snp.tipo_evidencia,
                'fecha_actualizacion': snp.fecha_actualizacion if isinstance(snp.fecha_actualizacion, str) else (snp.fecha_actualizacion.strftime('%Y-%m-%d') if snp.fecha_actualizacion else None)
            })
        
        return Response({
            'success': True,
            'data': {
                'patient': {
                    'id': patient.id,
                    'name': f"{patient.first_name} {patient.last_name}".strip() or patient.username,
                    'email': patient.email,
                },
                'variants': variants,
                'total_variants': len(variants)
            }
        })
