from django.urls import path

from services.views import PurchaseCreateAPIView, PurchasePayAPIView

urlpatterns = [
    path('services/purchases/', PurchaseCreateAPIView.as_view(), name='service_purchase_create'),
    path('services/purchases/<uuid:purchase_id>/pay/', PurchasePayAPIView.as_view(), name='service_purchase_pay'),
]
