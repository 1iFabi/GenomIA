from django.urls import path

from services.views import AdvanceServiceStatusAPIView, ConfirmPaymentAPIView

urlpatterns = [
    path('services/payments/', ConfirmPaymentAPIView.as_view(), name='service_payment_confirm'),
    path('services/requests/<uuid:request_id>/advance/', AdvanceServiceStatusAPIView.as_view(),
         name='service_status_advance'),
]
