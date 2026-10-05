import uuid

import django.db.models.deletion
from django.db import migrations, models
from django.db.models.functions import Now
from django.utils import timezone


class Migration(migrations.Migration):
    dependencies = [
        ('services', '0003_service_request_status_log'),
        ('participants', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Sample',
            fields=[
                ('sample_id', models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ('sample_code', models.CharField(max_length=96, unique=True)),
                ('sample_type', models.CharField(max_length=64)),
                ('material', models.CharField(max_length=64, null=True, blank=True)),
                ('collection_method', models.CharField(max_length=128, null=True, blank=True)),
                ('collected_at', models.DateTimeField(null=True, blank=True)),
                ('storage_location', models.CharField(max_length=255, null=True, blank=True)),
                ('metadata', models.JSONField(null=True, blank=True)),
                ('status', models.CharField(max_length=32, default='available', db_default=models.Value('available'))),
                ('created_at', models.DateTimeField(default=timezone.now, db_default=Now())),
                ('service_request', models.ForeignKey(
                    to='services.servicerequest', on_delete=django.db.models.deletion.PROTECT,
                    db_column='service_request_id', related_name='samples',
                )),
                ('participant', models.ForeignKey(
                    to='participants.participant', on_delete=django.db.models.deletion.PROTECT,
                    db_column='participant_id', related_name='samples',
                )),
                ('parent_sample', models.ForeignKey(
                    to='services.sample', on_delete=django.db.models.deletion.SET_NULL,
                    db_column='parent_sample_id', null=True, blank=True, related_name='child_samples',
                )),
            ],
            options={'db_table': 'sample'},
        ),
    ]
