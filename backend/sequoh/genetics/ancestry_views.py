from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.db.models import Count, Sum, F
from accounts.authentication import JWTAuthentication
from .models import UserSNP, SNP
from decimal import Decimal


@method_decorator(csrf_exempt, name='dispatch')
class AncestryAPIView(APIView):
    """
    Returns ancestry composition data for authenticated user.
    Analyzes user's SNPs and aggregates continental/country data.
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        
        # Get all SNPs associated with user
        user_snps = UserSNP.objects.filter(user=user).select_related('snp')
        
        if not user_snps.exists():
            # Return default/empty ancestry data if no SNPs found
            return Response({
                'success': True,
                'data': {
                    'continents': [],
                    'countries': [],
                    'total_variants': 0,
                    'message': 'No hay datos de ancestría disponibles aún.'
                }
            })
        
        # Aggregate continental ancestry data, excluding null and empty strings
        continental_data = user_snps.filter(
            snp__continente__isnull=False
        ).exclude(
            snp__continente__exact=''
        ).values('snp__continente').annotate(
            count=Count('snp'),
            avg_frequency=Sum('snp__af_continente') / Count('snp')
        ).order_by('-count')
        
        # Aggregate country ancestry data, excluding null and empty strings
        country_data = user_snps.filter(
            snp__pais__isnull=False
        ).exclude(
            snp__pais__exact=''
        ).values('snp__pais').annotate(
            count=Count('snp'),
            avg_frequency=Sum('snp__af_pais') / Count('snp'),
            continente=F('snp__continente')
        ).order_by('-count')
        
        # Process continental data
        continents = []
        total_continental_sum = sum(item['count'] for item in continental_data)
        
        for item in continental_data:
            continent_name = item['snp__continente'] or 'Unknown'
            count = item['count']
            avg_freq = item['avg_frequency'] or Decimal('0')
            percentage = round(float((count / total_continental_sum * 100) if total_continental_sum > 0 else 0), 2)
            
            continents.append({
                'name': continent_name,
                'percentage': percentage,
                'variant_count': count,
                'avg_allele_frequency': float(avg_freq)
            })
        
        # Sort by percentage descending
        continents.sort(key=lambda x: x['percentage'], reverse=True)
        
        # Process country data
        countries = []
        total_country_sum = sum(item['count'] for item in country_data)
        
        for item in country_data:
            country_name = item['snp__pais'] or 'Unknown'
            count = item['count']
            avg_freq = item['avg_frequency'] or Decimal('0')
            continent = item['continente'] or 'Unknown'
            # Calculate percentage based on count proportion to ensure 100% total
            percentage = round(float((count / total_country_sum * 100) if total_country_sum > 0 else 0), 2)
            
            countries.append({
                'name': country_name,
                'continent': continent,
                'percentage': percentage,
                'variant_count': count,
                'avg_allele_frequency': float(avg_freq)
            })
        
        # Sort by percentage descending
        countries.sort(key=lambda x: x['percentage'], reverse=True)
        
        # Normalize to exactly 100% if needed
        if countries:
            current_total = sum(c['percentage'] for c in countries)
            if current_total > 0 and abs(current_total - 100.0) > 0.01:
                # Adjust the largest percentage to make total exactly 100%
                adjustment = 100.0 - current_total
                if countries[0]['percentage'] + adjustment > 0:
                    countries[0]['percentage'] = round(countries[0]['percentage'] + adjustment, 2)
        
        # Get total unique SNPs
        total_variants = user_snps.count()
        
        return Response({
            'success': True,
            'data': {
                'continents': continents,
                'countries': countries,
                'total_variants': total_variants,
                'user': {
                    'id': user.id,
                    'email': user.email,
                    'name': f"{user.first_name} {user.last_name}".strip() or user.username
                }
            }
        })