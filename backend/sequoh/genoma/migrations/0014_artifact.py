"""Create Artifact, materialize DDL, then preserve its physical FKs."""

import uuid

import genoma.models
from django.contrib.postgres.functions import TransactionNow
from django.db import migrations, models
from django.utils import timezone


def materialize_artifact_schema(apps, schema_editor):
    # Resolve replacement constraints only after CreateModel's deferred DDL is present.
    for statement in schema_editor.deferred_sql:
        schema_editor.execute(statement, None)
    schema_editor.deferred_sql.clear()


def replace_artifact_fks(apps, schema_editor, physical=True):
    source = 'artifact'
    specs = [
        ('analysis_id', 'analysis', 'analysis_id', 'fk_artifact_analysis'),
        ('release_id', 'data_release', 'release_id', 'fk_artifact_release'),
        ('sample_id', 'sample', 'sample_id', 'fk_artifact_sample'),
    ]
    resolved = []
    with schema_editor.connection.cursor() as cursor:
        for column, table, key, name in specs:
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
            resolved.append((column, table, key, name, names[0][0]))

    # Validate all three exact relations before the first DDL statement, in both directions.
    def quote(identifier):
        return '"' + identifier.replace('"', '""') + '"'

    for column, table, key, name, old_name in resolved:
        schema_editor.execute(f'ALTER TABLE {quote(source)} DROP CONSTRAINT {quote(old_name)}')
        update, delete = ('CASCADE', 'SET NULL') if physical else ('NO ACTION', 'NO ACTION')
        deferrability = 'NOT DEFERRABLE' if physical else 'DEFERRABLE INITIALLY DEFERRED'
        schema_editor.execute(
            f'ALTER TABLE {quote(source)} ADD CONSTRAINT {quote(name)} '
            f'FOREIGN KEY ({quote(column)}) REFERENCES {quote(table)} ({quote(key)}) '
            f'ON UPDATE {update} ON DELETE {delete} {deferrability}'
        )


def restore_artifact_fks(apps, schema_editor):
    replace_artifact_fks(apps, schema_editor, physical=False)


class Migration(migrations.Migration):
    dependencies = [
        ('genoma', '0013_genotype'),
    ]

    operations = [
        migrations.CreateModel(
            name='Artifact',
            fields=[
                ('artifact_id', models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ('analysis', models.ForeignKey(
                    to='genoma.analysis', on_delete=models.SET_NULL, db_column='analysis_id',
                    null=True, blank=True, db_index=False, related_name='artifacts',
                )),
                ('release', models.ForeignKey(
                    to='genoma.datarelease', on_delete=models.SET_NULL, db_column='release_id',
                    null=True, blank=True, db_index=False, related_name='artifacts',
                )),
                ('sample', models.ForeignKey(
                    to='services.sample', on_delete=models.SET_NULL, db_column='sample_id',
                    null=True, blank=True, db_index=False, related_name='artifacts',
                )),
                ('role', models.CharField(max_length=32)),
                ('artifact_type', models.CharField(max_length=64)),
                ('format', models.CharField(max_length=64)),
                ('uri', models.TextField()),
                ('checksum_sha256', genoma.models.FixedCharField(max_length=64)),
                ('size_bytes', models.BigIntegerField(null=True, blank=True)),
                ('reference_assembly', models.CharField(max_length=32, null=True, blank=True)),
                ('metadata', models.JSONField(null=True, blank=True)),
                ('created_at', models.DateTimeField(default=timezone.now, db_default=TransactionNow())),
            ],
            options={
                'db_table': 'artifact',
                'indexes': [
                    models.Index(fields=['analysis'], name='idx_artifact_analysis'),
                    models.Index(fields=['checksum_sha256'], name='idx_artifact_checksum'),
                ],
                'constraints': [
                    models.CheckConstraint(condition=models.Q(size_bytes__gte=0), name='artifact_size_bytes_gte_0'),
                ],
            },
        ),
        migrations.RunPython(materialize_artifact_schema, migrations.RunPython.noop),
        migrations.RunPython(replace_artifact_fks, restore_artifact_fks),
    ]
