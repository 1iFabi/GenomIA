from django.db import migrations, models
from django.contrib.postgres.functions import TransactionNow
from django.utils import timezone


def materialize_membership_schema(apps, schema_editor):
    # CreateModel queues FK/index DDL; complete creation separately from replacement.
    for statement in schema_editor.deferred_sql:
        schema_editor.execute(statement, None)
    schema_editor.deferred_sql.clear()


def replace_release_epigenetic_feature_fks(apps, schema_editor, physical=True):
    source = 'release_epigenetic_feature'
    specs = [
        ('release_id', 'data_release', 'release_id', 'fk_release_epi_feature_release', 'CASCADE'),
        ('epigenetic_feature_id', 'epigenetic_feature', 'epigenetic_feature_id', 'fk_release_epi_feature_feature', 'RESTRICT'),
        ('included_by_analysis_id', 'analysis', 'analysis_id', 'fk_release_epi_feature_analysis', 'SET NULL'),
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
    # Resolve all three exact relations before any DDL, including in reverse.
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


def restore_release_epigenetic_feature_fks(apps, schema_editor):
    replace_release_epigenetic_feature_fks(apps, schema_editor, physical=False)


class Migration(migrations.Migration):
    dependencies = [('genetics', '0011_release_variant')]

    operations = [
        migrations.CreateModel(
            name='ReleaseEpigeneticFeature',
            fields=[
                ('pk', models.CompositePrimaryKey('release_id', 'epigenetic_feature_id', blank=True, editable=False, primary_key=True, serialize=False)),
                ('release', models.ForeignKey(
                    to='genetics.datarelease', on_delete=models.CASCADE, db_column='release_id',
                    db_index=False, related_name='epigenetic_feature_memberships',
                )),
                ('epigenetic_feature', models.ForeignKey(
                    to='genetics.epigeneticfeature', on_delete=models.RESTRICT, db_column='epigenetic_feature_id',
                    db_index=False, related_name='release_memberships',
                )),
                ('included_by_analysis', models.ForeignKey(
                    to='genetics.analysis', on_delete=models.SET_NULL, db_column='included_by_analysis_id',
                    null=True, blank=True, db_index=False, related_name='included_epigenetic_feature_memberships',
                )),
                ('created_at', models.DateTimeField(default=timezone.now, db_default=TransactionNow())),
            ],
            options={
                'db_table': 'release_epigenetic_feature',
                'indexes': [models.Index(fields=['epigenetic_feature'], name='idx_release_epi_feature')],
            },
        ),
        migrations.RunPython(materialize_membership_schema, migrations.RunPython.noop),
        migrations.RunPython(replace_release_epigenetic_feature_fks, restore_release_epigenetic_feature_fks),
    ]
