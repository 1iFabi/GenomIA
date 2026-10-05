"""Create AnalysisResult, materialize DDL, then preserve its physical FKs."""

import uuid

from django.contrib.postgres.functions import TransactionNow
from django.db import migrations, models
from django.db.models import deletion
from django.utils import timezone


def materialize_analysis_result_schema(apps, schema_editor):
    # Resolve replacement constraints only after CreateModel's deferred DDL is present.
    for statement in schema_editor.deferred_sql:
        schema_editor.execute(statement, None)
    schema_editor.deferred_sql.clear()


def replace_analysis_result_fks(apps, schema_editor, physical=True):
    source = 'analysis_result'
    specs = [
        ('analysis_id', 'analysis', 'analysis_id', 'fk_result_analysis', 'RESTRICT'),
        ('participant_id', 'participant', 'participant_id', 'fk_result_participant', 'SET NULL'),
        ('sample_id', 'sample', 'sample_id', 'fk_result_sample', 'SET NULL'),
        ('release_id', 'data_release', 'release_id', 'fk_result_release', 'SET NULL'),
        ('variant_id', 'variant', 'variant_id', 'fk_result_variant', 'SET NULL'),
        ('epigenetic_feature_id', 'epigenetic_feature', 'epigenetic_feature_id',
         'fk_result_epigenetic_feature', 'SET NULL'),
        ('population_id', 'population', 'population_id', 'fk_result_population', 'SET NULL'),
    ]
    resolved = []
    with schema_editor.connection.cursor() as cursor:
        for column, table, key, name, delete_action in specs:
            cursor.execute(
                "SELECT conname FROM pg_constraint WHERE contype = 'f' "
                "AND conrelid = %s::regclass AND confrelid = %s::regclass "
                "AND conkey = ARRAY[(SELECT attnum FROM pg_attribute WHERE attrelid = conrelid "
                "AND attname = %s AND attnum > 0 AND NOT attisdropped)] "
                "AND confkey = ARRAY[(SELECT attnum FROM pg_attribute WHERE attrelid = confrelid "
                "AND attname = %s AND attnum > 0 AND NOT attisdropped)]",
                [source, table, column, key],
            )
            names = cursor.fetchall()
            if len(names) != 1:
                raise RuntimeError(
                    f'Expected exactly one FK: {source}.{column} -> {table}.{key}.'
                )
            resolved.append((column, table, key, name, delete_action, names[0][0]))

    # Validate every exact relation before the first DDL statement, in both directions.
    def quote(identifier):
        return '"' + identifier.replace('"', '""') + '"'

    for column, table, key, name, delete_action, old_name in resolved:
        schema_editor.execute(f'ALTER TABLE {quote(source)} DROP CONSTRAINT {quote(old_name)}')
        update = 'CASCADE' if physical else 'NO ACTION'
        delete = delete_action if physical else 'NO ACTION'
        deferrability = 'NOT DEFERRABLE' if physical else 'DEFERRABLE INITIALLY DEFERRED'
        schema_editor.execute(
            f'ALTER TABLE {quote(source)} ADD CONSTRAINT {quote(name)} '
            f'FOREIGN KEY ({quote(column)}) REFERENCES {quote(table)} ({quote(key)}) '
            f'ON UPDATE {update} ON DELETE {delete} {deferrability}'
        )


def restore_analysis_result_fks(apps, schema_editor):
    replace_analysis_result_fks(apps, schema_editor, physical=False)


class Migration(migrations.Migration):
    dependencies = [
        ('genoma', '0014_artifact'),
    ]

    operations = [
        migrations.CreateModel(
            name='AnalysisResult',
            fields=[
                ('result_id', models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ('analysis', models.ForeignKey(
                    to='genoma.analysis', on_delete=deletion.PROTECT, db_column='analysis_id',
                    db_index=False, related_name='results',
                )),
                ('participant', models.ForeignKey(
                    to='participants.participant', on_delete=deletion.SET_NULL, db_column='participant_id',
                    null=True, blank=True, db_index=False, related_name='analysis_results',
                )),
                ('sample', models.ForeignKey(
                    to='services.sample', on_delete=deletion.SET_NULL, db_column='sample_id',
                    null=True, blank=True, db_index=False, related_name='analysis_results',
                )),
                ('release', models.ForeignKey(
                    to='genoma.datarelease', on_delete=deletion.SET_NULL, db_column='release_id',
                    null=True, blank=True, db_index=False, related_name='analysis_results',
                )),
                ('variant', models.ForeignKey(
                    to='genoma.variant', on_delete=deletion.SET_NULL, db_column='variant_id',
                    null=True, blank=True, db_index=False, related_name='analysis_results',
                )),
                ('epigenetic_feature', models.ForeignKey(
                    to='genoma.epigeneticfeature', on_delete=deletion.SET_NULL,
                    db_column='epigenetic_feature_id', null=True, blank=True, db_index=False,
                    related_name='analysis_results',
                )),
                ('population', models.ForeignKey(
                    to='genoma.population', on_delete=deletion.SET_NULL, db_column='population_id',
                    null=True, blank=True, db_index=False, related_name='analysis_results',
                )),
                ('module', models.CharField(max_length=64)),
                ('result_type', models.CharField(max_length=96)),
                ('reference_assembly', models.CharField(max_length=32, null=True, blank=True)),
                ('contig', models.CharField(max_length=64, null=True, blank=True)),
                ('start_pos', models.BigIntegerField(null=True, blank=True)),
                ('end_pos', models.BigIntegerField(null=True, blank=True)),
                ('haplotype', models.SmallIntegerField(null=True, blank=True)),
                ('value_numeric', models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True)),
                ('value_text', models.TextField(null=True, blank=True)),
                ('value_code', models.CharField(max_length=128, null=True, blank=True)),
                ('unit', models.CharField(max_length=64, null=True, blank=True)),
                ('percentile', models.DecimalField(max_digits=7, decimal_places=4, null=True, blank=True)),
                ('confidence', models.DecimalField(max_digits=7, decimal_places=6, null=True, blank=True)),
                ('payload', models.JSONField(null=True, blank=True)),
                ('created_at', models.DateTimeField(default=timezone.now, db_default=TransactionNow())),
            ],
            options={
                'db_table': 'analysis_result',
                'indexes': [
                    models.Index(fields=['participant', 'module'], name='idx_result_participant_module'),
                    models.Index(fields=['analysis'], name='idx_result_analysis'),
                    models.Index(
                        fields=['reference_assembly', 'contig', 'start_pos', 'end_pos'],
                        name='idx_result_interval',
                    ),
                ],
                'constraints': [
                    models.CheckConstraint(
                        condition=models.Q(start_pos__gte=1), name='analysis_result_start_pos_gte_1',
                    ),
                    models.CheckConstraint(
                        condition=models.Q(end_pos__gte=models.F('start_pos')),
                        name='analysis_result_end_pos_gte_start',
                    ),
                    models.CheckConstraint(
                        condition=models.Q(haplotype__gte=0), name='analysis_result_haplotype_gte_0',
                    ),
                    models.CheckConstraint(
                        condition=models.Q(percentile__gte=0, percentile__lte=100),
                        name='analysis_result_percentile_0_100',
                    ),
                    models.CheckConstraint(
                        condition=models.Q(confidence__gte=0, confidence__lte=1),
                        name='analysis_result_confidence_0_1',
                    ),
                ],
            },
        ),
        migrations.RunPython(materialize_analysis_result_schema, migrations.RunPython.noop),
        migrations.RunPython(replace_analysis_result_fks, restore_analysis_result_fks),
    ]
