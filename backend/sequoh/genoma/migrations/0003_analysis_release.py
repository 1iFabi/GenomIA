"""Attach Analysis.release after both normalized tables exist."""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('genoma', '0002_data_release'),
    ]

    operations = [
        migrations.AddField(
            model_name='analysis',
            name='release',
            # PROTECT intentionally retains provenance instead of SQL's SET NULL.
            field=models.ForeignKey(
                to='genoma.datarelease', on_delete=django.db.models.deletion.PROTECT,
                db_column='release_id', null=True, blank=True, db_index=False, related_name='analyses',
            ),
        ),
        migrations.AddIndex(
            model_name='analysis',
            index=models.Index(fields=['release', 'module'], name='idx_analysis_release_module'),
        ),
    ]
