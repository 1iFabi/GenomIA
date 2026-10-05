import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.utils import timezone


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Participant',
            fields=[
                ('participant_id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('participant_code', models.CharField(max_length=64, unique=True)),
                ('enrolled_at', models.DateTimeField(default=timezone.now)),
                ('enrollment_status', models.CharField(choices=[('pending', 'Pending'), ('active', 'Active'), ('inactive', 'Inactive')], default='pending', max_length=8)),
                ('consent_status', models.CharField(choices=[('pending', 'Pending'), ('granted', 'Granted'), ('withdrawn', 'Withdrawn')], default='pending', max_length=9)),
                ('consent_version', models.CharField(blank=True, max_length=32, null=True)),
                ('consented_at', models.DateTimeField(blank=True, null=True)),
                ('metadata', models.JSONField(blank=True, default=dict, help_text='Non-identifying enrollment metadata only.')),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name='participant', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'participant',
                'constraints': [
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
                ],
            },
        ),
    ]
