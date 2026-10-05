import uuid

import django.db.models.deletion
from django.db import migrations, models
from django.utils import timezone


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ('accounts', '0004_seed_roles_backfill'),
    ]

    operations = [
        migrations.CreateModel(
            name='PurchaseStatus',
            fields=[
                ('purchase_status_id', models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ('code', models.CharField(max_length=30, unique=True)),
                ('name', models.CharField(max_length=120, null=True, blank=True)),
            ],
            options={'db_table': 'purchase_status'},
        ),
        migrations.CreateModel(
            name='ServiceStatus',
            fields=[
                ('service_status_id', models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ('code', models.CharField(max_length=30, unique=True)),
                ('name', models.CharField(max_length=120, null=True, blank=True)),
            ],
            options={'db_table': 'service_status'},
        ),
        migrations.CreateModel(
            name='Purchase',
            fields=[
                ('purchase_id', models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ('purchased_at', models.DateTimeField(null=True, blank=True)),
                ('created_at', models.DateTimeField(default=timezone.now)),
                ('owner', models.ForeignKey(
                    to='accounts.appuser', on_delete=django.db.models.deletion.PROTECT,
                    db_column='user_id', db_index=False, related_name='purchases',
                )),
                ('status', models.ForeignKey(
                    to='services.purchasestatus', on_delete=django.db.models.deletion.PROTECT,
                    db_column='purchase_status_id', null=True, blank=True,
                    db_index=False, related_name='purchases',
                )),
            ],
            options={
                'db_table': 'purchase',
                'ordering': ['-created_at', '-purchase_id'],
                'indexes': [
                    models.Index(fields=['owner', '-created_at'], name='purchase_owner_created_idx'),
                    models.Index(fields=['status', '-created_at'], name='purchase_status_created_idx'),
                ],
            },
        ),
    ]
