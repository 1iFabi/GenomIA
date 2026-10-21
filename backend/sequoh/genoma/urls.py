from django.urls import path
from .client_results import AncestryCohortAPIView, ClientResultsAPIView

urlpatterns = [
    path('genoma/v1/results/', ClientResultsAPIView.as_view(), name='api_genoma_v1_client_results'),
    path('genoma/v1/results/ancestry-cohort/', AncestryCohortAPIView.as_view(),
         name='api_genoma_v1_ancestry_cohort'),
]
