import uuid

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
