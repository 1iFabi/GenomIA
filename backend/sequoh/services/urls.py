from django.urls import path

from services.views import PurchaseCreateAPIView, PurchasePayAPIView, SampleReceiveAPIView

urlpatterns = [
    path('services/purchases/', PurchaseCreateAPIView.as_view(), name='service_purchase_create'),
    path('services/purchases/<uuid:purchase_id>/pay/', PurchasePayAPIView.as_view(), name='service_purchase_pay'),
    path('services/requests/<uuid:request_id>/receive-sample/', SampleReceiveAPIView.as_view(),
         name='service_sample_receive'),
]
