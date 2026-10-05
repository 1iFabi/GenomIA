"""Create Analysis before attaching its DataRelease relationship in 0003."""

import uuid

import django.db.models.deletion
from django.contrib.postgres.functions import TransactionNow
from django.db import migrations, models
from django.utils import timezone


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ('participants', '0003_participant_metadata_support'),
        ('services', '0004_sample'),
    ]

    operations = [
        migrations.CreateModel(
            name='Analysis',
            fields=[
                ('analysis_id', models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ('participant', models.ForeignKey(
                    to='participants.participant', on_delete=django.db.models.deletion.PROTECT,
                    db_column='participant_id', null=True, blank=True, db_index=False, related_name='analyses',
                )),
                ('sample', models.ForeignKey(
                    to='services.sample', on_delete=django.db.models.deletion.PROTECT,
                    db_column='sample_id', null=True, blank=True, db_index=False, related_name='analyses',
                )),
                ('service_request', models.ForeignKey(
                    to='services.servicerequest', on_delete=django.db.models.deletion.PROTECT,
                    db_column='service_request_id', null=True, blank=True, db_index=False, related_name='analyses',
                )),
                ('module', models.CharField(max_length=64)),
                ('pipeline_name', models.CharField(max_length=128)),
                ('pipeline_version', models.CharField(max_length=64)),
                ('container_digest', models.CharField(max_length=255, null=True, blank=True)),
                ('reference_assembly', models.CharField(max_length=32, null=True, blank=True)),
                ('parameters', models.JSONField(null=True, blank=True)),
                ('status', models.CharField(max_length=32)),
                ('started_at', models.DateTimeField(null=True, blank=True)),
                ('finished_at', models.DateTimeField(null=True, blank=True)),
                ('created_at', models.DateTimeField(default=timezone.now, db_default=TransactionNow())),
            ],
            options={
                'db_table': 'analysis',
                'indexes': [models.Index(fields=['sample'], name='idx_analysis_sample')],
            },
        ),
    ]
