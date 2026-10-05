import uuid

import genetics.models

from django.db import migrations, models
from django.contrib.postgres.functions import TransactionNow
from django.utils import timezone


def replace_frequency_fks(apps, schema_editor, physical=True):
    # Materialize CreateModel's queued FK/index DDL before catalog lookup.
    for statement in schema_editor.deferred_sql:
        schema_editor.execute(statement, None)
    schema_editor.deferred_sql.clear()
    source = 'allele_frequency'
    specs = [
        ('release_id', 'data_release', 'release_id', 'fk_allele_frequency_release', 'SET NULL'),
        ('variant_id', 'variant', 'variant_id', 'fk_allele_frequency_variant', 'RESTRICT'),
        ('population_id', 'population', 'population_id', 'fk_allele_frequency_population', 'RESTRICT'),
        ('analysis_id', 'analysis', 'analysis_id', 'fk_allele_frequency_analysis', 'SET NULL'),
    ]
    resolved = []
    with schema_editor.connection.cursor() as cursor:
        for column, table, key, name, deletion in specs:
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
                raise RuntimeError(f'Expected exactly one FK: {source}.{column} -> {table}.{key}.')
            resolved.append((column, table, key, name, deletion, names[0][0]))
    # Resolve all four before changing any; quote even generated constraint names.
    def quote(identifier):
        return '"' + identifier.replace('"', '""') + '"'

    for column, table, key, name, deletion, old_name in resolved:
        schema_editor.execute(f'ALTER TABLE {quote(source)} DROP CONSTRAINT {quote(old_name)}')
        update, delete = ('CASCADE', deletion) if physical else ('NO ACTION', 'NO ACTION')
        deferrability = 'NOT DEFERRABLE' if physical else 'DEFERRABLE INITIALLY DEFERRED'
        schema_editor.execute(
            f'ALTER TABLE {quote(source)} ADD CONSTRAINT {quote(name)} '
            f'FOREIGN KEY ({quote(column)}) REFERENCES {quote(table)} ({quote(key)}) '
            f'ON UPDATE {update} ON DELETE {delete} {deferrability}'
        )


def restore_frequency_fks(apps, schema_editor):
    replace_frequency_fks(apps, schema_editor, physical=False)


class Migration(migrations.Migration):
    dependencies = [('genetics', '0009_variant_annotation')]

    operations = [
        migrations.CreateModel(
            name='AlleleFrequency',
            fields=[
                ('frequency_id', models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ('release', models.ForeignKey(
                    to='genetics.datarelease', on_delete=models.SET_NULL, db_column='release_id',
                    null=True, blank=True, db_index=False, related_name='allele_frequencies',
                )),
                ('variant', models.ForeignKey(
                    to='genetics.variant', on_delete=models.PROTECT, db_column='variant_id',
                    db_index=False, related_name='allele_frequencies',
                )),
                ('population', models.ForeignKey(
                    to='genetics.population', on_delete=models.PROTECT, db_column='population_id',
                    db_index=False, related_name='allele_frequencies',
                )),
                ('analysis', models.ForeignKey(
                    to='genetics.analysis', on_delete=models.SET_NULL, db_column='analysis_id',
                    null=True, blank=True, db_index=False, related_name='allele_frequencies',
                )),
                ('source_name', models.CharField(max_length=128)),
                ('source_version', models.CharField(max_length=64)),
                ('allele', models.TextField()),
                ('allele_count', models.BigIntegerField(null=True, blank=True)),
                ('allele_number', models.BigIntegerField(null=True, blank=True)),
                ('allele_frequency', models.DecimalField(max_digits=12, decimal_places=10, null=True, blank=True)),
                ('homozygote_count', models.BigIntegerField(null=True, blank=True)),
                ('heterozygote_count', models.BigIntegerField(null=True, blank=True)),
                ('sample_count', models.BigIntegerField(null=True, blank=True)),
                ('quality_flags', models.JSONField(null=True, blank=True)),
                ('created_at', models.DateTimeField(default=timezone.now, db_default=TransactionNow())),
            ],
            options={
                'db_table': 'allele_frequency',
                'indexes': [
                    genetics.models.PostgreSQLIndex(fields=['variant', 'population'], name='idx_frequency_variant_population'),
                    models.Index(fields=['source_name', 'source_version'], name='idx_frequency_source'),
                ],
                'constraints': [
                    models.UniqueConstraint(
                        fields=['release', 'variant', 'population', 'source_name', 'source_version', 'allele'],
                        name='uq_allele_frequency_record',
                    ),
                    models.CheckConstraint(condition=models.Q(allele_count__gte=0), name='allele_frequency_allele_count_gte_0'),
                    models.CheckConstraint(condition=models.Q(allele_number__gte=0), name='allele_frequency_allele_number_gte_0'),
                    models.CheckConstraint(condition=models.Q(homozygote_count__gte=0), name='allele_frequency_homozygote_count_gte_0'),
                    models.CheckConstraint(condition=models.Q(heterozygote_count__gte=0), name='allele_frequency_heterozygote_count_gte_0'),
                    models.CheckConstraint(condition=models.Q(sample_count__gte=0), name='allele_frequency_sample_count_gte_0'),
                    models.CheckConstraint(
                        condition=models.Q(allele_frequency__gte=0, allele_frequency__lte=1),
                        name='allele_frequency_value_range',
                    ),
                ],
            },
        ),
        migrations.RunPython(replace_frequency_fks, restore_frequency_fks),
    ]
