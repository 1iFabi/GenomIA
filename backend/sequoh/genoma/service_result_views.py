"""Authenticated local-demo endpoints, separate from every legacy genetic view."""

from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.authentication import JWTAuthentication
from genoma.service_result_reads import get_owned_synthetic_service, list_owned_synthetic_services


class SyntheticServiceListAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        services = list_owned_synthetic_services(request.user)
        return Response({'services': [
            service.summary | {
                'purchased_at': service.purchased_at.isoformat().replace('+00:00', 'Z'),
            } for service in services
        ]})


class SyntheticServiceResultsAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, service_request_id):
        service = get_owned_synthetic_service(request.user, service_request_id)
        if service is None:
            raise NotFound()
        return Response(service.summary | {'results': service.results})


class SyntheticServiceMetricsAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, service_request_id):
        service = get_owned_synthetic_service(request.user, service_request_id)
        if service is None:
            raise NotFound()
        return Response(service.summary | {'metrics': service.metrics})
