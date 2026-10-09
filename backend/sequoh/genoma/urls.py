from django.urls import path
from .client_results import AncestryCohortAPIView, ClientResultsAPIView
from .service_result_views import (
    SyntheticServiceListAPIView, SyntheticServiceMetricsAPIView, SyntheticServiceResultsAPIView,
)

urlpatterns = [
    path('genoma/v1/results/', ClientResultsAPIView.as_view(), name='api_genoma_v1_client_results'),
    path('genoma/v1/results/ancestry-cohort/', AncestryCohortAPIView.as_view(),
         name='api_genoma_v1_ancestry_cohort'),
    # Local-only bundled synthetic v1 reads; no legacy projections or counters.
    path('genoma/v1/services/', SyntheticServiceListAPIView.as_view(), name='api_genoma_v1_services'),
    path('genoma/v1/services/<str:service_request_id>/results/',
         SyntheticServiceResultsAPIView.as_view(), name='api_genoma_v1_service_results'),
    path('genoma/v1/services/<str:service_request_id>/metrics/',
         SyntheticServiceMetricsAPIView.as_view(), name='api_genoma_v1_service_metrics'),
]
