from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.db.models import Count, Sum
from accounts.authentication import JWTAuthentication
from .models import UserSNP, SNP
from decimal import Decimal


@method_decorator(csrf_exempt, name='dispatch')
class IndigenousPeoplesAPIView(APIView):
    """
    Returns indigenous peoples ancestry data for Chile.
    Filters SNPs where country is Chile and analyzes indigenous population data.
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        
        # Get all SNPs associated with user and filtered by Chile
        user_snps = UserSNP.objects.filter(
            user=user,
            snp__pais__iexact='Chile'
        ).select_related('snp')
        
        if not user_snps.exists():
            # Return default/empty data if no SNPs found for Chile
            return Response({
                'success': True,
                'data': {
                    'indigenous_peoples': [],
                    'total_variants': 0,
                    'message': 'No hay datos de pueblos indígenas disponibles.'
                }
            })
        
        # Aggregate data by indigenous population dynamically using what exists in the SNP catalog
        aggregates = user_snps.values('snp__poblacion_pais').annotate(
            count=Count('snp'),
            avg_frequency=Sum('snp__af_pais') / Count('snp')
        ).order_by('-count')

        def normalize_name(raw_name):
            """Fix encoding/underscore issues and standardize names for display."""
            if not raw_name:
                return 'Desconocido'
            name = raw_name.replace('_', ' ').strip()
            fixes = {
                'Aimara': 'Aymara',
                'Aymara': 'Aymara',
                'Atacameño': 'Atacameño',
                'Diaguita': 'Diaguita',
                'Mapuche': 'Mapuche',
                'Rapa Nui': 'Rapa Nui',
                'Chileno_general': 'Chileno general',
            }
            return fixes.get(name, name)

        total_count = sum(item['count'] for item in aggregates)
        results = []
        for item in aggregates:
            name = normalize_name(item['snp__poblacion_pais'])
            avg_freq = item['avg_frequency'] or Decimal('0')
            percentage = round(float((item['count'] / total_count * 100) if total_count > 0 else 0), 2)
            results.append({
                'name': name,
                'percentage': percentage,
                'variant_count': item['count'],
                'avg_allele_frequency': float(avg_freq)
            })
        
        # Get total unique SNPs
        total_variants = user_snps.count()
        
        return Response({
            'success': True,
            'data': {
                'indigenous_peoples': results,
                'total_variants': total_variants,
                'country': 'Chile',
                'user': {
                    'id': user.id,
                    'email': user.email,
                    'name': f"{user.first_name} {user.last_name}".strip() or user.username
                }
            }
        })
