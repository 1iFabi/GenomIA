import uuid

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class PurchaseStatus(models.Model):
    purchase_status_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=30, unique=True)
    name = models.CharField(max_length=120, null=True, blank=True)

    class Meta:
        db_table = 'purchase_status'


class ServiceStatus(models.Model):
    service_status_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=30, unique=True)
    name = models.CharField(max_length=120, null=True, blank=True)

    class Meta:
        db_table = 'service_status'


class Purchase(models.Model):
    purchase_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        'accounts.AppUser', on_delete=models.PROTECT, db_column='user_id',
        db_index=False, related_name='purchases',
    )
    status = models.ForeignKey(
        PurchaseStatus, on_delete=models.PROTECT, db_column='purchase_status_id',
        null=True, blank=True, db_index=False, related_name='purchases',
    )
    purchased_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'purchase'
        ordering = ['-created_at', '-purchase_id']
        indexes = [
            models.Index(fields=['owner', '-created_at'], name='purchase_owner_created_idx'),
            models.Index(fields=['status', '-created_at'], name='purchase_status_created_idx'),
        ]


class ServiceRequest(models.Model):
    service_request_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # Manual-payment MVP: one request per purchase, enforced even for concurrent payments.
    purchase = models.OneToOneField(
        Purchase, on_delete=models.PROTECT, db_column='purchase_id', related_name='service_request',
    )
    participant = models.ForeignKey(
        'participants.Participant', on_delete=models.PROTECT, db_column='participant_id',
        null=True, blank=True, related_name='service_requests',
    )
    status = models.ForeignKey(
        ServiceStatus, on_delete=models.PROTECT, db_column='service_status_id',
        related_name='service_requests',
    )
    created_at = models.DateTimeField(default=timezone.now)
    started_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'service_request'
        ordering = ['-created_at', '-service_request_id']
        indexes = [models.Index(fields=['-created_at'], name='service_req_created_idx')]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(completed_at__isnull=True) | models.Q(completed_at__gte=models.F('started_at')),
                name='service_request_completed_after_start',
            ),
        ]

    def clean(self):
        super().clean()
        if self.participant_id is not None and self.purchase_id is not None:
            owner_id = Purchase.objects.filter(pk=self.purchase_id).values_list(
                'owner__django_user_id', flat=True,
            ).first()
            from participants.models import Participant
            if not Participant.objects.filter(pk=self.participant_id, user_id=owner_id).exists():
                raise ValidationError({'participant': 'Participant must belong to the purchase owner.'})

    def save(self, *args, **kwargs):
        # QuerySet.update/bulk_create bypass Python validation; callers must preserve ownership.
        self.clean()
        return super().save(*args, **kwargs)


class ServiceStatusLog(models.Model):
    service_status_log_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    request = models.ForeignKey(
        ServiceRequest, on_delete=models.PROTECT, db_column='service_request_id',
        db_index=False, related_name='status_history',
    )
    status = models.ForeignKey(
        ServiceStatus, on_delete=models.PROTECT, db_column='service_status_id',
        related_name='service_logs',
    )
    actor = models.ForeignKey(
        'accounts.AppUser', on_delete=models.PROTECT, db_column='user_id',
        related_name='service_status_changes',
    )
    changed_at = models.DateTimeField(default=timezone.now)
    comment = models.TextField(null=True, blank=True)

    class Meta:
        db_table = 'service_status_log'
        ordering = ['-changed_at', '-service_status_log_id']
        indexes = [
            models.Index(fields=['request', '-changed_at'], name='service_log_request_time_idx'),
        ]
