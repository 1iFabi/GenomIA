from django.urls import path
from .views import ReceptionSearchAPIView, ReceptionVerifyRutAPIView

urlpatterns = [
    path('reception/search/', ReceptionSearchAPIView.as_view(), name='api_reception_search'),
    path('reception/verify-rut/', ReceptionVerifyRutAPIView.as_view(), name='api_reception_verify_rut'),
]
