"""Create Population and preserve its physical PostgreSQL parent FK."""

import uuid

from django.contrib.postgres.functions import TransactionNow
from django.db import migrations, models
from django.utils import timezone


def replace_population_fk(apps, schema_editor, physical=True):
    # CreateModel queues FK/index DDL until schema-editor exit; materialize it before lookup.
    for statement in schema_editor.deferred_sql:
        schema_editor.execute(statement, None)
    schema_editor.deferred_sql.clear()
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            "SELECT conname FROM pg_constraint WHERE contype = 'f' "
            "AND conrelid = 'population'::regclass AND confrelid = 'population'::regclass "
            "AND conkey = ARRAY[(SELECT attnum FROM pg_attribute WHERE attrelid = conrelid "
            "AND attname = 'parent_population_id' AND attnum > 0 AND NOT attisdropped)] "
            "AND confkey = ARRAY[(SELECT attnum FROM pg_attribute WHERE attrelid = confrelid "
            "AND attname = 'population_id' AND attnum > 0 AND NOT attisdropped)]"
        )
        names = cursor.fetchall()
    if len(names) != 1:
        raise RuntimeError('Expected exactly one FK: population.parent_population_id -> population.population_id.')
    schema_editor.execute('ALTER TABLE "population" DROP CONSTRAINT ' + schema_editor.quote_name(names[0][0]))
    update, delete = ('CASCADE', 'SET NULL') if physical else ('NO ACTION', 'NO ACTION')
    deferrability = 'NOT DEFERRABLE' if physical else 'DEFERRABLE INITIALLY DEFERRED'
    schema_editor.execute(
        'ALTER TABLE "population" ADD CONSTRAINT "fk_population_parent" '
        'FOREIGN KEY ("parent_population_id") REFERENCES "population" ("population_id") '
        f'ON UPDATE {update} ON DELETE {delete} {deferrability}'
    )


def restore_population_fk(apps, schema_editor):
    replace_population_fk(apps, schema_editor, physical=False)


class Migration(migrations.Migration):
    dependencies = [
        ('genoma', '0006_external_identifier'),
    ]

    operations = [
        migrations.CreateModel(
            name='Population',
            fields=[
                ('population_id', models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ('parent_population', models.ForeignKey(
                    to='genoma.population', on_delete=models.SET_NULL, db_column='parent_population_id',
                    null=True, blank=True, db_index=False, related_name='child_populations',
                )),
                ('code', models.CharField(max_length=64)),
                ('name', models.CharField(max_length=128)),
                ('description', models.TextField(null=True, blank=True)),
                ('geographic_region', models.CharField(max_length=128, null=True, blank=True)),
                ('is_internal', models.BooleanField(default=False, db_default=False)),
                ('is_masked', models.BooleanField(default=False, db_default=False)),
                ('metadata', models.JSONField(null=True, blank=True)),
                ('created_at', models.DateTimeField(default=timezone.now, db_default=TransactionNow())),
            ],
            options={
                'db_table': 'population',
                'constraints': [models.UniqueConstraint(fields=['code'], name='uq_population_code')],
            },
        ),
        migrations.RunPython(replace_population_fk, restore_population_fk),
    ]
