from django.db import migrations, models
from django.contrib.postgres.functions import TransactionNow
from django.utils import timezone


def replace_release_variant_fks(apps, schema_editor, physical=True):
    # Materialize CreateModel's queued FK/index DDL before catalog lookup.
    for statement in schema_editor.deferred_sql:
        schema_editor.execute(statement, None)
    schema_editor.deferred_sql.clear()
    source = 'release_variant'
    specs = [
        ('release_id', 'data_release', 'release_id', 'fk_release_variant_release', 'CASCADE'),
        ('variant_id', 'variant', 'variant_id', 'fk_release_variant_variant', 'RESTRICT'),
        ('placement_id', 'variant_placement', 'placement_id', 'fk_release_variant_placement', 'RESTRICT'),
        ('included_by_analysis_id', 'analysis', 'analysis_id', 'fk_release_variant_analysis', 'SET NULL'),
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
    # Resolve every FK before changing any; escape generated constraint names too.
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


def restore_release_variant_fks(apps, schema_editor):
    replace_release_variant_fks(apps, schema_editor, physical=False)


class Migration(migrations.Migration):
    dependencies = [('genetics', '0010_allele_frequency')]

    operations = [
        migrations.CreateModel(
            name='ReleaseVariant',
            fields=[
                ('pk', models.CompositePrimaryKey('release_id', 'variant_id', blank=True, editable=False, primary_key=True, serialize=False)),
                ('release', models.ForeignKey(
                    to='genetics.datarelease', on_delete=models.CASCADE, db_column='release_id',
                    db_index=False, related_name='variant_memberships',
                )),
                ('variant', models.ForeignKey(
                    to='genetics.variant', on_delete=models.RESTRICT, db_column='variant_id',
                    db_index=False, related_name='release_memberships',
                )),
                ('placement', models.ForeignKey(
                    to='genetics.variantplacement', on_delete=models.RESTRICT, db_column='placement_id',
                    null=True, blank=True, db_index=False, related_name='release_memberships',
                )),
                ('included_by_analysis', models.ForeignKey(
                    to='genetics.analysis', on_delete=models.SET_NULL, db_column='included_by_analysis_id',
                    null=True, blank=True, db_index=False, related_name='included_variant_memberships',
                )),
                ('inclusion_status', models.CharField(max_length=32, default='included', db_default='included')),
                ('created_at', models.DateTimeField(default=timezone.now, db_default=TransactionNow())),
            ],
            options={
                'db_table': 'release_variant',
                'indexes': [models.Index(fields=['variant'], name='idx_release_variant_variant')],
            },
        ),
        migrations.RunPython(replace_release_variant_fks, restore_release_variant_fks),
    ]
