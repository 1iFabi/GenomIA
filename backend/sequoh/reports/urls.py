from django.urls import path
from .views import UserReportPDFView

urlpatterns = [
    path('report/pdf/', UserReportPDFView.as_view(), name='api_report_pdf'),
]
