import uuid

import django.db.models.deletion
from django.db import migrations, models
from django.db.models.functions import Now
from django.utils import timezone


class Migration(migrations.Migration):
    dependencies = [
        ('participants', '0001_initial'),
        ('services', '0004_sample'),
    ]

    operations = [
        migrations.CreateModel(
            name='Observation',
            fields=[
                ('observation_id', models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ('observation_type', models.CharField(max_length=48)),
                ('code_system', models.CharField(max_length=64, null=True, blank=True)),
                ('code', models.CharField(max_length=128, null=True, blank=True)),
                ('label', models.CharField(max_length=255)),
                ('value_numeric', models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)),
                ('value_text', models.TextField(null=True, blank=True)),
                ('value_code', models.CharField(max_length=128, null=True, blank=True)),
                ('value_boolean', models.BooleanField(null=True, blank=True)),
                ('unit', models.CharField(max_length=64, null=True, blank=True)),
                ('reference_low', models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)),
                ('reference_high', models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)),
                ('source_name', models.CharField(max_length=128, null=True, blank=True)),
                ('source_version', models.CharField(max_length=64, null=True, blank=True)),
                ('observed_at', models.DateTimeField(null=True, blank=True)),
                ('metadata', models.JSONField(null=True, blank=True)),
                ('created_at', models.DateTimeField(default=timezone.now, db_default=Now())),
                ('participant', models.ForeignKey(
                    to='participants.participant', on_delete=django.db.models.deletion.PROTECT,
                    db_column='participant_id', db_index=False, related_name='observations',
                )),
                ('sample', models.ForeignKey(
                    to='services.sample', on_delete=django.db.models.deletion.PROTECT,
                    db_column='sample_id', null=True, blank=True, db_index=False, related_name='observations',
                )),
            ],
            options={
                'db_table': 'observation',
                'indexes': [
                    models.Index(fields=['participant', 'observed_at'], name='observation_part_time_idx'),
                    models.Index(fields=['code_system', 'code'], name='observation_code_idx'),
                ],
            },
        ),
    ]
