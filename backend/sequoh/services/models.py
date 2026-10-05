import uuid

from django.core.exceptions import ValidationError
from django.db import models, router
from django.db.models.functions import Now
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


class Sample(models.Model):
    sample_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    service_request = models.ForeignKey(
        ServiceRequest, on_delete=models.PROTECT, db_column='service_request_id', related_name='samples',
    )
    participant = models.ForeignKey(
        'participants.Participant', on_delete=models.PROTECT, db_column='participant_id', related_name='samples',
    )
    parent_sample = models.ForeignKey(
        'self', on_delete=models.SET_NULL, db_column='parent_sample_id',
        null=True, blank=True, related_name='child_samples',
    )
    sample_code = models.CharField(max_length=96, unique=True)
    sample_type = models.CharField(max_length=64)
    material = models.CharField(max_length=64, null=True, blank=True)
    collection_method = models.CharField(max_length=128, null=True, blank=True)
    collected_at = models.DateTimeField(null=True, blank=True)
    storage_location = models.CharField(max_length=255, null=True, blank=True)
    metadata = models.JSONField(null=True, blank=True)
    status = models.CharField(max_length=32, default='available', db_default=models.Value('available'))
    created_at = models.DateTimeField(default=timezone.now, db_default=Now())

    class Meta:
        db_table = 'sample'

    def _validate_relationships(self, using):
        for field in ('service_request', 'participant'):
            if getattr(self, f'{field}_id') is None:
                raise ValidationError({field: 'This field is required.'})
        request = ServiceRequest.objects.using(using).filter(pk=self.service_request_id).values(
            'participant_id', 'participant__user_id', 'purchase__owner__django_user_id',
        ).first()
        if request is None or request['participant_id'] is None:
            raise ValidationError({'service_request': 'An existing service with a participant is required.'})
        if request['participant_id'] != self.participant_id:
            raise ValidationError({'participant': 'Participant must match the service participant.'})
        if request['purchase__owner__django_user_id'] != request['participant__user_id']:
            raise ValidationError({'service_request': 'Participant must belong to the purchase owner.'})

        samples = type(self).objects.using(using)
        persisted = samples.filter(pk=self.pk).values('service_request_id', 'participant_id').first()
        if persisted:
            errors = {
                field: 'Sample ownership cannot be reassigned.'
                for field in ('service_request', 'participant')
                if persisted[f'{field}_id'] != getattr(self, f'{field}_id')
            }
            if errors:
                raise ValidationError(errors)
        seen = {self.pk}
        parent_id = self.parent_sample_id
        while parent_id is not None:
            if parent_id in seen:
                raise ValidationError({'parent_sample': 'Sample ancestry must not contain a cycle.'})
            seen.add(parent_id)
            parent = samples.filter(pk=parent_id).values(
                'service_request_id', 'participant_id', 'parent_sample_id',
            ).first()
            if parent is None:
                raise ValidationError({'parent_sample': 'Parent sample must exist.'})
            if (parent['service_request_id'], parent['participant_id']) != (
                self.service_request_id, self.participant_id,
            ):
                raise ValidationError({'parent_sample': 'Parent must belong to the same service and participant.'})
            parent_id = parent['parent_sample_id']

    def clean(self):
        super().clean()
        self._validate_relationships(router.db_for_write(type(self), instance=self))

    def save(self, *args, **kwargs):
        # bulk_create/QuerySet.update bypass Python validation; simple FKs cannot
        # enforce ownership equality across service, purchase and participant tables.
        # GDB03c service reads must fail closed unless sample.participant matches
        # request.participant AND participant.user == request.purchase.owner.django_user.
        using = kwargs.get('using') or router.db_for_write(type(self), instance=self)
        self._validate_relationships(using)
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
