from django.urls import path
from .views import ReceptionSearchAPIView

urlpatterns = [
    path('reception/search/', ReceptionSearchAPIView.as_view(), name='api_reception_search'),
]
