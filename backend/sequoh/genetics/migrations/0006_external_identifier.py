import uuid

from django.db import migrations, models
from django.contrib.postgres.functions import TransactionNow
from django.utils import timezone


def replace_identifier_fks(apps, schema_editor, physical=True):
    # CreateModel queues FK/index DDL until schema-editor exit; materialize it before lookup.
    for statement in schema_editor.deferred_sql:
        schema_editor.execute(statement, None)
    schema_editor.deferred_sql.clear()
    specs = [
        ('variant_id', 'variant', 'variant_id', 'fk_external_identifier_variant', 'CASCADE'),
        ('replaced_by_identifier_id', 'external_identifier', 'external_identifier_id', 'fk_external_identifier_replacement', 'SET NULL'),
    ]
    resolved = []
    with schema_editor.connection.cursor() as cursor:
        for column, table, key, name, deletion in specs:
            cursor.execute(
                "SELECT conname FROM pg_constraint WHERE contype = 'f' "
                "AND conrelid = 'external_identifier'::regclass AND confrelid = %s::regclass "
                "AND conkey = ARRAY[(SELECT attnum FROM pg_attribute WHERE attrelid = conrelid "
                "AND attname = %s AND attnum > 0 AND NOT attisdropped)] "
                "AND confkey = ARRAY[(SELECT attnum FROM pg_attribute WHERE attrelid = confrelid "
                "AND attname = %s AND attnum > 0 AND NOT attisdropped)]",
                [table, column, key],
            )
            names = cursor.fetchall()
            if len(names) != 1:
                raise RuntimeError(f'Expected exactly one FK: external_identifier.{column} -> {table}.{key}.')
            resolved.append((column, table, key, name, deletion, names[0][0]))
    # Resolve both constraints before changing either, so a failed lookup cannot partially replace them.
    quote = schema_editor.quote_name
    for column, table, key, name, deletion, old_name in resolved:
        schema_editor.execute('ALTER TABLE "external_identifier" DROP CONSTRAINT ' + quote(old_name))
        update, delete = ('CASCADE', deletion) if physical else ('NO ACTION', 'NO ACTION')
        deferrability = 'NOT DEFERRABLE' if physical else 'DEFERRABLE INITIALLY DEFERRED'
        schema_editor.execute(
            f'ALTER TABLE "external_identifier" ADD CONSTRAINT {quote(name)} '
            f'FOREIGN KEY ({quote(column)}) REFERENCES {quote(table)} ({quote(key)}) '
            f'ON UPDATE {update} ON DELETE {delete} {deferrability}'
        )


def restore_identifier_fks(apps, schema_editor):
    replace_identifier_fks(apps, schema_editor, physical=False)


class Migration(migrations.Migration):
    dependencies = [('genetics', '0005_variant_placement')]

    operations = [
        migrations.CreateModel(
            name='ExternalIdentifier',
            fields=[
                ('external_identifier_id', models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ('variant', models.ForeignKey(
                    to='genetics.variant', on_delete=models.CASCADE, db_column='variant_id',
                    db_index=False, related_name='external_identifiers',
                )),
                ('replaced_by_identifier', models.ForeignKey(
                    to='genetics.externalidentifier', on_delete=models.SET_NULL, db_column='replaced_by_identifier_id',
                    null=True, blank=True, db_index=False, related_name='replaced_identifiers',
                )),
                ('namespace', models.CharField(max_length=64)),
                ('accession', models.CharField(max_length=255)),
                ('version', models.CharField(max_length=64, null=True, blank=True)),
                ('status', models.CharField(max_length=32, default='active', db_default='active')),
                ('source_release', models.CharField(max_length=128, null=True, blank=True)),
                ('is_primary', models.BooleanField(default=False, db_default=False)),
                ('created_at', models.DateTimeField(default=timezone.now, db_default=TransactionNow())),
            ],
            options={
                'db_table': 'external_identifier',
                'indexes': [models.Index(fields=['namespace', 'accession'], name='idx_external_identifier_lookup')],
                'constraints': [models.UniqueConstraint(fields=['namespace', 'accession', 'version'], name='uq_external_identifier')],
            },
        ),
        migrations.RunPython(replace_identifier_fks, restore_identifier_fks),
    ]
