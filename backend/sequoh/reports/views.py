from django.http import JsonResponse
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView


class UserReportPDFView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        return JsonResponse({
            "code": "pdf_report_unavailable",
            "detail": "El reporte PDF estará disponible cuando los resultados hayan sido revisados y publicados.",
        }, status=503)
