import uuid

import genetics.models
from django.db import migrations, models
from django.contrib.postgres.functions import TransactionNow
from django.utils import timezone


class Migration(migrations.Migration):
    dependencies = [('genetics', '0007_population')]

    operations = [
        migrations.CreateModel(
            name='EpigeneticFeature',
            fields=[
                ('epigenetic_feature_id', models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ('feature_type', models.CharField(max_length=64)),
                ('reference_assembly', models.CharField(max_length=32)),
                ('contig', models.CharField(max_length=64)),
                ('start_pos', models.BigIntegerField()),
                ('end_pos', models.BigIntegerField()),
                ('coordinate_system', models.CharField(max_length=32, default='1-based-inclusive', db_default='1-based-inclusive')),
                ('strand', genetics.models.FixedCharField(max_length=1, null=True, blank=True)),
                ('modification_code', models.CharField(max_length=32, null=True, blank=True)),
                ('name', models.CharField(max_length=255, null=True, blank=True)),
                ('metadata', models.JSONField(null=True, blank=True)),
                ('created_at', models.DateTimeField(default=timezone.now, db_default=TransactionNow())),
            ],
            options={
                'db_table': 'epigenetic_feature',
                'indexes': [
                    models.Index(fields=['reference_assembly', 'contig', 'start_pos', 'end_pos'], name='idx_epigenetic_feature_region'),
                ],
                'constraints': [
                    models.CheckConstraint(condition=models.Q(start_pos__gte=1), name='epigenetic_feature_start_gte_1'),
                    models.CheckConstraint(condition=models.Q(end_pos__gte=models.F('start_pos')), name='epigenetic_feature_end_gte_start'),
                ],
            },
        ),
    ]
