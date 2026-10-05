"""Create VariantPlacement and preserve its physical PostgreSQL FK."""

import uuid

import genoma.models
from django.contrib.postgres.functions import TransactionNow
from django.db import migrations, models
from django.utils import timezone


def replace_variant_fk(apps, schema_editor, cascade=True):
    # CreateModel queues FK/index DDL until schema-editor exit; materialize it before lookup.
    for statement in schema_editor.deferred_sql:
        schema_editor.execute(statement, None)
    schema_editor.deferred_sql.clear()
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            "SELECT conname FROM pg_constraint WHERE contype = 'f' "
            "AND conrelid = 'variant_placement'::regclass AND confrelid = 'variant'::regclass "
            "AND conkey = ARRAY[(SELECT attnum FROM pg_attribute WHERE attrelid = conrelid AND attname = 'variant_id')] "
            "AND confkey = ARRAY[(SELECT attnum FROM pg_attribute WHERE attrelid = confrelid AND attname = 'variant_id')]"
        )
        names = cursor.fetchall()
    if len(names) != 1:
        raise RuntimeError('Expected exactly one FK: variant_placement.variant_id -> variant.variant_id.')
    schema_editor.execute('ALTER TABLE "variant_placement" DROP CONSTRAINT ' + schema_editor.quote_name(names[0][0]))
    action = 'CASCADE' if cascade else 'NO ACTION'
    deferrability = 'NOT DEFERRABLE' if cascade else 'DEFERRABLE INITIALLY DEFERRED'
    schema_editor.execute(
        'ALTER TABLE "variant_placement" ADD CONSTRAINT "fk_variant_placement_variant" '
        'FOREIGN KEY ("variant_id") REFERENCES "variant" ("variant_id") '
        f'ON UPDATE {action} ON DELETE {action} {deferrability}'
    )


def restore_variant_fk(apps, schema_editor):
    replace_variant_fk(apps, schema_editor, cascade=False)


class Migration(migrations.Migration):
    dependencies = [
        ('genoma', '0004_variant'),
    ]

    operations = [
        migrations.CreateModel(
            name='VariantPlacement',
            fields=[
                ('placement_id', models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ('variant', models.ForeignKey(
                    to='genoma.variant', on_delete=models.CASCADE, db_column='variant_id',
                    db_index=False, related_name='placements',
                )),
                ('reference_assembly', models.CharField(max_length=32)),
                ('contig', models.CharField(max_length=64)),
                ('start_pos', models.BigIntegerField()),
                ('end_pos', models.BigIntegerField()),
                ('coordinate_system', models.CharField(max_length=32, default='1-based-inclusive', db_default='1-based-inclusive')),
                ('reference_allele', models.TextField(null=True, blank=True)),
                ('alternate_allele', models.TextField(null=True, blank=True)),
                ('strand', genoma.models.FixedCharField(max_length=1, null=True, blank=True)),
                ('sv_length', models.BigIntegerField(null=True, blank=True)),
                ('breakend', models.JSONField(null=True, blank=True)),
                ('is_canonical', models.BooleanField(default=False, db_default=False)),
                ('normalized', models.BooleanField(default=False, db_default=False)),
                ('metadata', models.JSONField(null=True, blank=True)),
                ('created_at', models.DateTimeField(default=timezone.now, db_default=TransactionNow())),
            ],
            options={
                'db_table': 'variant_placement',
                'indexes': [
                    models.Index(fields=['reference_assembly', 'contig', 'start_pos', 'end_pos'], name='idx_variant_placement_region'),
                    models.Index(fields=['variant'], name='idx_variant_placement_variant'),
                ],
                'constraints': [
                    models.CheckConstraint(condition=models.Q(start_pos__gte=1), name='variant_placement_start_gte_1'),
                    models.CheckConstraint(condition=models.Q(end_pos__gte=models.F('start_pos')), name='variant_placement_end_gte_start'),
                ],
            },
        ),
        migrations.RunPython(replace_variant_fk, restore_variant_fk),
    ]
