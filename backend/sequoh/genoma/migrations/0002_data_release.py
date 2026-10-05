"""Create the normalized DataRelease table."""

import uuid

import genoma.models
from django.contrib.postgres.functions import TransactionNow
from django.db import migrations, models
from django.utils import timezone


class Migration(migrations.Migration):
    dependencies = [
        ('genoma', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='DataRelease',
            fields=[
                ('release_id', models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ('name', models.CharField(max_length=128)),
                ('version', models.CharField(max_length=64)),
                ('status', models.CharField(max_length=32)),
                ('reference_assembly', models.CharField(max_length=32)),
                ('description', models.TextField(null=True, blank=True)),
                ('manifest_checksum', genoma.models.FixedCharField(max_length=64, null=True, blank=True)),
                ('frozen_at', models.DateTimeField(null=True, blank=True)),
                ('created_at', models.DateTimeField(default=timezone.now, db_default=TransactionNow())),
            ],
            options={
                'db_table': 'data_release',
                'constraints': [models.UniqueConstraint(fields=['name', 'version'], name='uq_data_release_name_version')],
            },
        ),
    ]
