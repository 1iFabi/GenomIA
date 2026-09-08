from django.urls import path
from .views import (
    ReceptionSearchAPIView,
    ReceptionArrivalAPIView,
    ReceptionSampleCodeAPIView,
    ReceptionSampleStatusAPIView,
)

urlpatterns = [
    path('reception/search/', ReceptionSearchAPIView.as_view(), name='api_reception_search'),
    path('reception/arrival/', ReceptionArrivalAPIView.as_view(), name='api_reception_arrival'),
    path('reception/sample-code/', ReceptionSampleCodeAPIView.as_view(), name='api_reception_sample_code'),
    path('reception/sample-status/', ReceptionSampleStatusAPIView.as_view(), name='api_reception_sample_status'),
]
