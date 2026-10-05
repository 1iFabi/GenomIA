import uuid

import django.db.models.deletion
import genetics.models
from django.db import migrations, models
from django.contrib.postgres.functions import TransactionNow
from django.utils import timezone


class Migration(migrations.Migration):
    dependencies = [('genetics', '0002_analysis')]

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
                ('manifest_checksum', genetics.models.FixedCharField(max_length=64, null=True, blank=True)),
                ('frozen_at', models.DateTimeField(null=True, blank=True)),
                ('created_at', models.DateTimeField(default=timezone.now, db_default=TransactionNow())),
            ],
            options={
                'db_table': 'data_release',
                'constraints': [models.UniqueConstraint(fields=['name', 'version'], name='uq_data_release_name_version')],
            },
        ),
        migrations.AddField(
            model_name='analysis',
            name='release',
            # PROTECT intentionally retains provenance instead of SQL's SET NULL.
            field=models.ForeignKey(
                to='genetics.datarelease', on_delete=django.db.models.deletion.PROTECT,
                db_column='release_id', null=True, blank=True, db_index=False, related_name='analyses',
            ),
        ),
        migrations.AddIndex(
            model_name='analysis',
            index=models.Index(fields=['release', 'module'], name='idx_analysis_release_module'),
        ),
    ]
