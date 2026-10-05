"""Read-only projection of a client's newest paid service into legacy Profile status."""

from dataclasses import dataclass
from datetime import datetime

from django.db.models import F

from profiles.models import Profile, ServiceStatus as LegacyStatus
from services.models import Purchase, ServiceRequest, ServiceStatusLog


@dataclass(frozen=True)
class LegacyServiceProjection:
    service_status: str
    updated_at: datetime | None

    @property
    def can_view_results(self):
        return self.service_status == LegacyStatus.COMPLETED


def get_legacy_service_projection(user):
    """Never use an older service or Profile to mask a broken paid purchase."""
    purchase = (Purchase.objects.filter(owner__django_user=user, status__code='PAID')
                .order_by(F('purchased_at').desc(nulls_first=True), '-created_at', '-pk')
                .first())
    if purchase is None:
        profile = Profile.objects.filter(user=user).first()
        if profile is not None:
            return LegacyServiceProjection(profile.service_status, profile.service_updated_at)
        return LegacyServiceProjection(LegacyStatus.NO_PURCHASED, None)

    unavailable = LegacyServiceProjection(LegacyStatus.NO_PURCHASED, None)
    if purchase.purchased_at is None:
        return unavailable
    service = ServiceRequest.objects.select_related('status').filter(purchase=purchase).first()
    if service is None:
        return unavailable
    if service.participant_id is not None:
        from participants.models import Participant
        if not Participant.objects.filter(pk=service.participant_id, user_id=user.pk).exists():
            return unavailable
    if not ServiceStatusLog.objects.filter(request=service, status__code='WAITING_SAMPLE').exists():
        return unavailable
    latest_log = (ServiceStatusLog.objects.select_related('status').filter(request=service)
                  .order_by('-changed_at', '-pk').first())
    if latest_log is None or latest_log.status_id != service.status_id:
        return unavailable
    code = service.status.code
    if code == 'COMPLETED':
        if service.completed_at is None or service.completed_at < service.started_at:
            return unavailable
        return LegacyServiceProjection(LegacyStatus.COMPLETED, latest_log.changed_at)
    if code in ('WAITING_SAMPLE', 'SAMPLE_RECEIVED', 'PROCESSING'):
        return LegacyServiceProjection(LegacyStatus.PENDING, latest_log.changed_at)
    return unavailable
