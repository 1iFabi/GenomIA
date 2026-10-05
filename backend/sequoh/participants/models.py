import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class Participant(models.Model):
    class EnrollmentStatus(models.TextChoices):
        PENDING = 'pending', 'Pending'
        ACTIVE = 'active', 'Active'
        INACTIVE = 'inactive', 'Inactive'

    class ConsentStatus(models.TextChoices):
        PENDING = 'pending', 'Pending'
        GRANTED = 'granted', 'Granted'
        WITHDRAWN = 'withdrawn', 'Withdrawn'

    participant_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    participant_code = models.CharField(max_length=64, unique=True)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='participant',
    )
    enrolled_at = models.DateTimeField(default=timezone.now)
    enrollment_status = models.CharField(
        max_length=8,
        choices=EnrollmentStatus.choices,
        default=EnrollmentStatus.PENDING,
    )
    consent_status = models.CharField(
        max_length=9,
        choices=ConsentStatus.choices,
        default=ConsentStatus.PENDING,
    )
    consent_version = models.CharField(max_length=32, null=True, blank=True)
    consented_at = models.DateTimeField(null=True, blank=True)
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text='Non-identifying enrollment metadata only.',
    )

    class Meta:
        db_table = 'participant'
        constraints = [
            models.CheckConstraint(
                condition=models.Q(enrollment_status__in=['pending', 'active', 'inactive']),
                name='participant_enrollment_status_valid',
            ),
            models.CheckConstraint(
                condition=models.Q(consent_status__in=['pending', 'granted', 'withdrawn']),
                name='participant_consent_status_valid',
            ),
            models.CheckConstraint(
                condition=(
                    ~models.Q(consent_status='granted')
                    | (
                        models.Q(consent_version__isnull=False)
                        & ~models.Q(consent_version='')
                        & models.Q(consented_at__isnull=False)
                    )
                ),
                name='participant_granted_consent_complete',
            ),
        ]
