import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, router
from django.db.models.functions import Now
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

    class SexAtBirth(models.TextChoices):
        FEMALE = 'female', 'Female'
        MALE = 'male', 'Male'
        INTERSEX = 'intersex', 'Intersex'
        OTHER = 'other', 'Other'

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
    # Collected with the purchase data, never at registration. Year only to reduce re-identification risk.
    sex_at_birth = models.CharField(max_length=32, choices=SexAtBirth.choices, null=True, blank=True)
    birth_year = models.PositiveSmallIntegerField(null=True, blank=True)
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
            models.CheckConstraint(
                condition=models.Q(sex_at_birth__isnull=True) | models.Q(sex_at_birth__in=['female', 'male', 'intersex', 'other']),
                name='participant_sex_at_birth_valid',
            ),
            models.CheckConstraint(
                condition=models.Q(birth_year__isnull=True) | models.Q(birth_year__gte=1900),
                name='participant_birth_year_valid',
            ),
        ]


class ParticipantMetadata(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, null=True, blank=True)
    questionary = models.JSONField(null=True, blank=True)
    version = models.IntegerField(null=True, blank=True)
    description = models.CharField(max_length=255, null=True, blank=True)
    type = models.CharField(max_length=50, default='form_or_consent', db_default='form_or_consent')

    class Meta:
        db_table = 'participant_metadata'


class ParticipantMetadataLink(models.Model):
    pk = models.CompositePrimaryKey('idm', 'idp')
    idm = models.ForeignKey(
        ParticipantMetadata, on_delete=models.PROTECT, db_column='idm',
        db_index=False, related_name='participant_links',
    )
    idp = models.ForeignKey(
        Participant, on_delete=models.PROTECT, db_column='idp',
        db_index=False, related_name='metadata_links',
    )
    answer = models.JSONField(null=True, blank=True)
    first_date = models.DateField(null=True, blank=True)
    last_update = models.DateField(null=True, blank=True)
    description = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        db_table = 'participant_2_meta'


class Observation(models.Model):
    observation_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    participant = models.ForeignKey(
        Participant, on_delete=models.PROTECT, db_column='participant_id',
        db_index=False, related_name='observations',
    )
    sample = models.ForeignKey(
        'services.Sample', on_delete=models.PROTECT, db_column='sample_id',
        null=True, blank=True, db_index=False, related_name='observations',
    )
    observation_type = models.CharField(max_length=48)
    code_system = models.CharField(max_length=64, null=True, blank=True)
    code = models.CharField(max_length=128, null=True, blank=True)
    label = models.CharField(max_length=255)
    value_numeric = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    value_text = models.TextField(null=True, blank=True)
    value_code = models.CharField(max_length=128, null=True, blank=True)
    value_boolean = models.BooleanField(null=True, blank=True)
    unit = models.CharField(max_length=64, null=True, blank=True)
    reference_low = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    reference_high = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    source_name = models.CharField(max_length=128, null=True, blank=True)
    source_version = models.CharField(max_length=64, null=True, blank=True)
    observed_at = models.DateTimeField(null=True, blank=True)
    metadata = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_default=Now())

    class Meta:
        db_table = 'observation'
        indexes = [
            models.Index(fields=['participant', 'observed_at'], name='observation_part_time_idx'),
            models.Index(fields=['code_system', 'code'], name='observation_code_idx'),
        ]

    def _validate_relationships(self, using, update_fields=None):
        user_id = Participant.objects.using(using).filter(pk=self.participant_id).values_list('user_id', flat=True).first()
        if user_id is None:
            raise ValidationError({'participant': 'An existing participant is required.'})
        persisted = type(self).objects.using(using).filter(pk=self.pk).values('participant_id', 'sample_id').first()
        if persisted and persisted['participant_id'] != self.participant_id:
            raise ValidationError({'participant': 'Observation ownership cannot be reassigned.'})
        sample_id = self.sample_id
        # Partial saves must validate the sample that will remain in the row.
        if persisted and update_fields is not None and {'sample', 'sample_id'}.isdisjoint(update_fields):
            sample_id = persisted['sample_id']
        if sample_id is not None:
            from services.models import Sample
            sample = Sample.objects.using(using).filter(pk=sample_id).values(
                'participant_id', 'service_request__participant_id',
                'service_request__purchase__owner__django_user_id',
            ).first()
            if sample is None or (
                sample['participant_id'], sample['service_request__participant_id'],
                sample['service_request__purchase__owner__django_user_id'],
            ) != (self.participant_id, self.participant_id, user_id):
                raise ValidationError({'sample': 'Sample, service participant and purchase owner must match the participant.'})

    def clean(self):
        super().clean()
        self._validate_relationships(router.db_for_write(type(self), instance=self))

    def save(self, *args, **kwargs):
        # bulk_create/QuerySet.update bypass validation; cross-table ownership is
        # checked from persisted relations, not cached objects, on ordinary saves.
        using = kwargs.get('using') or router.db_for_write(type(self), instance=self)
        update_fields = kwargs.get('update_fields')
        if update_fields is not None:
            update_fields = kwargs['update_fields'] = frozenset(update_fields)
        self._validate_relationships(using, update_fields)
        return super().save(*args, **kwargs)
