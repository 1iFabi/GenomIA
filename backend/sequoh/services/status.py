"""Read-only projection of a client's newest paid service into the client-facing status."""

from dataclasses import dataclass, replace
from datetime import datetime

from django.db import models
from django.db.models import F

from services.models import Purchase, Sample, ServiceRequest, ServiceStatusLog


class ClientStatus(models.TextChoices):
    NO_PURCHASED = "NO_PURCHASED", "Sin servicio"
    PENDING = "PENDING", "Pendiente"
    COMPLETED = "COMPLETED", "Completado"


@dataclass(frozen=True)
class ServiceProjection:
    service_status: str
    updated_at: datetime | None
    service_samples: tuple[Sample, ...] = ()
    service_request_id: object = None
    request_status: str | None = None

    @property
    def can_view_results(self):
        return self.service_status == ClientStatus.COMPLETED


def _project_paid(purchase, service, *, has_initial, latest_log, participant_owned):
    """A malformed newest paid purchase must never expose older results state."""
    unavailable = ServiceProjection(ClientStatus.NO_PURCHASED, None)
    if (purchase.purchased_at is None or service is None or not participant_owned
            or not has_initial or latest_log is None or latest_log.status_id != service.status_id):
        return unavailable
    code = service.status.code
    if code == 'COMPLETED':
        if service.completed_at is None or service.completed_at < service.started_at:
            return unavailable
        return ServiceProjection(ClientStatus.COMPLETED, latest_log.changed_at,
                                 service_request_id=service.pk, request_status=code)
    if code in ('WAITING_SAMPLE', 'SAMPLE_RECEIVED', 'PROCESSING'):
        return ServiceProjection(ClientStatus.PENDING, latest_log.changed_at,
                                 service_request_id=service.pk, request_status=code)
    return unavailable


def get_service_projections(user_ids, *, include_samples=False):
    """Projections keyed by Django User ID; users without a paid purchase are absent.

    PostgreSQL DISTINCT ON chooses one newest PAID purchase per owner. The two
    history queries cover initial and latest state without a query per account.
    Reception can opt into one sample query limited to the selected trusted requests.
    """
    ids = list(user_ids)
    if not ids:
        return {}
    purchases = list(
        Purchase.objects.filter(owner__django_user_id__in=ids, status__code='PAID')
        .select_related('owner', 'service_request__status')
        .annotate(participant_owner_id=F('service_request__participant__user_id'))
        .order_by('owner_id', F('purchased_at').desc(nulls_first=True), '-created_at', '-pk')
        .distinct('owner_id')
    )
    services = [(purchase, getattr(purchase, 'service_request', None)) for purchase in purchases]
    request_ids = [service.pk for _, service in services if service is not None]
    initial_ids = set(ServiceStatusLog.objects.filter(
        request_id__in=request_ids, status__code='WAITING_SAMPLE',
    ).order_by().values_list('request_id', flat=True).distinct()) if request_ids else set()
    latest_logs = {log.request_id: log for log in (
        ServiceStatusLog.objects.filter(request_id__in=request_ids)
        .order_by('request_id', '-changed_at', '-pk').distinct('request_id')
    )} if request_ids else {}
    projections = {}
    request_owners = {}
    for purchase, service in services:
        owner_id = purchase.owner.django_user_id
        projections[owner_id] = _project_paid(
            purchase, service,
            has_initial=service is not None and service.pk in initial_ids,
            latest_log=latest_logs.get(service.pk) if service else None,
            participant_owned=service is None or service.participant_id is None
            or purchase.participant_owner_id == owner_id,
        )
        if (include_samples and projections[owner_id].service_status != ClientStatus.NO_PURCHASED
                and service.participant_id is not None):
            request_owners[service.pk] = owner_id
    if request_owners:
        samples = {request_id: [] for request_id in request_owners}
        # Recheck persisted ownership: bulk/upstream writes bypass Sample.clean().
        for sample in (Sample.objects.filter(
            service_request_id__in=request_owners,
            participant_id=F('service_request__participant_id'),
            participant__user_id=F('service_request__purchase__owner__django_user_id'),
        ).only('service_request_id', 'sample_code', 'sample_type', 'status', 'collected_at', 'created_at')
                .order_by('service_request_id', 'created_at', 'pk')):
            samples[sample.service_request_id].append(sample)
        for request_id, owner_id in request_owners.items():
            projections[owner_id] = replace(projections[owner_id], service_samples=tuple(samples[request_id]))
    return projections


def get_service_projection(user):
    """Never use an older service to mask a broken newest paid purchase."""
    purchase = (Purchase.objects.filter(owner__django_user=user, status__code='PAID')
                .order_by(F('purchased_at').desc(nulls_first=True), '-created_at', '-pk')
                .first())
    if purchase is None:
        return ServiceProjection(ClientStatus.NO_PURCHASED, None)
    if purchase.purchased_at is None:
        return _project_paid(purchase, None, has_initial=False, latest_log=None, participant_owned=True)

    service = ServiceRequest.objects.select_related('status').filter(purchase=purchase).first()
    if service is None:
        return _project_paid(purchase, None, has_initial=False, latest_log=None, participant_owned=True)
    participant_owned = True
    if service.participant_id is not None:
        from participants.models import Participant
        participant_owned = Participant.objects.filter(pk=service.participant_id, user_id=user.pk).exists()
    has_initial = ServiceStatusLog.objects.filter(request=service, status__code='WAITING_SAMPLE').exists()
    latest_log = (ServiceStatusLog.objects.filter(request=service)
                  .order_by('-changed_at', '-pk').first())
    return _project_paid(purchase, service, has_initial=has_initial,
                         latest_log=latest_log, participant_owned=participant_owned)
