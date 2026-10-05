"""Create VariantAnnotation and preserve its physical PostgreSQL FKs."""

import uuid

from django.contrib.postgres.functions import TransactionNow
from django.db import migrations, models
from django.utils import timezone


def replace_annotation_fks(apps, schema_editor, physical=True):
    # CreateModel queues FK/index DDL until schema-editor exit; materialize it before lookup.
    for statement in schema_editor.deferred_sql:
        schema_editor.execute(statement, None)
    schema_editor.deferred_sql.clear()
    source = 'variant_annotation'
    specs = [
        ('variant_id', 'variant', 'variant_id', 'fk_variant_annotation_variant', 'CASCADE'),
        ('placement_id', 'variant_placement', 'placement_id', 'fk_variant_annotation_placement', 'SET NULL'),
        ('analysis_id', 'analysis', 'analysis_id', 'fk_variant_annotation_analysis', 'SET NULL'),
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
    # Resolve all three before altering any; discovered catalog names may contain quotes.
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


def restore_annotation_fks(apps, schema_editor):
    replace_annotation_fks(apps, schema_editor, physical=False)


class Migration(migrations.Migration):
    dependencies = [
        ('genoma', '0008_epigenetic_feature'),
    ]

    operations = [
        migrations.CreateModel(
            name='VariantAnnotation',
            fields=[
                ('annotation_id', models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ('variant', models.ForeignKey(
                    to='genoma.variant', on_delete=models.CASCADE, db_column='variant_id',
                    db_index=False, related_name='annotations',
                )),
                ('placement', models.ForeignKey(
                    to='genoma.variantplacement', on_delete=models.SET_NULL, db_column='placement_id',
                    null=True, blank=True, db_index=False, related_name='annotations',
                )),
                ('analysis', models.ForeignKey(
                    to='genoma.analysis', on_delete=models.SET_NULL, db_column='analysis_id',
                    null=True, blank=True, db_index=False, related_name='annotations',
                )),
                ('source_name', models.CharField(max_length=128)),
                ('source_version', models.CharField(max_length=64)),
                ('annotation_type', models.CharField(max_length=96)),
                ('gene_symbol', models.CharField(max_length=64, null=True, blank=True)),
                ('transcript_id', models.CharField(max_length=128, null=True, blank=True)),
                ('consequence', models.CharField(max_length=128, null=True, blank=True)),
                ('clinical_significance', models.CharField(max_length=128, null=True, blank=True)),
                ('evidence_level', models.CharField(max_length=64, null=True, blank=True)),
                ('score', models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True)),
                ('citation_id', models.CharField(max_length=128, null=True, blank=True)),
                ('payload', models.JSONField(null=True, blank=True)),
                ('created_at', models.DateTimeField(default=timezone.now, db_default=TransactionNow())),
            ],
            options={
                'db_table': 'variant_annotation',
                'indexes': [
                    models.Index(fields=['variant'], name='idx_variant_annotation_variant'),
                    models.Index(fields=['source_name', 'source_version'], name='idx_variant_annotation_source'),
                    models.Index(fields=['gene_symbol'], name='idx_variant_annotation_gene'),
                ],
            },
        ),
        migrations.RunPython(replace_annotation_fks, restore_annotation_fks),
    ]
