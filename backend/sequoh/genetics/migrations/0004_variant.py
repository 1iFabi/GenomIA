import uuid

from django.db import migrations, models
from django.contrib.postgres.functions import TransactionNow
from django.utils import timezone


class Migration(migrations.Migration):
    dependencies = [('genetics', '0003_data_release_analysis_release')]

    operations = [
        migrations.CreateModel(
            name='Variant',
            fields=[
                ('variant_id', models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ('variant_type', models.CharField(max_length=32)),
                ('canonical_name', models.CharField(max_length=255, null=True, blank=True)),
                ('vrs_id', models.CharField(max_length=255, null=True, blank=True, unique=True)),
                ('status', models.CharField(max_length=32, default='active', db_default='active')),
                ('metadata', models.JSONField(null=True, blank=True)),
                ('created_at', models.DateTimeField(default=timezone.now, db_default=TransactionNow())),
            ],
            options={
                'db_table': 'variant',
                'indexes': [models.Index(fields=['variant_type'], name='idx_variant_type')],
            },
        ),
    ]
