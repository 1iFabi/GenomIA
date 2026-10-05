import uuid

import genetics.models

from django.db import migrations, models
from django.contrib.postgres.functions import TransactionNow
from django.utils import timezone


def materialize_genotype_schema(apps, schema_editor):
    # CreateModel queues FK/index DDL; finish creation before replacement lookup.
    for statement in schema_editor.deferred_sql:
        schema_editor.execute(statement, None)
    schema_editor.deferred_sql.clear()


def replace_genotype_fks(apps, schema_editor, physical=True):
    source = 'genotype'
    specs = [
        ('release_id', 'data_release', 'release_id', 'fk_genotype_release', 'CASCADE'),
        ('variant_id', 'variant', 'variant_id', 'fk_genotype_variant', 'RESTRICT'),
        ('participant_id', 'participant', 'participant_id', 'fk_genotype_participant', 'RESTRICT'),
        ('sample_id', 'sample', 'sample_id', 'fk_genotype_sample', 'SET NULL'),
        ('analysis_id', 'analysis', 'analysis_id', 'fk_genotype_analysis', 'RESTRICT'),
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
    # Resolve all five exact relations before any DDL, in either direction.
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


def restore_genotype_fks(apps, schema_editor):
    replace_genotype_fks(apps, schema_editor, physical=False)


class Migration(migrations.Migration):
    dependencies = [
        ('genetics', '0012_release_epigenetic_feature'),
        ('participants', '0003_participant_metadata_support'),
        ('services', '0004_sample'),
    ]

    operations = [
        migrations.CreateModel(
            name='Genotype',
            fields=[
                ('genotype_id', models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ('release', models.ForeignKey(
                    to='genetics.datarelease', on_delete=models.CASCADE, db_column='release_id',
                    db_index=False, related_name='genotypes',
                )),
                ('variant', models.ForeignKey(
                    to='genetics.variant', on_delete=models.PROTECT, db_column='variant_id',
                    db_index=False, related_name='genotypes',
                )),
                ('participant', models.ForeignKey(
                    to='participants.participant', on_delete=models.PROTECT, db_column='participant_id',
                    db_index=False, related_name='genotypes',
                )),
                ('sample', models.ForeignKey(
                    to='services.sample', on_delete=models.SET_NULL, db_column='sample_id',
                    null=True, blank=True, db_index=False, related_name='genotypes',
                )),
                ('analysis', models.ForeignKey(
                    to='genetics.analysis', on_delete=models.PROTECT, db_column='analysis_id',
                    db_index=False, related_name='genotypes',
                )),
                ('genotype', models.CharField(max_length=32)),
                ('phased', models.BooleanField(default=False, db_default=False)),
                ('phase_set', models.CharField(max_length=64, null=True, blank=True)),
                ('dosage', models.DecimalField(max_digits=6, decimal_places=3, null=True, blank=True)),
                ('genotype_quality', models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)),
                ('read_depth', models.IntegerField(null=True, blank=True)),
                ('allele_depths', models.JSONField(null=True, blank=True)),
                ('filters', models.JSONField(null=True, blank=True)),
                ('created_at', models.DateTimeField(default=timezone.now, db_default=TransactionNow())),
            ],
            options={
                'db_table': 'genotype',
                'indexes': [
                    genetics.models.PostgreSQLIndex(fields=['participant', 'release'], name='idx_genotype_participant_release'),
                    models.Index(fields=['variant', 'release'], name='idx_genotype_variant_release'),
                ],
                'constraints': [
                    models.UniqueConstraint(
                        fields=['analysis', 'participant', 'sample', 'variant'], name='uq_genotype_analysis_sample_variant',
                    ),
                    models.CheckConstraint(condition=models.Q(genotype_quality__gte=0), name='genotype_quality_gte_0'),
                    models.CheckConstraint(condition=models.Q(read_depth__gte=0), name='genotype_read_depth_gte_0'),
                ],
            },
        ),
        migrations.RunPython(materialize_genotype_schema, migrations.RunPython.noop),
        migrations.RunPython(replace_genotype_fks, restore_genotype_fks),
    ]
