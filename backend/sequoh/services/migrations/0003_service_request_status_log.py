import uuid

import django.db.models.deletion
from django.db import migrations, models
from django.utils import timezone


class Migration(migrations.Migration):
    dependencies = [
        ('services', '0002_seed_statuses'),
        ('participants', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='ServiceRequest',
            fields=[
                ('service_request_id', models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ('created_at', models.DateTimeField(default=timezone.now)),
                ('started_at', models.DateTimeField(default=timezone.now)),
                ('completed_at', models.DateTimeField(null=True, blank=True)),
                ('purchase', models.OneToOneField(
                    to='services.purchase', on_delete=django.db.models.deletion.PROTECT,
                    db_column='purchase_id', related_name='service_request',
                )),
                ('participant', models.ForeignKey(
                    to='participants.participant', on_delete=django.db.models.deletion.PROTECT,
                    db_column='participant_id', null=True, blank=True, related_name='service_requests',
                )),
                ('status', models.ForeignKey(
                    to='services.servicestatus', on_delete=django.db.models.deletion.PROTECT,
                    db_column='service_status_id', related_name='service_requests',
                )),
            ],
            options={
                'db_table': 'service_request',
                'ordering': ['-created_at', '-service_request_id'],
                'indexes': [models.Index(fields=['-created_at'], name='service_req_created_idx')],
                'constraints': [models.CheckConstraint(
                    condition=models.Q(completed_at__isnull=True) | models.Q(completed_at__gte=models.F('started_at')),
                    name='service_request_completed_after_start',
                )],
            },
        ),
        migrations.CreateModel(
            name='ServiceStatusLog',
            fields=[
                ('service_status_log_id', models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ('changed_at', models.DateTimeField(default=timezone.now)),
                ('comment', models.TextField(null=True, blank=True)),
                ('request', models.ForeignKey(
                    to='services.servicerequest', on_delete=django.db.models.deletion.PROTECT,
                    db_column='service_request_id', db_index=False, related_name='status_history',
                )),
                ('status', models.ForeignKey(
                    to='services.servicestatus', on_delete=django.db.models.deletion.PROTECT,
                    db_column='service_status_id', related_name='service_logs',
                )),
                ('actor', models.ForeignKey(
                    to='accounts.appuser', on_delete=django.db.models.deletion.PROTECT,
                    db_column='user_id', related_name='service_status_changes',
                )),
            ],
            options={
                'db_table': 'service_status_log',
                'ordering': ['-changed_at', '-service_status_log_id'],
                'indexes': [models.Index(fields=['request', '-changed_at'], name='service_log_request_time_idx')],
            },
        ),
    ]
