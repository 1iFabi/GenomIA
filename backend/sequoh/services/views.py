from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.authentication import JWTAuthentication
from accounts.csrf import CSRFDoubleSubmitMixin
from accounts.models import AppUser, Role
from accounts.roles import is_admin_or_reception
from participants.models import Participant
from services.models import Purchase, PurchaseStatus, ServiceRequest, ServiceStatus, ServiceStatusLog


class PurchaseCreateAPIView(CSRFDoubleSubmitMixin, APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not is_admin_or_reception(request.user):
            return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
        if not isinstance(request.data, dict) or set(request.data) != {'userId'}:
            return Response({'error': 'Only userId is required'}, status=status.HTTP_400_BAD_REQUEST)
        user_id = request.data['userId']
        if type(user_id) is not int or user_id <= 0:
            return Response({'error': 'Invalid userId'}, status=status.HTTP_400_BAD_REQUEST)
        owner = AppUser.objects.filter(
            django_user_id=user_id, django_user__is_active=True, role__code=Role.Code.CLIENTE,
        ).first()
        if owner is None:
            return Response({'error': 'Client not found'}, status=status.HTTP_404_NOT_FOUND)
        pending = PurchaseStatus.objects.filter(code='PENDING').first()
        if pending is None:
            return Response({'error': 'Purchase status unavailable'}, status=status.HTTP_409_CONFLICT)
        purchase = Purchase.objects.create(owner=owner, status=pending)
        return Response({'purchaseId': purchase.pk, 'status': 'PENDING'}, status=status.HTTP_201_CREATED)


class PurchasePayAPIView(CSRFDoubleSubmitMixin, APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, purchase_id):
        if not is_admin_or_reception(request.user):
            return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
        if not isinstance(request.data, dict) or request.data:
            return Response({'error': 'Payment does not accept fields'}, status=status.HTTP_400_BAD_REQUEST)
        with transaction.atomic():
            actor = AppUser.objects.select_for_update(of=('self',)).filter(
                django_user_id=request.user.pk, role__code__in=[Role.Code.ADMIN, Role.Code.RECEPCION],
            ).first()
            if actor is None:
                return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
            purchase = Purchase.objects.select_for_update(of=('self',)).select_related('status').filter(
                pk=purchase_id,
            ).first()
            if purchase is None:
                return Response({'error': 'Purchase not found'}, status=status.HTTP_404_NOT_FOUND)
            owner = AppUser.objects.select_for_update(of=('self',)).filter(
                pk=purchase.owner_id, django_user__is_active=True, role__code=Role.Code.CLIENTE,
            ).first()
            if owner is None:
                return Response({'error': 'Purchase not found'}, status=status.HTTP_404_NOT_FOUND)
            code = purchase.status.code if purchase.status_id else None
            if code == 'PAID':
                service = ServiceRequest.objects.filter(purchase=purchase).first()
                log = (ServiceStatusLog.objects.filter(request=service, status__code='WAITING_SAMPLE')
                       .order_by('changed_at', 'pk').first()) if service else None
                if service is None or log is None or purchase.purchased_at is None:
                    return Response({'error': 'Inconsistent paid purchase'}, status=status.HTTP_409_CONFLICT)
            elif code == 'PENDING':
                paid = PurchaseStatus.objects.filter(code='PAID').first()
                waiting = ServiceStatus.objects.filter(code='WAITING_SAMPLE').first()
                if paid is None or waiting is None or ServiceRequest.objects.filter(purchase=purchase).exists():
                    return Response({'error': 'Purchase cannot be paid'}, status=status.HTTP_409_CONFLICT)
                purchase.status = paid
                purchase.purchased_at = timezone.now()
                purchase.save(update_fields=['status', 'purchased_at'])
                participant = Participant.objects.filter(user_id=owner.django_user_id).first()
                try:
                    service = ServiceRequest.objects.create(
                        purchase=purchase, participant=participant, status=waiting,
                    )
                    log = ServiceStatusLog.objects.create(request=service, status=waiting, actor=actor)
                except IntegrityError:
                    # A competing direct insert can still hit the purchase's unique request key.
                    transaction.set_rollback(True)
                    return Response({'error': 'Purchase cannot be paid'}, status=status.HTTP_409_CONFLICT)
            else:
                return Response({'error': 'Purchase cannot be paid'}, status=status.HTTP_409_CONFLICT)
            return Response({
                'purchaseId': purchase.pk, 'status': 'PAID',
                'purchasedAt': purchase.purchased_at.isoformat().replace('+00:00', 'Z'),
                'serviceRequestId': service.pk, 'statusLogId': log.pk,
            })


class SampleReceiveAPIView(CSRFDoubleSubmitMixin, APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, request_id):
        if not is_admin_or_reception(request.user):
            return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
        if not isinstance(request.data, dict) or request.data:
            return Response({'error': 'Sample reception does not accept fields'}, status=status.HTTP_400_BAD_REQUEST)
        with transaction.atomic():
            actor = AppUser.objects.select_for_update(of=('self',)).filter(
                django_user_id=request.user.pk, role__code__in=[Role.Code.ADMIN, Role.Code.RECEPCION],
            ).first()
            if actor is None:
                return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
            service = ServiceRequest.objects.select_for_update(of=('self',)).select_related('status').filter(
                pk=request_id,
            ).first()
            if service is None:
                return Response({'error': 'Service request not found'}, status=status.HTTP_404_NOT_FOUND)
            purchase = Purchase.objects.select_for_update(of=('self',)).select_related('status').get(
                pk=service.purchase_id,
            )
            owner = AppUser.objects.select_for_update(of=('self',)).filter(
                pk=purchase.owner_id, django_user__is_active=True, role__code=Role.Code.CLIENTE,
            ).first()
            if owner is None or (service.participant_id is not None and not Participant.objects.filter(
                pk=service.participant_id, user_id=owner.django_user_id,
            ).exists()):
                return Response({'error': 'Service request not found'}, status=status.HTTP_404_NOT_FOUND)
            if purchase.status is None or purchase.status.code != 'PAID' or purchase.purchased_at is None:
                return Response({'error': 'Service is not paid'}, status=status.HTTP_409_CONFLICT)
            if service.status.code in ('WAITING_SAMPLE', 'SAMPLE_RECEIVED') and not ServiceStatusLog.objects.filter(
                request=service, status__code='WAITING_SAMPLE',
            ).exists():
                return Response({'error': 'Missing payment log'}, status=status.HTTP_409_CONFLICT)
            if service.status.code == 'SAMPLE_RECEIVED':
                log = ServiceStatusLog.objects.filter(
                    request=service, status=service.status,
                ).order_by('changed_at', 'pk').first()
                if log is None:
                    return Response({'error': 'Missing reception log'}, status=status.HTTP_409_CONFLICT)
            elif service.status.code == 'WAITING_SAMPLE':
                received = ServiceStatus.objects.filter(code='SAMPLE_RECEIVED').first()
                if received is None:
                    return Response({'error': 'Service status unavailable'}, status=status.HTTP_409_CONFLICT)
                service.status = received
                service.save(update_fields=['status'])
                log = ServiceStatusLog.objects.create(request=service, status=received, actor=actor)
            else:
                return Response({'error': 'Service cannot receive sample'}, status=status.HTTP_409_CONFLICT)
            return Response({
                'serviceRequestId': service.pk, 'status': 'SAMPLE_RECEIVED', 'statusLogId': log.pk,
            })
