from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.authentication import JWTAuthentication
from accounts.csrf import CSRFDoubleSubmitMixin
from accounts.email_utils import send_sample_code_email
from accounts.models import AppUser, Role
from participants.codes import new_client_code
from participants.models import Participant
from services.models import Purchase, PurchaseStatus, Sample, ServiceRequest, ServiceStatus, ServiceStatusLog

STATUS_SEQUENCE = ('WAITING_SAMPLE', 'SAMPLE_RECEIVED', 'PROCESSING', 'COMPLETED')


def _lock_actor(user, roles):
    return AppUser.objects.select_for_update(of=('self',)).filter(
        django_user_id=user.pk, role__code__in=roles,
    ).first()


def _sample_code_for(participant):
    """First sample reuses the client's Sample ID; repeat purchases get -2, -3, ..."""
    code, n = participant.participant_code, 1
    while Sample.objects.filter(sample_code__iexact=code).exists():
        n += 1
        code = f'{participant.participant_code}-{n}'
    return code


class ConfirmPaymentAPIView(CSRFDoubleSubmitMixin, APIView):
    """Reception confirms an in-person payment: PAID purchase, service and sample code, emailed to the client."""
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not isinstance(request.data, dict) or set(request.data) != {'userId'}:
            return Response({'error': 'Only userId is required'}, status=status.HTTP_400_BAD_REQUEST)
        user_id = request.data['userId']
        if type(user_id) is not int or user_id <= 0:
            return Response({'error': 'Invalid userId'}, status=status.HTTP_400_BAD_REQUEST)
        with transaction.atomic():
            actor = _lock_actor(request.user, [Role.Code.ADMIN, Role.Code.RECEPCION])
            if actor is None:
                return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
            # Locking the owner serializes concurrent confirmations for the same client.
            owner = AppUser.objects.select_for_update(of=('self',)).select_related('django_user').filter(
                django_user_id=user_id, django_user__is_active=True, role__code=Role.Code.CLIENTE,
            ).first()
            if owner is None:
                return Response({'error': 'Client not found'}, status=status.HTTP_404_NOT_FOUND)
            if ServiceRequest.objects.filter(
                purchase__owner=owner, purchase__status__code='PAID',
            ).exclude(status__code='COMPLETED').exists():
                return Response({'error': 'Client already has an active service'}, status=status.HTTP_409_CONFLICT)
            paid = PurchaseStatus.objects.filter(code='PAID').first()
            waiting = ServiceStatus.objects.filter(code=STATUS_SEQUENCE[0]).first()
            if paid is None or waiting is None:
                return Response({'error': 'Status catalog unavailable'}, status=status.HTTP_409_CONFLICT)
            participant, _ = Participant.objects.get_or_create(
                user_id=user_id, defaults={'participant_code': new_client_code()},
            )
            purchase = Purchase.objects.create(owner=owner, status=paid, purchased_at=timezone.now())
            service = ServiceRequest.objects.create(purchase=purchase, status=waiting, participant=participant)
            log = ServiceStatusLog.objects.create(request=service, status=waiting, actor=actor)
            sample = Sample.objects.create(
                service_request=service, participant=participant, sample_code=_sample_code_for(participant),
                sample_type='saliva', status='pending_collection',
            )
        # After commit: a failed email must not undo a confirmed payment; reception sees the outcome.
        email_sent = send_sample_code_email(owner.django_user, sample.sample_code)
        return Response({
            'purchaseId': purchase.pk, 'status': 'PAID',
            'purchasedAt': purchase.purchased_at.isoformat().replace('+00:00', 'Z'),
            'serviceRequestId': service.pk, 'serviceStatus': waiting.code, 'statusLogId': log.pk,
            'sampleCode': sample.sample_code, 'sampleEmailSent': email_sent,
        }, status=status.HTTP_201_CREATED)


class AdvanceServiceStatusAPIView(CSRFDoubleSubmitMixin, APIView):
    """Analyst moves a paid service one step forward along STATUS_SEQUENCE."""
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, request_id):
        if not isinstance(request.data, dict) or request.data:
            return Response({'error': 'Advancing does not accept fields'}, status=status.HTTP_400_BAD_REQUEST)
        with transaction.atomic():
            actor = _lock_actor(request.user, [Role.Code.ADMIN, Role.Code.ANALISTA])
            if actor is None:
                return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
            service = ServiceRequest.objects.select_for_update(of=('self',)).select_related(
                'status', 'purchase__status',
            ).filter(pk=request_id).first()
            if service is None:
                return Response({'error': 'Service request not found'}, status=status.HTTP_404_NOT_FOUND)
            purchase = service.purchase
            if purchase.status is None or purchase.status.code != 'PAID' or purchase.purchased_at is None:
                return Response({'error': 'Service is not paid'}, status=status.HTTP_409_CONFLICT)
            current = service.status.code
            if current not in STATUS_SEQUENCE[:-1]:
                return Response({'error': f'Service cannot advance from {current}'}, status=status.HTTP_409_CONFLICT)
            following = ServiceStatus.objects.filter(
                code=STATUS_SEQUENCE[STATUS_SEQUENCE.index(current) + 1],
            ).first()
            if following is None:
                return Response({'error': 'Status catalog unavailable'}, status=status.HTTP_409_CONFLICT)
            service.status = following
            update_fields = ['status']
            if following.code == 'COMPLETED':
                service.completed_at = timezone.now()
                update_fields.append('completed_at')
            if following.code == 'SAMPLE_RECEIVED':
                Sample.objects.filter(service_request=service, status='pending_collection').update(
                    status='received', collected_at=timezone.now(),
                )
            service.save(update_fields=update_fields)
            log = ServiceStatusLog.objects.create(request=service, status=following, actor=actor)
        return Response({
            'serviceRequestId': service.pk, 'previousStatus': current,
            'status': following.code, 'statusLogId': log.pk,
        })
