import json
import uuid
from datetime import timedelta
from importlib import import_module, reload
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth.models import Group, User
from django.contrib.postgres.functions import TransactionNow
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import DataError, IntegrityError, connection, transaction
from django.db.migrations.loader import MigrationLoader
from django.db.models.deletion import CASCADE, PROTECT, SET_NULL, ProtectedError
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.jwt_utils import encode_jwt
from accounts.models import AppUser
from accounts.roles import grant_admin_role, grant_analyst_role, grant_reception_role
from genetics import models as domain
from genetics.models import SNP, UserSNP
from genetics.upload_views import UploadGeneticFileAPIView
from profiles.models import Profile, ServiceStatus
from services.models import (
    Purchase, PurchaseStatus, Sample, ServiceRequest, ServiceStatus as RequestStatus,
    ServiceStatusLog,
)


class ExternalIdentifierTests(TestCase):
    def setUp(self):
        self.assertTrue(connection.settings_dict['NAME'].startswith('gdb_test_'))
        self.variant = domain.Variant.objects.create(variant_type='synthetic-identifier')

    def identifier(self, **changes):
        return domain.ExternalIdentifier(**(dict(
            variant=self.variant, namespace='custom-namespace', accession=uuid.uuid4().hex,
        ) | changes))

    def fk_actions(self):
        with connection.cursor() as cursor:
            cursor.execute('SELECT conname, confdeltype, confupdtype, condeferrable, condeferred FROM pg_constraint '
                           "WHERE conrelid = 'external_identifier'::regclass AND contype = 'f'")
            return {row[0]: row[1:] for row in cursor.fetchall()}

    def test_minimal_identifier_has_orm_defaults_and_nullable_fields(self):
        self.assertTrue(hasattr(domain, 'ExternalIdentifier'), 'ExternalIdentifier is missing.')
        identifier = domain.ExternalIdentifier(variant=self.variant, namespace='custom-namespace', accession='synthetic')
        identifier.full_clean()
        identifier.save()
        identifier.refresh_from_db()
        self.assertIsInstance(identifier.pk, uuid.UUID)
        self.assertEqual(identifier.pk.version, 4)
        self.assertEqual(identifier.variant, self.variant)
        self.assertEqual(identifier.status, 'active')
        self.assertIs(identifier.is_primary, False)
        self.assertTrue(timezone.is_aware(identifier.created_at))
        for field in ('replaced_by_identifier_id', 'version', 'source_release'):
            self.assertIsNone(getattr(identifier, field))

    def test_exact_ten_columns_defaults_keys_unique_and_only_lookup_index(self):
        columns = {
            'external_identifier_id': ('uuid', None, 'NO', None),
            'variant_id': ('uuid', None, 'NO', None),
            'replaced_by_identifier_id': ('uuid', None, 'YES', None),
            'namespace': ('character varying', 64, 'NO', None),
            'accession': ('character varying', 255, 'NO', None),
            'version': ('character varying', 64, 'YES', None),
            'status': ('character varying', 32, 'NO', "'active'::character varying"),
            'source_release': ('character varying', 128, 'YES', None),
            'is_primary': ('boolean', None, 'NO', 'false'),
            'created_at': ('timestamp with time zone', None, 'NO', 'CURRENT_TIMESTAMP'),
        }
        model = domain.ExternalIdentifier
        self.assertEqual((model._meta.db_table, model._meta.pk.name), ('external_identifier', 'external_identifier_id'))
        self.assertEqual({field.column for field in model._meta.local_fields}, set(columns))
        self.assertIs(model._meta.pk.default, uuid.uuid4)
        self.assertFalse(model._meta.pk.editable)
        for field in model._meta.local_fields:
            _, length, nullable, _ = columns[field.column]
            self.assertEqual((field.null, field.blank), (nullable == 'YES', nullable == 'YES'))
            if length is not None:
                self.assertEqual(field.max_length, length)
            self.assertFalse(field.choices)
        status, primary, created = (model._meta.get_field(name) for name in ('status', 'is_primary', 'created_at'))
        self.assertEqual((status.default, status.db_default), ('active', 'active'))
        self.assertIs(primary.default, False)
        self.assertIs(primary.db_default, False)
        self.assertIs(created.default, timezone.now)
        self.assertIsInstance(created.db_default, TransactionNow)
        expected_fks = {('variant_id', ('variant', 'variant_id')),
                        ('replaced_by_identifier_id', ('external_identifier', 'external_identifier_id'))}
        for name, target, action in (('variant', domain.Variant, CASCADE), ('replaced_by_identifier', model, SET_NULL)):
            relation = model._meta.get_field(name)
            self.assertIs(relation.remote_field.model, target)
            self.assertIs(relation.remote_field.on_delete, action)
            self.assertFalse(relation.db_index)
        self.assertEqual({index.name: index.fields for index in model._meta.indexes}, {
            'idx_external_identifier_lookup': ['namespace', 'accession'],
        })
        unique, = model._meta.constraints
        self.assertEqual((unique.name, unique.fields, unique.nulls_distinct),
                         ('uq_external_identifier', ('namespace', 'accession', 'version'), None))
        with connection.cursor() as cursor:
            cursor.execute('SELECT column_name, data_type, character_maximum_length, is_nullable, column_default '
                           'FROM information_schema.columns WHERE table_schema = current_schema() '
                           "AND table_name = 'external_identifier'")
            self.assertEqual({row[0]: row[1:] for row in cursor.fetchall()}, columns)
            constraints = connection.introspection.get_constraints(cursor, 'external_identifier')
            cursor.execute("SELECT indexname FROM pg_indexes WHERE schemaname = current_schema() AND tablename = 'external_identifier'")
            self.assertEqual({row[0] for row in cursor.fetchall()}, {
                'external_identifier_pkey', 'uq_external_identifier', 'idx_external_identifier_lookup',
            })
        self.assertEqual([info['columns'] for info in constraints.values() if info['primary_key']], [['external_identifier_id']])
        self.assertEqual({name: info['columns'] for name, info in constraints.items() if info['unique'] and not info['primary_key']},
                         {'uq_external_identifier': ['namespace', 'accession', 'version']})
        self.assertEqual({(info['columns'][0], info['foreign_key']) for info in constraints.values() if info['foreign_key']}, expected_fks)
        self.assertEqual({name: info['columns'] for name, info in constraints.items() if info['index']},
                         {'idx_external_identifier_lookup': ['namespace', 'accession']})
        self.assertEqual(self.fk_actions(), {'fk_external_identifier_variant': ('c', 'c', False, False),
                                            'fk_external_identifier_replacement': ('n', 'c', False, False)})

    def test_raw_sql_defaults_use_unquoted_active_false_and_transaction_timestamp(self):
        with connection.cursor() as cursor:
            cursor.execute('INSERT INTO external_identifier (external_identifier_id, variant_id, namespace, accession) '
                           'VALUES (%s, %s, %s, %s) RETURNING status, is_primary, replaced_by_identifier_id, version, '
                           'source_release, created_at, transaction_timestamp()',
                           [uuid.uuid4(), self.variant.pk, 'synthetic-sql', 'synthetic'])
            status, primary, *optional, created_at, database_now = cursor.fetchone()
        self.assertEqual(status, 'active')  # SQL v01.5 triple-quoted literals would embed quote characters.
        self.assertIs(primary, False)
        self.assertEqual(optional, [None] * 3)
        self.assertTrue(timezone.is_aware(created_at))
        self.assertEqual(created_at, database_now)

    def test_explicit_values_round_trip_without_legacy_side_effects_or_namespace_enum(self):
        replacement = self.identifier()
        replacement.save()
        legacy = (SNP, UserSNP, domain.Analysis, domain.DataRelease, domain.Variant, domain.VariantPlacement)
        before = {model: model.objects.count() for model in legacy}
        values = dict(namespace='unlisted-namespace', accession='synthetic-accession', version='synthetic-version',
                      status='custom-status', source_release='synthetic-release', is_primary=True,
                      replaced_by_identifier=replacement, created_at=timezone.now())
        identifier = self.identifier(**values)
        identifier.full_clean()
        identifier.save()
        identifier.refresh_from_db()
        self.assertEqual({field: getattr(identifier, field) for field in values}, values)
        self.assertEqual({model: model.objects.count() for model in legacy}, before)

    def test_composite_uniqueness_rejects_nonnull_duplicates_but_accepts_null_versions(self):
        first = self.identifier(accession='shared-accession', version='v1')
        first.save()
        with self.assertRaises(IntegrityError) as error, transaction.atomic():
            self.identifier(accession=first.accession, version=first.version).save()
        self.assertEqual(error.exception.__cause__.diag.constraint_name, 'uq_external_identifier')
        for changes in ({'version': 'v2'}, {'accession': 'other'}, {'namespace': 'other'}, {'version': None}, {'version': None}):
            identifier = self.identifier(**(dict(accession=first.accession, version=first.version) | changes))
            identifier.full_clean()
            identifier.save()
        self.assertEqual(domain.ExternalIdentifier.objects.count(), 6)
        self.assertEqual(domain.ExternalIdentifier.objects.filter(accession=first.accession, version__isnull=True).count(), 2)

    def test_required_columns_primary_key_and_immediate_foreign_keys_are_enforced(self):
        values = dict(external_identifier_id=uuid.uuid4(), variant_id=self.variant.pk, namespace='synthetic',
                      accession='synthetic', status='active', is_primary=False, created_at=timezone.now())
        columns, placeholders = ', '.join(connection.ops.quote_name(field) for field in values), ', '.join(['%s'] * len(values))
        for field in values:
            with self.subTest(null_column=field):
                with self.assertRaises(IntegrityError) as error, transaction.atomic():
                    with connection.cursor() as cursor:
                        cursor.execute(f'INSERT INTO external_identifier ({columns}) VALUES ({placeholders})',
                                       [None if name == field else value for name, value in values.items()])
                self.assertEqual(error.exception.__cause__.diag.column_name, field)
        for field in ('variant', 'replaced_by_identifier'):
            orphan = self.identifier(**{f'{field}_id': uuid.uuid4()})
            with self.subTest(orphan=field):
                with self.assertRaises(ValidationError) as error:
                    orphan.full_clean()
                self.assertIn(field, error.exception.message_dict)
                with self.assertRaises(IntegrityError), transaction.atomic():
                    orphan.save()
                    self.fail('External identifier FK must reject missing references immediately.')
        first = self.identifier()
        first.save()
        with self.assertRaises(IntegrityError), transaction.atomic():
            domain.ExternalIdentifier.objects.bulk_create([self.identifier(external_identifier_id=first.pk)])

    def test_all_varchar_boundaries_and_overflows_in_orm_and_database(self):
        for field, length in (('namespace', 64), ('accession', 255), ('version', 64), ('status', 32), ('source_release', 128)):
            with self.subTest(field=field):
                boundary = self.identifier(**{field: 'x' * length})
                boundary.full_clean()
                boundary.save()
                boundary.refresh_from_db()
                self.assertEqual(getattr(boundary, field), 'x' * length)
                too_long = self.identifier(**{field: 'x' * (length + 1)})
                with self.assertRaises(ValidationError) as error:
                    too_long.full_clean()
                self.assertIn(field, error.exception.message_dict)
                with self.assertRaises(DataError), transaction.atomic():
                    too_long.save()

    def test_raw_variant_update_delete_cascades_and_preserves_other_variant_identifiers(self):
        identifier = self.identifier()
        identifier.save()
        other = domain.Variant.objects.create(variant_type='synthetic-other')
        remaining = self.identifier(variant=other, replaced_by_identifier=identifier)
        remaining.save()
        new_id = uuid.uuid4()
        with connection.cursor() as cursor:
            cursor.execute('UPDATE variant SET variant_id = %s WHERE variant_id = %s', [new_id, self.variant.pk])
            identifier.refresh_from_db()
            self.assertEqual(identifier.variant_id, new_id)
            cursor.execute('DELETE FROM variant WHERE variant_id = %s', [new_id])
        remaining.refresh_from_db()
        self.assertIsNone(remaining.replaced_by_identifier_id)
        self.assertEqual(list(domain.ExternalIdentifier.objects.values_list('pk', flat=True)), [remaining.pk])
        self.assertTrue(domain.Variant.objects.filter(pk=other.pk).exists())

    def test_raw_replacement_update_cascades_and_delete_sets_references_null(self):
        replacement = self.identifier()
        replacement.save()
        references = [self.identifier(replaced_by_identifier=replacement) for _ in range(2)]
        domain.ExternalIdentifier.objects.bulk_create(references)
        new_id = uuid.uuid4()
        with connection.cursor() as cursor:
            cursor.execute('UPDATE external_identifier SET external_identifier_id = %s WHERE external_identifier_id = %s', [new_id, replacement.pk])
            self.assertEqual(list(domain.ExternalIdentifier.objects.exclude(pk=new_id).values_list('replaced_by_identifier_id', flat=True)), [new_id] * 2)
            cursor.execute('DELETE FROM external_identifier WHERE external_identifier_id = %s', [new_id])
        self.assertEqual(list(domain.ExternalIdentifier.objects.values_list('replaced_by_identifier_id', flat=True)), [None] * 2)
        self.assertTrue(domain.Variant.objects.filter(pk=self.variant.pk).exists())

    def test_orm_variant_cascade_and_replacement_set_null_match_database_actions(self):
        replacement = self.identifier()
        replacement.save()
        other = domain.Variant.objects.create(variant_type='synthetic-other')
        remaining = self.identifier(variant=other, replaced_by_identifier=replacement)
        remaining.save()
        replacement.delete()
        remaining.refresh_from_db()
        self.assertIsNone(remaining.replaced_by_identifier_id)
        self.identifier().save()
        self.variant.delete()
        self.assertEqual(list(domain.ExternalIdentifier.objects.values_list('pk', flat=True)), [remaining.pk])

    def test_fk_reverse_restores_django_defaults_and_lookup_fails_closed(self):
        operation = import_module('genetics.migrations.0006_external_identifier').Migration.operations[1]
        state = MigrationLoader(connection).project_state([('genetics', '0006_external_identifier')])
        with connection.schema_editor() as editor, connection.cursor() as cursor:
            expected = self.fk_actions()
            operation.database_backwards('genetics', editor, state, state)
            restored = {name: ('a', 'a', True, True) for name in expected}
            self.assertEqual(self.fk_actions(), restored)
            operation.database_forwards('genetics', editor, state, state)
            self.assertEqual(self.fk_actions(), expected)
            operation.database_backwards('genetics', editor, state, state)
            for column, table, key, name in (
                ('variant_id', 'variant', 'variant_id', 'fk_external_identifier_variant'),
                ('replaced_by_identifier_id', 'external_identifier', 'external_identifier_id', 'fk_external_identifier_replacement'),
            ):
                for case, sql in (
                    ('missing', f'ALTER TABLE external_identifier DROP CONSTRAINT {name}'),
                    ('ambiguous', f'ALTER TABLE external_identifier ADD CONSTRAINT duplicate_fk FOREIGN KEY ({column}) '
                     f'REFERENCES {table} ({key}) DEFERRABLE INITIALLY DEFERRED'),
                ):
                    with self.subTest(column=column, case=case), transaction.atomic():
                        cursor.execute(sql)
                        before = self.fk_actions()
                        with self.assertRaisesMessage(RuntimeError, 'Expected exactly one FK'):
                            operation.database_forwards('genetics', editor, state, state)
                        self.assertEqual(self.fk_actions(), before)  # Neither FK changes if either lookup fails.
                        transaction.set_rollback(True)
            operation.database_forwards('genetics', editor, state, state)

    def test_fk_lookup_matches_source_and_target_attnums_not_other_self_references(self):
        operation = import_module('genetics.migrations.0006_external_identifier').Migration.operations[1]
        state = MigrationLoader(connection).project_state([('genetics', '0006_external_identifier')])
        with transaction.atomic(), connection.schema_editor() as editor, connection.cursor() as cursor:
            expected = self.fk_actions()
            cursor.execute('ALTER TABLE external_identifier ADD CONSTRAINT decoy_unique UNIQUE (variant_id)')
            for name, source, target in (('decoy_source', 'variant_id', 'external_identifier_id'),
                                         ('decoy_target', 'replaced_by_identifier_id', 'variant_id')):
                cursor.execute(f'ALTER TABLE external_identifier ADD CONSTRAINT {name} FOREIGN KEY ({source}) '
                               f'REFERENCES external_identifier ({target}) DEFERRABLE INITIALLY DEFERRED')
            operation.database_backwards('genetics', editor, state, state)
            operation.database_forwards('genetics', editor, state, state)
            self.assertEqual(self.fk_actions(), expected | {name: ('a', 'a', True, True) for name in ('decoy_source', 'decoy_target')})
            transaction.set_rollback(True)

    def test_schema_only_migration_dependency_and_state_match_model(self):
        with self.assertNumQueries(0):
            migration = reload(import_module('genetics.migrations.0006_external_identifier')).Migration
        self.assertEqual(migration.dependencies, [('genetics', '0005_variant_placement')])
        self.assertEqual([type(operation).__name__ for operation in migration.operations], ['CreateModel', 'RunPython'])
        self.assertEqual(migration.operations[0].name, 'ExternalIdentifier')
        historical = MigrationLoader(connection).project_state([('genetics', '0006_external_identifier')]).apps.get_model('genetics', 'ExternalIdentifier')
        self.assertEqual(historical._meta.db_table, domain.ExternalIdentifier._meta.db_table)
        self.assertEqual({field.name: field.deconstruct()[1:] for field in historical._meta.local_fields},
                         {field.name: field.deconstruct()[1:] for field in domain.ExternalIdentifier._meta.local_fields})
        self.assertEqual(historical._meta.indexes, domain.ExternalIdentifier._meta.indexes)
        self.assertEqual(historical._meta.constraints, domain.ExternalIdentifier._meta.constraints)
        call_command('check')
        call_command('makemigrations', check=True, dry_run=True)


class VariantPlacementTests(TestCase):
    def setUp(self):
        self.assertTrue(connection.settings_dict['NAME'].startswith('gdb_test_'))
        self.variant = domain.Variant.objects.create(variant_type='synthetic-placement')

    def placement(self, **changes):
        return domain.VariantPlacement(**(dict(
            variant_id=self.variant.pk, reference_assembly='GRCh38', contig='1', start_pos=1, end_pos=1,
        ) | changes))

    def test_minimal_placement_has_orm_defaults_and_nullable_fields(self):
        self.assertTrue(hasattr(domain, 'VariantPlacement'), 'Assembly-specific VariantPlacement is missing.')
        placement = self.placement()
        placement.full_clean()
        placement.save()
        placement.refresh_from_db()
        self.assertIsInstance(placement.pk, uuid.UUID)
        self.assertEqual(placement.pk.version, 4)
        self.assertEqual(placement.variant, self.variant)
        # SQL v01.5's triple-quoted literal would store quote characters, not the intended coordinate label.
        self.assertEqual(placement.coordinate_system, '1-based-inclusive')
        self.assertIs(placement.is_canonical, False)
        self.assertIs(placement.normalized, False)
        self.assertTrue(timezone.is_aware(placement.created_at))
        for field in ('reference_allele', 'alternate_allele', 'strand', 'sv_length', 'breakend', 'metadata'):
            self.assertIsNone(getattr(placement, field))

    def test_exact_sixteen_physical_columns_defaults_keys_checks_and_indexes(self):
        columns = {
            'placement_id': ('uuid', None, 'NO', None),
            'variant_id': ('uuid', None, 'NO', None),
            'reference_assembly': ('character varying', 32, 'NO', None),
            'contig': ('character varying', 64, 'NO', None),
            'start_pos': ('bigint', None, 'NO', None),
            'end_pos': ('bigint', None, 'NO', None),
            'coordinate_system': ('character varying', 32, 'NO', "'1-based-inclusive'::character varying"),
            'reference_allele': ('text', None, 'YES', None),
            'alternate_allele': ('text', None, 'YES', None),
            'strand': ('character', 1, 'YES', None),
            'sv_length': ('bigint', None, 'YES', None),
            'breakend': ('jsonb', None, 'YES', None),
            'is_canonical': ('boolean', None, 'NO', 'false'),
            'normalized': ('boolean', None, 'NO', 'false'),
            'metadata': ('jsonb', None, 'YES', None),
            'created_at': ('timestamp with time zone', None, 'NO', 'CURRENT_TIMESTAMP'),
        }
        model = domain.VariantPlacement
        self.assertEqual((model._meta.db_table, model._meta.pk.name), ('variant_placement', 'placement_id'))
        self.assertEqual({field.column for field in model._meta.local_fields}, set(columns))
        self.assertIs(model._meta.pk.default, uuid.uuid4)
        self.assertFalse(model._meta.pk.editable)
        for field in model._meta.local_fields:
            _, length, nullable, _ = columns[field.column]
            self.assertEqual((field.null, field.blank), (nullable == 'YES', nullable == 'YES'))
            if length is not None:
                self.assertEqual(field.max_length, length)
        coordinate = model._meta.get_field('coordinate_system')
        self.assertEqual((coordinate.default, coordinate.db_default), ('1-based-inclusive', '1-based-inclusive'))
        for name in ('is_canonical', 'normalized'):
            field = model._meta.get_field(name)
            self.assertIs(field.default, False)
            self.assertIs(field.db_default, False)
        created_at = model._meta.get_field('created_at')
        self.assertIs(created_at.default, timezone.now)
        self.assertIsInstance(created_at.db_default, TransactionNow)
        relation = model._meta.get_field('variant')
        self.assertIs(relation.remote_field.model, domain.Variant)
        self.assertIs(relation.remote_field.on_delete, CASCADE)
        self.assertFalse(relation.db_index)  # The explicitly named index replaces Django's automatic FK index.
        self.assertEqual({index.name: index.fields for index in model._meta.indexes}, {
            'idx_variant_placement_region': ['reference_assembly', 'contig', 'start_pos', 'end_pos'],
            'idx_variant_placement_variant': ['variant'],
        })
        with connection.cursor() as cursor:
            cursor.execute('SELECT column_name, data_type, character_maximum_length, is_nullable, column_default '
                           'FROM information_schema.columns WHERE table_schema = current_schema() '
                           "AND table_name = 'variant_placement'")
            self.assertEqual({row[0]: row[1:] for row in cursor.fetchall()}, columns)
            constraints = connection.introspection.get_constraints(cursor, 'variant_placement')
            cursor.execute('SELECT conname, confdeltype, confupdtype, condeferrable, condeferred FROM pg_constraint '
                           "WHERE conrelid = 'variant_placement'::regclass AND contype = 'f'")
            self.assertEqual(cursor.fetchall(), [('fk_variant_placement_variant', 'c', 'c', False, False)])
        self.assertEqual([info['columns'] for info in constraints.values() if info['primary_key']], [['placement_id']])
        self.assertEqual([(info['columns'], info['foreign_key']) for info in constraints.values() if info['foreign_key']],
                         [(['variant_id'], ('variant', 'variant_id'))])
        self.assertFalse(any(info['unique'] and not info['primary_key'] for info in constraints.values()))
        self.assertEqual({name: info['columns'] for name, info in constraints.items() if info['index']}, {
            'idx_variant_placement_region': ['reference_assembly', 'contig', 'start_pos', 'end_pos'],
            'idx_variant_placement_variant': ['variant_id'],
        })
        checks = {
            'variant_placement_start_gte_1': {'start_pos'},
            'variant_placement_end_gte_start': {'end_pos', 'start_pos'},
        }
        self.assertEqual({constraint.name for constraint in model._meta.constraints}, set(checks))
        self.assertEqual({name: set(info['columns']) for name, info in constraints.items() if info['check']}, checks)

    def test_raw_sql_minimal_insert_uses_unquoted_coordinate_boolean_and_transaction_defaults(self):
        with connection.cursor() as cursor:
            cursor.execute('INSERT INTO variant_placement '
                           '(placement_id, variant_id, reference_assembly, contig, start_pos, end_pos) '
                           'VALUES (%s, %s, %s, %s, %s, %s) RETURNING coordinate_system, is_canonical, normalized, '
                           'reference_allele, alternate_allele, strand, sv_length, breakend, metadata, '
                           'created_at, transaction_timestamp()',
                           [uuid.uuid4(), self.variant.pk, 'GRCh38', '1', 1, 1])
            coordinate, canonical, normalized, *optional, created_at, database_now = cursor.fetchone()
        self.assertEqual(coordinate, '1-based-inclusive')
        self.assertIs(canonical, False)
        self.assertIs(normalized, False)
        self.assertEqual(optional, [None] * 6)
        self.assertTrue(timezone.is_aware(created_at))
        self.assertEqual(created_at, database_now)

    def test_optional_values_signed_bigints_and_normalized_flags_have_no_biological_validation(self):
        legacy = (SNP, UserSNP, domain.Analysis, domain.DataRelease, domain.Variant)
        before = {model: model.objects.count() for model in legacy}
        for normalized in (False, True):
            values = dict(
                reference_assembly='synthetic-assembly', contig='synthetic-contig',
                start_pos=2**40, end_pos=2**40 + 2, coordinate_system='synthetic-coordinate-system',
                reference_allele='not-DNA' * 50, alternate_allele='<synthetic>', strand='?', sv_length=-2**40,
                breakend={'mate': {'contig': 'synthetic', 'position': 0}, 'orientation': ['unchecked']},
                is_canonical=True, normalized=normalized, metadata={'details': {'tags': ['synthetic'], 'count': 2}},
                created_at=timezone.now(),
            )
            placement = self.placement(**values)
            placement.full_clean()
            placement.save()
            placement.refresh_from_db()
            self.assertEqual({field: getattr(placement, field) for field in values}, values)
        self.assertEqual(domain.VariantPlacement.objects.count(), 2)  # No uniqueness rule on placement or canonical flag.
        self.assertEqual({model: model.objects.count() for model in legacy}, before)

    def test_coordinates_reject_start_zero_and_end_before_start_in_orm_and_database(self):
        valid = self.placement()
        valid.save()  # Inclusive single-base placements at position one are valid.
        for changes, constraint in (
            ({'start_pos': 0}, 'variant_placement_start_gte_1'),
            ({'start_pos': -1}, 'variant_placement_start_gte_1'),
            ({'start_pos': 2, 'end_pos': 1}, 'variant_placement_end_gte_start'),
        ):
            with self.subTest(changes=changes):
                placement = self.placement(**changes)
                with self.assertRaises(ValidationError) as error:
                    placement.full_clean()
                self.assertIn(constraint, str(error.exception))
                with self.assertRaises(IntegrityError) as error, transaction.atomic():
                    placement.save()
                self.assertEqual(error.exception.__cause__.diag.constraint_name, constraint)
                with self.assertRaises(IntegrityError) as error, transaction.atomic():
                    domain.VariantPlacement.objects.filter(pk=valid.pk).update(**changes)
                self.assertEqual(error.exception.__cause__.diag.constraint_name, constraint)
        valid.refresh_from_db()
        self.assertEqual((valid.start_pos, valid.end_pos), (1, 1))
        self.assertEqual(domain.VariantPlacement.objects.count(), 1)

    def test_database_required_columns_primary_key_and_variant_reference_are_enforced(self):
        values = dict(
            placement_id=uuid.uuid4(), variant_id=self.variant.pk, reference_assembly='GRCh38', contig='1',
            start_pos=1, end_pos=1, coordinate_system='1-based-inclusive', is_canonical=False,
            normalized=False, created_at=timezone.now(),
        )
        columns = ', '.join(connection.ops.quote_name(field) for field in values)
        placeholders = ', '.join(['%s'] * len(values))
        for field in values:
            with self.subTest(null_column=field):
                with self.assertRaises(IntegrityError) as error, transaction.atomic():
                    with connection.cursor() as cursor:
                        cursor.execute(f'INSERT INTO variant_placement ({columns}) VALUES ({placeholders})',
                                       [None if name == field else value for name, value in values.items()])
                self.assertEqual(error.exception.__cause__.diag.column_name, field)
        orphan = self.placement(variant_id=uuid.uuid4())
        with self.assertRaises(ValidationError) as error:
            orphan.full_clean()
        self.assertIn('variant', error.exception.message_dict)
        with self.assertRaises(IntegrityError), transaction.atomic():
            orphan.save()
            self.fail('Placement FK must reject orphan references immediately.')
        first = self.placement()
        first.save()
        with self.assertRaises(IntegrityError), transaction.atomic():
            domain.VariantPlacement.objects.bulk_create([self.placement(placement_id=first.pk)])
        self.assertEqual(domain.VariantPlacement.objects.count(), 1)

    def test_database_and_orm_enforce_varchar_and_fixed_char_limits(self):
        for field, length in (('reference_assembly', 32), ('contig', 64), ('coordinate_system', 32), ('strand', 1)):
            with self.subTest(field=field):
                boundary = self.placement(**{field: 'x' * length})
                boundary.full_clean()
                boundary.save()
                boundary.refresh_from_db()
                self.assertEqual(getattr(boundary, field), 'x' * length)
                too_long = self.placement(**{field: 'x' * (length + 1)})
                with self.assertRaises(ValidationError) as error:
                    too_long.full_clean()
                self.assertIn(field, error.exception.message_dict)
                with self.assertRaises(DataError), transaction.atomic():
                    too_long.save()

    def test_raw_sql_variant_update_and_delete_cascade_only_its_placements(self):
        placement = self.placement()
        placement.save()
        other = domain.Variant.objects.create(variant_type='synthetic-unrelated')
        remaining = self.placement(variant_id=other.pk)
        remaining.save()
        new_id = uuid.uuid4()
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute('UPDATE variant SET variant_id = %s WHERE variant_id = %s', [new_id, self.variant.pk])
            placement.refresh_from_db()
            self.assertEqual(placement.variant_id, new_id)
            cursor.execute('DELETE FROM variant WHERE variant_id = %s', [new_id])
            self.assertEqual(list(domain.VariantPlacement.objects.values_list('pk', flat=True)), [remaining.pk])

    def test_orm_variant_delete_cascades_only_its_placements(self):
        for contig in ('1', '2'):
            self.placement(contig=contig).save()
        other = domain.Variant.objects.create(variant_type='synthetic-unrelated')
        remaining = self.placement(variant_id=other.pk)
        remaining.save()
        self.assertEqual(self.variant.placements.count(), 2)
        self.variant.delete()  # ORM cascade remains supported alongside the physical FK actions.
        self.assertEqual(list(domain.VariantPlacement.objects.values_list('pk', flat=True)), [remaining.pk])
        self.assertTrue(domain.Variant.objects.filter(pk=other.pk).exists())

    def test_fk_migration_reverse_and_missing_or_ambiguous_lookup(self):
        operation = import_module('genetics.migrations.0005_variant_placement').Migration.operations[1]
        state = MigrationLoader(connection).project_state([('genetics', '0005_variant_placement')])
        actions_sql = ('SELECT confdeltype, confupdtype, condeferrable, condeferred FROM pg_constraint '
                       "WHERE conrelid = 'variant_placement'::regclass AND conname = 'fk_variant_placement_variant'")
        with connection.schema_editor() as editor, connection.cursor() as cursor:
            operation.database_backwards('genetics', editor, state, state)
            cursor.execute(actions_sql)
            self.assertEqual(cursor.fetchall(), [('a', 'a', True, True)])
            operation.database_forwards('genetics', editor, state, state)
            cursor.execute(actions_sql)
            self.assertEqual(cursor.fetchall(), [('c', 'c', False, False)])
            for case, sql in (
                ('missing', 'ALTER TABLE variant_placement DROP CONSTRAINT fk_variant_placement_variant'),
                ('ambiguous', 'ALTER TABLE variant_placement ADD CONSTRAINT duplicate_variant_fk '
                 'FOREIGN KEY (variant_id) REFERENCES variant (variant_id) DEFERRABLE INITIALLY DEFERRED'),
            ):
                with self.subTest(case=case), transaction.atomic():
                    cursor.execute(sql)
                    with self.assertRaisesMessage(RuntimeError, 'Expected exactly one FK'):
                        operation.database_forwards('genetics', editor, state, state)
                    transaction.set_rollback(True)  # Restore the isolated FK after each intentional lookup failure.

    def test_schema_only_migration_dependency_state_and_fixed_char_deconstruction(self):
        with self.assertNumQueries(0):
            migration = reload(import_module('genetics.migrations.0005_variant_placement')).Migration
        self.assertEqual(migration.dependencies, [('genetics', '0004_variant')])
        self.assertEqual([type(operation).__name__ for operation in migration.operations], ['CreateModel', 'RunPython'])
        self.assertEqual(migration.operations[0].name, 'VariantPlacement')
        historical = MigrationLoader(connection).project_state([('genetics', '0005_variant_placement')]).apps.get_model(
            'genetics', 'VariantPlacement',
        )
        self.assertEqual(historical._meta.db_table, domain.VariantPlacement._meta.db_table)
        self.assertEqual({field.name: field.deconstruct()[1:] for field in historical._meta.local_fields},
                         {field.name: field.deconstruct()[1:] for field in domain.VariantPlacement._meta.local_fields})
        self.assertEqual(historical._meta.indexes, domain.VariantPlacement._meta.indexes)
        self.assertEqual(historical._meta.constraints, domain.VariantPlacement._meta.constraints)
        field = domain.VariantPlacement._meta.get_field('strand')
        self.assertIsInstance(field, domain.FixedCharField)
        _, path, args, kwargs = field.deconstruct()
        self.assertEqual(path, 'genetics.models.FixedCharField')
        rebuilt = domain.FixedCharField(*args, **kwargs)
        self.assertEqual(rebuilt.deconstruct()[1:], field.deconstruct()[1:])
        self.assertEqual(rebuilt.db_type(connection), 'char(1)')
        call_command('check')
        call_command('makemigrations', check=True, dry_run=True)


class VariantTests(TestCase):
    def setUp(self):
        self.assertTrue(connection.settings_dict['NAME'].startswith('gdb_test_'))

    def test_minimal_variant_has_orm_defaults_and_nullable_fields(self):
        self.assertTrue(hasattr(domain, 'Variant'), 'The stable Variant concept is missing.')
        variant = domain.Variant(variant_type='synthetic-type')
        variant.full_clean()
        variant.save()
        variant.refresh_from_db()
        self.assertIsInstance(variant.pk, uuid.UUID)
        self.assertEqual(variant.pk.version, 4)
        self.assertEqual(variant.variant_type, 'synthetic-type')
        self.assertEqual(variant.status, 'active')
        self.assertTrue(timezone.is_aware(variant.created_at))
        for field in ('canonical_name', 'vrs_id', 'metadata'):
            self.assertIsNone(getattr(variant, field))

    def test_exact_seven_physical_columns_defaults_primary_key_unique_and_index(self):
        columns = {
            'variant_id': ('uuid', None, 'NO', None),
            'variant_type': ('character varying', 32, 'NO', None),
            'canonical_name': ('character varying', 255, 'YES', None),
            'vrs_id': ('character varying', 255, 'YES', None),
            'status': ('character varying', 32, 'NO', "'active'::character varying"),
            'metadata': ('jsonb', None, 'YES', None),
            'created_at': ('timestamp with time zone', None, 'NO', 'CURRENT_TIMESTAMP'),
        }
        model = domain.Variant
        self.assertEqual((model._meta.db_table, model._meta.pk.name), ('variant', 'variant_id'))
        self.assertEqual({field.column for field in model._meta.local_fields}, set(columns))
        self.assertIs(model._meta.pk.default, uuid.uuid4)
        self.assertFalse(model._meta.pk.editable)
        for field in model._meta.local_fields:
            _, length, nullable, _ = columns[field.column]
            self.assertEqual((field.null, field.blank), (nullable == 'YES', nullable == 'YES'))
            if length is not None:
                self.assertEqual(field.max_length, length)
        status = model._meta.get_field('status')
        self.assertEqual((status.default, status.db_default), ('active', 'active'))
        created_at = model._meta.get_field('created_at')
        self.assertIs(created_at.default, timezone.now)
        self.assertIsInstance(created_at.db_default, TransactionNow)
        self.assertTrue(model._meta.get_field('vrs_id').unique)
        for field in ('variant_type', 'status'):
            self.assertFalse(model._meta.get_field(field).choices)
        self.assertEqual({index.name: index.fields for index in model._meta.indexes}, {
            'idx_variant_type': ['variant_type'],
        })
        with connection.cursor() as cursor:
            cursor.execute('SELECT column_name, data_type, character_maximum_length, is_nullable, column_default '
                           "FROM information_schema.columns WHERE table_schema = current_schema() AND table_name = 'variant'")
            self.assertEqual({row[0]: row[1:] for row in cursor.fetchall()}, columns)
            constraints = connection.introspection.get_constraints(cursor, 'variant')
        self.assertEqual([info['columns'] for info in constraints.values() if info['primary_key']], [['variant_id']])
        self.assertTrue(any(info['unique'] and info['columns'] == ['vrs_id'] for info in constraints.values()))
        self.assertFalse(any(info['foreign_key'] for info in constraints.values()))
        index = constraints['idx_variant_type']
        self.assertTrue(index['index'])
        self.assertFalse(index['unique'])
        self.assertEqual(index['columns'], ['variant_type'])

    def test_optional_metadata_and_explicit_values_round_trip_without_legacy_side_effects(self):
        legacy = (SNP, UserSNP, domain.Analysis, domain.DataRelease)
        before = {model: model.objects.count() for model in legacy}
        values = dict(
            variant_type='synthetic-structural', canonical_name='Synthetic concept',
            vrs_id='ga4gh:VA.synthetic-round-trip', status='custom-status',
            metadata={'tags': ['synthetic'], 'details': {'count': 2}}, created_at=timezone.now(),
        )
        variant = domain.Variant(**values)
        variant.full_clean()
        variant.save()
        variant.refresh_from_db()
        self.assertEqual({field: getattr(variant, field) for field in values}, values)
        self.assertEqual({model: model.objects.count() for model in legacy}, before)

    def test_database_rejects_duplicate_vrs_and_primary_key_but_allows_multiple_null_vrs(self):
        first = domain.Variant.objects.create(variant_type='synthetic', vrs_id='ga4gh:VA.synthetic-one')
        with self.assertRaises(IntegrityError), transaction.atomic():
            domain.Variant.objects.create(variant_type='different-type', vrs_id=first.vrs_id)
        with self.assertRaises(IntegrityError), transaction.atomic():
            domain.Variant.objects.create(variant_id=first.pk, variant_type='different-type')
        domain.Variant.objects.create(variant_type='synthetic', vrs_id='ga4gh:VA.synthetic-two')
        for _ in range(2):
            variant = domain.Variant(variant_type='synthetic', canonical_name='Repeated concept', vrs_id=None)
            variant.full_clean()
            variant.save()
        self.assertEqual(domain.Variant.objects.count(), 4)
        self.assertEqual(domain.Variant.objects.filter(vrs_id__isnull=True).count(), 2)

    def test_raw_sql_minimal_insert_uses_active_and_transaction_timestamp_defaults(self):
        with connection.cursor() as cursor:
            cursor.execute('INSERT INTO variant (variant_id, variant_type) VALUES (%s, %s) '
                           'RETURNING canonical_name, vrs_id, status, metadata, created_at, transaction_timestamp()',
                           [uuid.uuid4(), 'synthetic-sql'])
            name, vrs_id, status, metadata, created_at, database_now = cursor.fetchone()
        self.assertEqual((name, vrs_id, metadata), (None, None, None))
        self.assertEqual(status, 'active')
        self.assertTrue(timezone.is_aware(created_at))
        self.assertEqual(created_at, database_now)

    def test_database_required_columns_and_varchar_limits_are_enforced(self):
        values = dict(variant_id=uuid.uuid4(), variant_type='synthetic', status='active', created_at=timezone.now())
        for field in values:
            with self.subTest(null_field=field), self.assertRaises(IntegrityError), transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute('INSERT INTO variant (variant_id, variant_type, status, created_at) '
                                   'VALUES (%s, %s, %s, %s)',
                                   [None if name == field else value for name, value in values.items()])
        for field, length in (('variant_type', 32), ('status', 32), ('canonical_name', 255), ('vrs_id', 255)):
            variant = domain.Variant(**(dict(variant_type='synthetic') | {field: 'x' * (length + 1)}))
            with self.subTest(long_field=field):
                with self.assertRaises(ValidationError) as error:
                    variant.full_clean()
                self.assertIn(field, error.exception.message_dict)
                with self.assertRaises(DataError), transaction.atomic():
                    variant.save()

    def test_schema_only_migration_dependency_and_state_match_current_model(self):
        with self.assertNumQueries(0):
            migration = reload(import_module('genetics.migrations.0004_variant')).Migration
        self.assertEqual(migration.dependencies, [('genetics', '0003_data_release_analysis_release')])
        self.assertEqual([type(operation).__name__ for operation in migration.operations], ['CreateModel'])
        self.assertEqual(migration.operations[0].name, 'Variant')
        historical = MigrationLoader(connection).project_state([('genetics', '0004_variant')]).apps.get_model('genetics', 'Variant')
        self.assertEqual(historical._meta.db_table, domain.Variant._meta.db_table)
        self.assertEqual({field.name: field.deconstruct()[1:] for field in historical._meta.local_fields},
                         {field.name: field.deconstruct()[1:] for field in domain.Variant._meta.local_fields})
        self.assertEqual(historical._meta.indexes, domain.Variant._meta.indexes)
        self.assertEqual(historical._meta.constraints, domain.Variant._meta.constraints)
        call_command('check')
        call_command('makemigrations', check=True, dry_run=True)


class DataReleaseTests(TestCase):
    def setUp(self):
        self.assertTrue(connection.settings_dict['NAME'].startswith('gdb_test_'))

    def release(self, **changes):
        return domain.DataRelease(**(dict(
            name='Synthetic release', version='1.0', status='draft', reference_assembly='GRCh38',
        ) | changes))

    def test_all_nine_sql_columns_have_exact_types_nullability_and_unique_constraint(self):
        columns = {
            'release_id': ('uuid', None, 'NO'), 'name': ('character varying', 128, 'NO'),
            'version': ('character varying', 64, 'NO'), 'status': ('character varying', 32, 'NO'),
            'reference_assembly': ('character varying', 32, 'NO'), 'description': ('text', None, 'YES'),
            'manifest_checksum': ('character', 64, 'YES'), 'frozen_at': ('timestamp with time zone', None, 'YES'),
            'created_at': ('timestamp with time zone', None, 'NO'),
        }
        model = domain.DataRelease
        self.assertEqual((model._meta.db_table, model._meta.pk.name), ('data_release', 'release_id'))
        self.assertEqual({field.column for field in model._meta.local_fields}, set(columns))
        self.assertIsInstance(model._meta.pk.get_default(), uuid.UUID)
        for field in model._meta.local_fields:
            _, length, nullable = columns[field.column]
            self.assertEqual((field.null, field.blank), (nullable == 'YES', nullable == 'YES'))
            if length is not None:
                self.assertEqual(field.max_length, length)
        self.assertFalse(model._meta.get_field('status').choices)
        with connection.cursor() as cursor:
            cursor.execute('SELECT column_name, data_type, character_maximum_length, is_nullable '
                           "FROM information_schema.columns WHERE table_schema = current_schema() AND table_name = 'data_release'")
            self.assertEqual({row[0]: row[1:] for row in cursor.fetchall()}, columns)
            constraints = connection.introspection.get_constraints(cursor, 'data_release')
        self.assertTrue(any(info['primary_key'] and info['columns'] == ['release_id']
                            for info in constraints.values()))
        unique = constraints['uq_data_release_name_version']
        self.assertTrue(unique['unique'])
        self.assertEqual(unique['columns'], ['name', 'version'])

    def test_nullable_metadata_round_trip_and_orm_and_transaction_defaults(self):
        release = self.release()
        release.full_clean()
        release.save()
        release.refresh_from_db()
        self.assertIsInstance(release.pk, uuid.UUID)
        self.assertTrue(timezone.is_aware(release.created_at))
        for field in ('description', 'manifest_checksum', 'frozen_at'):
            self.assertIsNone(getattr(release, field))
        optional = dict(description='Synthetic manifest', manifest_checksum='a' * 64, frozen_at=timezone.now())
        for field, value in optional.items():
            setattr(release, field, value)
        release.full_clean()
        release.save()
        release.refresh_from_db()
        for field, value in optional.items():
            self.assertEqual(getattr(release, field), value)
        created = domain.DataRelease._meta.get_field('created_at')
        self.assertIs(created.default, timezone.now)
        self.assertIsInstance(created.db_default, TransactionNow)
        with connection.cursor() as cursor:
            cursor.execute('SELECT column_name, column_default FROM information_schema.columns '
                           "WHERE table_schema = current_schema() AND table_name = 'data_release'")
            self.assertEqual(dict(cursor.fetchall()), {
                field.column: 'CURRENT_TIMESTAMP' if field.name == 'created_at' else None
                for field in domain.DataRelease._meta.local_fields
            })
            cursor.execute('INSERT INTO data_release (release_id, name, version, status, reference_assembly) '
                           'VALUES (%s, %s, %s, %s, %s) '
                           'RETURNING description, manifest_checksum, frozen_at, created_at, transaction_timestamp()',
                           [uuid.uuid4(), 'Synthetic SQL release', '1.0', 'draft', 'GRCh38'])
            description, checksum, frozen_at, created_at, database_now = cursor.fetchone()
        self.assertEqual((description, checksum, frozen_at), (None, None, None))
        self.assertTrue(timezone.is_aware(created_at))
        self.assertEqual(created_at, database_now)

    def test_database_not_null_and_composite_uniqueness(self):
        self.release().save()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.release().save()
        self.release(version='2.0').save()
        self.release(name='Another synthetic release').save()
        self.assertEqual(domain.DataRelease.objects.count(), 3)
        for field in ('name', 'version', 'status', 'reference_assembly', 'created_at'):
            with self.subTest(field=field), self.assertRaises(IntegrityError), transaction.atomic():
                self.release(**(dict(name=f'Null {field}', version='null-case') | {field: None})).save()

    def test_schema_only_migration_dependency_state_and_fixed_char_deconstruction(self):
        with self.assertNumQueries(0):
            migration = reload(import_module('genetics.migrations.0003_data_release_analysis_release')).Migration
        self.assertEqual(migration.dependencies, [('genetics', '0002_analysis')])
        self.assertEqual([type(op).__name__ for op in migration.operations], ['CreateModel', 'AddField', 'AddIndex'])
        state = MigrationLoader(connection).project_state([('genetics', '0003_data_release_analysis_release')])
        for name in ('DataRelease', 'Analysis'):
            historical, current = state.apps.get_model('genetics', name), getattr(domain, name)
            self.assertEqual(historical._meta.db_table, current._meta.db_table)
            self.assertEqual({f.name: f.deconstruct()[1:] for f in historical._meta.local_fields},
                             {f.name: f.deconstruct()[1:] for f in current._meta.local_fields})
            self.assertEqual(historical._meta.indexes, current._meta.indexes)
            self.assertEqual(historical._meta.constraints, current._meta.constraints)
        field = domain.DataRelease._meta.get_field('manifest_checksum')
        _, path, args, kwargs = field.deconstruct()
        self.assertEqual(path, 'genetics.models.FixedCharField')
        rebuilt = domain.FixedCharField(*args, **kwargs)
        self.assertEqual(rebuilt.deconstruct()[1:], field.deconstruct()[1:])
        self.assertEqual(rebuilt.db_type(connection), 'char(64)')


class AnalysisTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from participants.models import Participant
        cls.user = User.objects.create_user(username='analysis-owner')
        cls.other_user = User.objects.create_user(username='analysis-other')
        cls.participant = Participant.objects.create(user=cls.user, participant_code='analysis-owner')
        cls.other_participant = Participant.objects.create(user=cls.other_user, participant_code='analysis-other')
        cls.request = ServiceRequest.objects.create(
            purchase=Purchase.objects.create(owner=cls.user.app_user), participant=cls.participant,
            status=RequestStatus.objects.get(code='WAITING_SAMPLE'),
        )
        cls.other_request = ServiceRequest.objects.create(
            purchase=Purchase.objects.create(owner=cls.other_user.app_user), participant=cls.other_participant,
            status=cls.request.status,
        )
        cls.sample = Sample.objects.create(service_request=cls.request, participant=cls.participant,
                                           sample_code='analysis-input', sample_type='saliva')
        cls.other_sample = Sample.objects.create(service_request=cls.other_request, participant=cls.other_participant,
                                                 sample_code='analysis-other-input', sample_type='saliva')

    def analysis(self, **changes):
        return domain.Analysis(**(dict(
            participant=self.participant, sample=self.sample, service_request=self.request,
            module='ancestry', pipeline_name='synthetic-pipeline', pipeline_version='1.0', status='queued',
        ) | changes))

    def assert_invalid(self, analysis, field):
        for action in (analysis.clean, analysis.save):
            with self.subTest(action=action.__name__), self.assertRaises(ValidationError) as error:
                action()
            self.assertIn(field, error.exception.message_dict)
            self.assertNotIn(self.sample.sample_code, str(error.exception))
            self.assertNotIn(self.user.username, str(error.exception))

    def test_release_level_analysis_keeps_optional_provenance_empty(self):
        analysis = domain.Analysis.objects.create(
            module='ancestry', pipeline_name='synthetic-pipeline',
            pipeline_version='1.0', status='queued',
        )
        analysis.refresh_from_db()
        self.assertIsInstance(analysis.pk, uuid.UUID)
        for field in ('participant_id', 'sample_id', 'release_id', 'service_request_id', 'container_digest',
                      'reference_assembly', 'parameters', 'started_at', 'finished_at'):
            self.assertIsNone(getattr(analysis, field))
        self.assertTrue(timezone.is_aware(analysis.created_at))

    def test_release_reference_is_optional_and_protected(self):
        release = domain.DataRelease.objects.create(
            name='Synthetic release', version='1.0', status='draft', reference_assembly='GRCh38',
        )
        analysis = self.analysis(participant=None, sample=None, service_request=None, release=release)
        analysis.save()
        analysis.refresh_from_db()
        self.assertEqual(analysis.release_id, release.pk)
        with self.assertRaises(ProtectedError) as error:
            release.delete()
        self.assertIn(analysis, error.exception.protected_objects)
        with self.assertRaises(ProtectedError):
            domain.DataRelease.objects.filter(pk=release.pk).delete()
        self.assertTrue(domain.DataRelease.objects.filter(pk=release.pk).exists())
        self.assertEqual(domain.Analysis.objects.get(pk=analysis.pk).release_id, release.pk)
        analysis.release = None
        analysis.save(update_fields=['release'])
        analysis.refresh_from_db()
        self.assertIsNone(analysis.release_id)
        release.delete()  # Unreferenced releases are not subject to additional lifecycle rules.

    def test_all_fifteen_sql_columns_have_exact_types_foreign_keys_and_indexes(self):
        columns = {
            'analysis_id': ('uuid', None, 'NO'), 'participant_id': ('uuid', None, 'YES'),
            'sample_id': ('uuid', None, 'YES'), 'release_id': ('uuid', None, 'YES'),
            'service_request_id': ('uuid', None, 'YES'),
            'module': ('character varying', 64, 'NO'), 'pipeline_name': ('character varying', 128, 'NO'),
            'pipeline_version': ('character varying', 64, 'NO'), 'container_digest': ('character varying', 255, 'YES'),
            'reference_assembly': ('character varying', 32, 'YES'), 'parameters': ('jsonb', None, 'YES'),
            'status': ('character varying', 32, 'NO'), 'started_at': ('timestamp with time zone', None, 'YES'),
            'finished_at': ('timestamp with time zone', None, 'YES'), 'created_at': ('timestamp with time zone', None, 'NO'),
        }
        self.assertEqual((domain.Analysis._meta.db_table, domain.Analysis._meta.pk.name), ('analysis', 'analysis_id'))
        self.assertEqual({f.column for f in domain.Analysis._meta.local_fields}, set(columns))
        for field in domain.Analysis._meta.local_fields:
            _, length, nullable = columns[field.column]
            self.assertEqual((field.null, field.blank), (nullable == 'YES', nullable == 'YES'))
            if length:
                self.assertEqual(field.max_length, length)
        self.assertFalse(domain.Analysis._meta.get_field('status').choices)
        with connection.cursor() as cursor:
            cursor.execute('SELECT column_name, data_type, character_maximum_length, is_nullable '
                           "FROM information_schema.columns WHERE table_schema = current_schema() AND table_name = 'analysis'")
            self.assertEqual({row[0]: row[1:] for row in cursor.fetchall()}, columns)
            constraints = connection.introspection.get_constraints(cursor, 'analysis')
        self.assertTrue(any(info['primary_key'] and info['columns'] == ['analysis_id']
                            for info in constraints.values()))
        for field, table, key in (
            ('participant', 'participant', 'participant_id'), ('sample', 'sample', 'sample_id'),
            ('service_request', 'service_request', 'service_request_id'), ('release', 'data_release', 'release_id'),
        ):
            relation = domain.Analysis._meta.get_field(field)
            self.assertEqual(relation.remote_field.on_delete, PROTECT)
            self.assertTrue(any(info['foreign_key'] == (table, key) and info['columns'] == [relation.column]
                                for info in constraints.values()))
        self.assertEqual({i.name: i.fields for i in domain.Analysis._meta.indexes}, {
            'idx_analysis_sample': ['sample'], 'idx_analysis_release_module': ['release', 'module'],
        })
        self.assertEqual({name: info['columns'] for name, info in constraints.items() if info['index']}, {
            'idx_analysis_sample': ['sample_id'], 'idx_analysis_release_module': ['release_id', 'module'],
        })

    def test_created_at_has_orm_and_postgresql_defaults(self):
        field = domain.Analysis._meta.get_field('created_at')
        self.assertIs(field.default, timezone.now)
        with self.subTest(default='model'):
            self.assertIsInstance(field.db_default, TransactionNow)
        with connection.cursor() as cursor:
            cursor.execute('SELECT column_default FROM information_schema.columns '
                           "WHERE table_schema = current_schema() AND table_name = 'analysis' AND column_name = 'created_at'")
            with self.subTest(default='physical_column'):
                self.assertEqual(cursor.fetchone()[0], 'CURRENT_TIMESTAMP')
            cursor.execute('INSERT INTO analysis (analysis_id, module, pipeline_name, pipeline_version, status) '
                           'VALUES (%s, %s, %s, %s, %s) RETURNING created_at, transaction_timestamp()',
                           [uuid.uuid4(), 'ancestry', 'synthetic-sql', '1.0', 'queued'])
            created_at, database_now = cursor.fetchone()
        self.assertTrue(timezone.is_aware(created_at))
        self.assertEqual(created_at, database_now)

    def test_nullable_links_and_optional_execution_metadata_round_trip(self):
        optional = dict(container_digest='sha256:synthetic', reference_assembly='GRCh38',
                        parameters={'software': {'version': '1.0'}, 'inputs': ['synthetic']},
                        started_at=timezone.now(), finished_at=timezone.now())
        for links in ({}, {'participant': self.participant}, {'sample': self.sample}, {'service_request': self.request}):
            analysis = self.analysis(**(dict(participant=None, sample=None, service_request=None) | links | optional))
            analysis.full_clean()
            analysis.save()
            analysis.refresh_from_db()
            for field, value in optional.items():
                self.assertEqual(getattr(analysis, field), value)
            self.assertNotIn(self.user.username, str(analysis))
        self.request.refresh_from_db()
        self.assertEqual(self.request.status.code, 'WAITING_SAMPLE')
        self.assertFalse(ServiceStatusLog.objects.exists())
        self.assertFalse(UserSNP.objects.exists())

    def test_database_not_null_and_foreign_key_constraints(self):
        changes = [(field, None) for field in ('module', 'pipeline_name', 'pipeline_version', 'status', 'created_at')]
        changes += [(field, uuid.uuid4()) for field in ('participant_id', 'sample_id', 'release_id', 'service_request_id')]
        for field, value in changes:
            with self.subTest(field=field), self.assertRaises(IntegrityError), transaction.atomic():
                domain.Analysis.objects.bulk_create([self.analysis(**{field: value})])
                connection.check_constraints()

    def test_create_and_save_reject_missing_references_and_mismatched_participants(self):
        for changes, field in (
            ({'participant_id': uuid.uuid4()}, 'participant'), ({'sample_id': uuid.uuid4()}, 'sample'),
            ({'service_request_id': uuid.uuid4()}, 'service_request'),
            ({'participant': self.other_participant}, 'sample'), ({'sample': self.other_sample}, 'sample'),
            ({'service_request': self.other_request}, 'service_request'),
        ):
            with self.subTest(changes=changes):
                analysis = self.analysis(**changes)
                self.assert_invalid(analysis, field)
                values = {f.attname: getattr(analysis, f.attname) for f in analysis._meta.local_fields}
                with self.assertRaises(ValidationError):
                    domain.Analysis.objects.create(**values)
                self.assertFalse(domain.Analysis.objects.filter(pk=analysis.pk).exists())

    def test_revalidates_live_sample_request_and_owner_even_with_cached_relations(self):
        from participants.models import Participant
        saved = self.analysis()
        saved.save()
        replacement = User.objects.create_user(username='analysis-replacement')
        for model, pk, field, invalid, original in (
            (Sample, self.sample.pk, 'participant', self.other_participant, self.participant),
            (ServiceRequest, self.request.pk, 'participant', None, self.participant),
            (ServiceRequest, self.request.pk, 'participant', self.other_participant, self.participant),
            (Purchase, self.request.purchase_id, 'owner', self.other_user.app_user, self.user.app_user),
            (Participant, self.participant.pk, 'user', replacement, self.user),
        ):
            with self.subTest(model=model.__name__, field=field):
                model.objects.filter(pk=pk).update(**{field: invalid})
                for analysis in (self.analysis(), saved):
                    self.assert_invalid(analysis, 'sample')
                with self.assertRaises(ValidationError):
                    saved.save(update_fields=['status'])
                model.objects.filter(pk=pk).update(**{field: original})
        self.assertEqual(domain.Analysis.objects.count(), 1)

    def test_optional_request_also_requires_matching_live_participant_and_owner(self):
        request = ServiceRequest.objects.create(purchase=Purchase.objects.create(owner=self.user.app_user),
                                               participant=self.participant, status=self.request.status)
        analysis = self.analysis(service_request=request)
        analysis.save()  # Another request is valid if the participant and owner agree.
        for field, value in (('participant', None), ('participant', self.other_participant)):
            ServiceRequest.objects.filter(pk=request.pk).update(**{field: value})
            self.assert_invalid(analysis, 'service_request')
        ServiceRequest.objects.filter(pk=request.pk).update(participant=self.participant)
        Purchase.objects.filter(pk=request.purchase_id).update(owner=self.other_user.app_user)
        self.assert_invalid(analysis, 'service_request')

    def test_partial_save_validates_persisted_links_not_stale_or_cleared_instance_links(self):
        analysis = self.analysis()
        analysis.save()
        for field, foreign, original in (
            ('participant', self.other_participant, self.participant), ('sample', self.other_sample, self.sample),
            ('service_request', self.other_request, self.request),
        ):
            with self.subTest(field=field):
                domain.Analysis.objects.filter(pk=analysis.pk).update(**{field: foreign})
                setattr(analysis, field, None)
                analysis.status = 'must-not-save'
                with self.assertRaises(ValidationError):
                    analysis.save(update_fields=['status'])
                self.assertEqual(domain.Analysis.objects.get(pk=analysis.pk).status, 'queued')
                domain.Analysis.objects.filter(pk=analysis.pk).update(**{field: original})
                analysis.refresh_from_db()
        domain.Analysis.objects.filter(pk=analysis.pk).update(participant=None)
        analysis.refresh_from_db()
        analysis.sample = None
        analysis.participant = self.other_participant
        with self.assertRaises(ValidationError):
            analysis.save(update_fields=['participant'])  # The persisted sample still belongs to the original owner.

    def test_missing_joined_identities_cannot_match_each_other_as_null(self):
        for field, target in (('sample', self.sample), ('service_request', self.request)):
            with self.subTest(field=field), transaction.atomic():
                try:
                    missing = uuid.uuid4()
                    Sample.objects.filter(pk=self.sample.pk).update(participant_id=missing)
                    ServiceRequest.objects.filter(pk=self.request.pk).update(participant_id=missing)
                    Purchase.objects.filter(pk=self.request.purchase_id).update(owner_id=uuid.uuid4())
                    analysis = self.analysis(participant=None, sample=None, service_request=None)
                    setattr(analysis, field, target)
                    self.assert_invalid(analysis, field)
                finally:
                    transaction.set_rollback(True)  # Never retain deliberately broken deferred FKs.

    def test_protects_every_link_and_rejects_bulk_inserted_mismatched_provenance_on_save(self):
        analysis = self.analysis()
        analysis.save()
        for target in (self.participant, self.sample, self.request):
            with self.assertRaises(ProtectedError) as error:
                target.delete()
            self.assertIn(analysis, error.exception.protected_objects)
        dirty = self.analysis(participant=self.other_participant)
        domain.Analysis.objects.bulk_create([dirty])
        self.assert_invalid(dirty, 'sample')

    def test_migration_is_schema_only_matches_model_and_checks_only_isolated_database(self):
        with self.assertNumQueries(0):
            migration = reload(import_module('genetics.migrations.0002_analysis')).Migration
        self.assertEqual(set(migration.dependencies), {('genetics', '0001_initial'),
                         ('participants', '0003_participant_metadata_support'), ('services', '0004_sample')})
        self.assertEqual([type(op).__name__ for op in migration.operations], ['CreateModel'])
        historical = MigrationLoader(connection).project_state([('genetics', '0003_data_release_analysis_release')]).apps.get_model('genetics', 'Analysis')
        self.assertEqual({f.name: f.deconstruct()[1:] for f in historical._meta.local_fields},
                         {f.name: f.deconstruct()[1:] for f in domain.Analysis._meta.local_fields})
        self.assertEqual(historical._meta.indexes, domain.Analysis._meta.indexes)
        self.assertTrue(connection.settings_dict['NAME'].startswith('gdb_test_'))
        call_command('check')
        call_command('makemigrations', check=True, dry_run=True)


class GeneticsTests(APITestCase):
    def test_variantes_requires_auth(self):
        """Sin autenticación, el endpoint de variantes debe rechazar."""
        r = self.client.get('/api/genetics/variantes/')
        self.assertIn(r.status_code, (401, 403))

    def test_variantes_allows_analyst(self):
        """Un analista puede consultar variantes."""
        user = User.objects.create_user(username='ana', password='x', email='ana@test.com')
        grant_analyst_role(user)
        self.client.force_authenticate(user=user)
        r = self.client.get('/api/genetics/variantes/')
        self.assertEqual(r.status_code, 200)

    def test_diseases_requires_auth(self):
        r = self.client.get('/api/genetics/diseases/')
        self.assertIn(r.status_code, (401, 403))


class LegacyGeneticUploadDeprecationTests(APITestCase):
    url = '/api/ingest/upload-genetic-file/'
    compatibility_error = (
        'Legacy user-scoped SNP upload is disabled until validated per-service '
        'import and review are available.'
    )

    def setUp(self):
        self.actor = User.objects.create_user(username='upload-actor', email='actor@example.test')
        grant_admin_role(self.actor)
        self.snp = SNP.objects.create(rsid='rs-upload-test', genotipo='C/T', fenotipo='test')
        self.client.cookies['csrftoken'] = 'upload-csrf'
        self.authenticate(self.actor)

    def authenticate(self, user):
        self.client.cookies[getattr(settings, 'AUTH_COOKIE_NAME', 'access_token')] = encode_jwt({
            'sub': str(user.pk), 'email': user.email,
        })

    def upload(self, body, *, csrf=True):
        self.client.cookies['csrftoken'] = 'upload-csrf'
        headers = {'HTTP_X_CSRFTOKEN': 'upload-csrf'} if csrf else {}
        return self.client.post(self.url, data=body, content_type='application/json', **headers)

    def make_target(self, suffix, legacy_status=ServiceStatus.PENDING):
        target = User.objects.create_user(username=f'upload-target-{suffix}')
        profile = Profile.objects.create(
            user=target, sample_code=f'SAMPLE-{suffix}',
            service_status=legacy_status, report_filename='previous.txt',
        )
        return target, profile

    def make_paid_request(self, target):
        paid = PurchaseStatus.objects.get(code='PAID')
        waiting = RequestStatus.objects.get(code='WAITING_SAMPLE')
        purchase = Purchase.objects.create(owner=target.app_user, status=paid)
        request = ServiceRequest.objects.create(purchase=purchase, status=waiting)
        ServiceStatusLog.objects.create(
            request=request, status=waiting, actor=self.actor.app_user,
        )

    def state(self, target):
        return {
            'snps': list(UserSNP.objects.filter(user=target).values_list('pk', 'snp_id')),
            'profiles': list(Profile.objects.filter(user=target).values_list(
                'pk', 'service_status', 'service_updated_at', 'report_filename', 'report_uploaded_at',
            )),
            'purchases': list(Purchase.objects.filter(owner=target.app_user).values_list(
                'pk', 'status_id', 'purchased_at',
            )),
            'requests': list(ServiceRequest.objects.filter(purchase__owner=target.app_user).values_list(
                'pk', 'status_id', 'completed_at',
            )),
            'history': list(ServiceStatusLog.objects.filter(
                request__purchase__owner=target.app_user,
            ).values_list('pk', 'status_id', 'actor_id', 'changed_at')),
        }

    def test_valid_staff_upload_never_publishes_or_writes_legacy_snps(self):
        for suffix, paid_count, legacy_status in (
            ('one-paid', 1, ServiceStatus.PENDING),
            ('two-paid', 2, ServiceStatus.PENDING),
            ('no-paid', 0, ServiceStatus.PENDING),
            ('legacy-complete', 0, ServiceStatus.COMPLETED),
        ):
            with self.subTest(suffix=suffix):
                target, profile = self.make_target(suffix, legacy_status)
                for _ in range(paid_count):
                    self.make_paid_request(target)
                if legacy_status == ServiceStatus.COMPLETED:
                    UserSNP.objects.create(user=target, snp=self.snp)
                before = self.state(target)
                payload = json.dumps({
                    'userId': target.pk, 'filename': f'{profile.sample_code}.txt',
                    'fileContent': '1,rs-upload-test,T/C',
                })

                with patch('genetics.upload_views.send_results_ready_email', create=True) as email:
                    response = self.upload(payload)
                    self.assertEqual(response.status_code, 409)
                    self.assertEqual(response.data, {'error': self.compatibility_error})
                    email.assert_not_called()
                self.assertEqual(self.state(target), before)

    def test_rejects_before_body_parsing_or_processing_even_without_target(self):
        with patch('genetics.upload_views.json') as parser, \
             patch.object(UploadGeneticFileAPIView, '_process_genetic_file') as process, \
             patch('genetics.upload_views.send_results_ready_email', create=True) as email:
            parser.loads.side_effect = AssertionError('parsed')
            response = self.upload('{malformed json')
            self.assertEqual(response.status_code, 409)
            self.assertEqual(response.data, {'error': self.compatibility_error})
            parser.loads.assert_not_called()
            process.assert_not_called()
            email.assert_not_called()

    def test_unauthenticated_and_unauthorized_roles_keep_existing_denials(self):
        cookie_name = getattr(settings, 'AUTH_COOKIE_NAME', 'access_token')
        del self.client.cookies[cookie_name]
        response = self.upload('{}')
        self.assertEqual(response.status_code, 403)
        self.assertNotEqual(response.data.get('error'), self.compatibility_error)

        for suffix, grant in (('client', None), ('reception', grant_reception_role)):
            with self.subTest(role=suffix):
                user = User.objects.create_user(
                    username=f'upload-{suffix}', email=f'{suffix}@example.test', is_staff=True,
                )
                if grant:
                    grant(user)
                self.authenticate(user)
                response = self.upload('{}')
                self.assertEqual(response.status_code, 403)
                self.assertEqual(response.data, {
                    'error': 'No tienes permisos para realizar esta acción',
                })

    def test_analyst_sees_compatibility_error_but_csrf_still_precedes_role(self):
        grant_analyst_role(self.actor)
        response = self.upload('{}')
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data, {'error': self.compatibility_error})
        response = self.upload('{}', csrf=False)
        self.assertEqual(response.status_code, 403)
        self.assertNotEqual(response.data.get('error'), self.compatibility_error)


class LegacyGeneticDeleteAndReportStatusTests(APITestCase):
    delete_url = '/api/ingest/delete-genetic-file/'

    def setUp(self):
        self.actor = User.objects.create_user(username='delete-actor')
        grant_admin_role(self.actor)
        self.target = User.objects.create_user(username='delete-target')
        self.other = User.objects.create_user(username='delete-other')
        self.now = timezone.now()
        self.profile = Profile.objects.create(
            user=self.target, service_status=ServiceStatus.COMPLETED,
            sample_code='DELETE-SAMPLE', report_filename='legacy.txt', report_uploaded_at=self.now,
        )
        self.snps = [SNP.objects.create(rsid=f'rs-delete-{i}', genotipo='C/T', fenotipo='test')
                     for i in range(2)]
        UserSNP.objects.bulk_create([UserSNP(user=self.target, snp=snp) for snp in self.snps])
        UserSNP.objects.create(user=self.other, snp=self.snps[0])
        self.authenticate(self.actor)

    def authenticate(self, user):
        self.client.cookies[settings.AUTH_COOKIE_NAME] = encode_jwt({'sub': str(user.pk)})

    def delete_report(self, user_id=None):
        self.client.cookies['csrftoken'] = 'delete-csrf'
        return self.client.post(
            self.delete_url, data=json.dumps({'userId': self.target.pk if user_id is None else user_id}),
            content_type='application/json', HTTP_X_CSRFTOKEN='delete-csrf',
        )

    def report(self, user=None):
        return self.client.get(f'/api/ingest/user-report-status/{(user or self.target).pk}/')

    def paid_service(self, code='WAITING_SAMPLE', *, days=0, history=True):
        purchase = Purchase.objects.create(
            owner=self.target.app_user, status=PurchaseStatus.objects.get(code='PAID'),
            purchased_at=self.now + timedelta(days=days),
        )
        waiting = RequestStatus.objects.get(code='WAITING_SAMPLE')
        state = RequestStatus.objects.get(code=code)
        service = ServiceRequest.objects.create(
            purchase=purchase, status=state, started_at=self.now,
            completed_at=self.now + timedelta(seconds=1) if code == 'COMPLETED' else None,
        )
        if history:
            ServiceStatusLog.objects.create(
                request=service, status=waiting, actor=self.actor.app_user, changed_at=self.now,
            )
            if state != waiting:
                ServiceStatusLog.objects.create(
                    request=service, status=state, actor=self.actor.app_user,
                    changed_at=self.now + timedelta(seconds=2),
                )
        return purchase, service

    def state(self):
        return [list(model.objects.order_by('pk').values()) for model in
                (AppUser, UserSNP, Profile, Purchase, ServiceRequest, ServiceStatusLog)]

    def test_paid_delete_conflicts_before_touching_profile_or_snps_for_two_services(self):
        self.paid_service('COMPLETED', days=-1)
        newest, service = self.paid_service()
        for malformed in ('none', 'request', 'purchase'):
            with self.subTest(malformed_paid=malformed):
                if malformed == 'request':
                    ServiceRequest.objects.filter(pk=service.pk).update(
                        status=RequestStatus.objects.get(code='COMPLETED'),
                    )  # No completion timestamp or matching current history.
                elif malformed == 'purchase':
                    Purchase.objects.filter(pk=newest.pk).update(purchased_at=None)
                before = self.state()
                with CaptureQueriesContext(connection) as queries, patch.object(Profile, 'save') as save:
                    response = self.delete_report()
                self.assertEqual(response.status_code, 409)
                self.assertEqual(set(response.data), {'error'})
                save.assert_not_called()
                self.assertFalse(any('"profiles_profile"' in q['sql'] or 'DELETE FROM' in q['sql']
                                     for q in queries.captured_queries))
                self.assertEqual(self.state(), before)

    def assert_report(self, service_status, *, user=None, has_report=False, count=2,
                      filename=None, date=None):
        response = self.report(user)
        self.assertEqual(response.status_code, 200)
        self.assertIs(type(response.data['snp_count']), int)
        self.assertIs(type(response.data['has_report']), bool)
        self.assertEqual(response.data, {
            'user_id': (user or self.target).pk, 'has_report': has_report, 'snp_count': count,
            'service_status': service_status, 'report_filename': filename, 'report_date': date,
        })

    def test_unpaid_delete_preserves_role_response_and_target_scope_and_clears_metadata(self):
        Purchase.objects.create(owner=self.other.app_user, status=PurchaseStatus.objects.get(code='PAID'))
        for grant, user_id, count in ((grant_admin_role, self.target.pk, 2),
                                      (grant_analyst_role, str(self.target.pk), 0)):
            grant(self.actor)
            with CaptureQueriesContext(connection) as queries:
                response = self.delete_report(user_id)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data, {
                'success': True, 'message': f'Reporte genético eliminado. {count} variantes removidas.',
                'user_id': user_id, 'deleted_count': count,
            })
            sql = [q['sql'] for q in queries.captured_queries]
            owner_lock = next(i for i, q in enumerate(sql) if 'FOR UPDATE' in q and '"app_user"' in q)
            paid_check = next(i for i, q in enumerate(sql) if 'FROM "purchase"' in q)
            self.assertLess(owner_lock, paid_check)
            self.profile.refresh_from_db()
            self.assertEqual((self.profile.service_status, self.profile.report_filename,
                              self.profile.report_uploaded_at), (ServiceStatus.NO_PURCHASED, None, None))
            self.assertEqual(self.profile.sample_code, 'DELETE-SAMPLE')
            self.assertFalse(UserSNP.objects.filter(user=self.target).exists())
            self.assertEqual(UserSNP.objects.filter(user=self.other).count(), 1)
            self.assertEqual(Purchase.objects.filter(owner=self.other.app_user).count(), 1)

    def test_analyst_delete_tolerates_missing_profile_and_owner(self):
        grant_analyst_role(self.actor)
        legacy = User.objects.bulk_create([User(username='delete-unmapped-target')])[0]
        UserSNP.objects.create(user=legacy, snp=self.snps[0])
        response = self.delete_report(str(legacy.pk))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['deleted_count'], 1)
        self.assertFalse(UserSNP.objects.filter(user=legacy).exists())
        self.assertFalse(Profile.objects.filter(user=legacy).exists())
        self.assertFalse(AppUser.objects.filter(django_user=legacy).exists())

    def test_profile_save_failure_rolls_back_deleted_snps_and_updated_profile(self):
        before = self.state()
        save = Profile.save
        depth = len(connection.savepoint_ids)

        def fail_after_save(instance, *args, **kwargs):
            self.assertTrue(connection.in_atomic_block)
            self.assertGreater(len(connection.savepoint_ids), depth)
            save(instance, *args, **kwargs)
            raise RuntimeError('injected Profile save failure')

        with patch.object(Profile, 'save', autospec=True, side_effect=fail_after_save):
            response = self.delete_report()
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.data, {'error': 'Error interno del servidor'})
        self.assertEqual(self.state(), before)

    def test_malformed_delete_bodies_and_ids_return_400_before_target_orm(self):
        self.client.force_authenticate(user=self.actor)  # Exclude the authentication User lookup.
        bodies = ['{bad json', b'\xff', '', '[]', 'null', '"user"', 'true', '{}',
                  '{"userId": ' + '9' * 5000 + '}'] + [
            json.dumps({'userId': value}) for value in (
                None, True, False, 0, -1, 1.0, [], [1], {}, {'id': 1}, '', '0', '01',
                '+1', '-1', ' 1', '1 ', '1.0', '1e2', '١', 2**63, str(2**63), '9' * 5000,
            )
        ]
        with patch.object(User.objects, 'get', side_effect=lambda **kwargs: self.fail('target ORM queried')) as get_user, \
             patch.object(AppUser.objects, 'select_for_update') as lock_owner:
            for body in bodies:
                with self.subTest(body=body[:80]):
                    self.client.cookies['csrftoken'] = 'delete-csrf'
                    response = self.client.post(
                        self.delete_url, data=body, content_type='application/json',
                        HTTP_X_CSRFTOKEN='delete-csrf',
                    )
                    self.assertEqual(response.status_code, 400)
                    self.assertIn(response.data, ({'error': 'userId inválido'},
                                                  {'error': 'userId es obligatorio'}))
            get_user.assert_not_called()
            lock_owner.assert_not_called()

    def test_unknown_target_and_malformed_get_path_keep_404(self):
        response = self.delete_report(2**63 - 1)
        self.assertEqual((response.status_code, response.data), (404, {'error': 'Usuario no encontrado'}))
        response = self.client.get('/api/ingest/user-report-status/999999999/')
        self.assertEqual((response.status_code, response.data), (404, {'error': 'Usuario no encontrado'}))
        for segment in ('-1', '1.0', 'not-an-id'):
            self.assertEqual(self.client.get(f'/api/ingest/user-report-status/{segment}/').status_code, 404)

    def test_only_explicit_admin_or_analyst_may_delete_or_read_even_with_django_flags(self):
        flagged = User.objects.create_user(username='delete-flagged', is_staff=True, is_superuser=True)
        flagged.groups.add(Group.objects.get_or_create(name='ADMIN')[0])
        reception = User.objects.create_user(username='delete-reception')
        grant_reception_role(reception)
        unmapped = User.objects.bulk_create([User(username='delete-unmapped-actor')])[0]
        before = self.state()
        for actor in (self.other, flagged, reception, unmapped, None):
            with self.subTest(actor=actor):
                self.client.cookies.pop(settings.AUTH_COOKIE_NAME, None)
                if actor:
                    self.authenticate(actor)
                self.assertEqual(self.delete_report().status_code, 403)
                self.assertEqual(self.report().status_code, 403)
                self.assertEqual(self.state(), before)

    def test_delete_requires_matching_csrf_cookie_and_header(self):
        before = self.state()
        for cookie, header in ((None, 'csrf'), ('csrf', None), ('one', 'two')):
            self.client.cookies.pop('csrftoken', None)
            if cookie:
                self.client.cookies['csrftoken'] = cookie
            headers = {'HTTP_X_CSRFTOKEN': header} if header else {}
            response = self.client.post(
                self.delete_url, data=json.dumps({'userId': self.target.pk}),
                content_type='application/json', **headers,
            )
            self.assertEqual(response.status_code, 403)
            self.assertEqual(self.state(), before)

    def test_paid_status_projects_newest_paid_but_never_claims_a_legacy_report(self):
        self.paid_service('COMPLETED', days=-2)
        self.assert_report(ServiceStatus.COMPLETED)
        self.paid_service(days=-1)
        Purchase.objects.create(
            owner=self.target.app_user, status=PurchaseStatus.objects.get(code='PENDING'),
            created_at=self.now + timedelta(days=1),
        )
        before = self.state()
        self.assert_report(ServiceStatus.PENDING)
        self.assertEqual(self.state(), before)

    def test_malformed_newest_paid_status_never_falls_back_to_profile_or_older_completion(self):
        self.paid_service('COMPLETED')
        newest = Purchase.objects.create(
            owner=self.target.app_user, status=PurchaseStatus.objects.get(code='PAID'),
            purchased_at=self.now + timedelta(days=1),
        )
        self.assert_report(ServiceStatus.NO_PURCHASED)  # Missing request.
        waiting = RequestStatus.objects.get(code='WAITING_SAMPLE')
        service = ServiceRequest.objects.create(purchase=newest, status=waiting)
        self.assert_report(ServiceStatus.NO_PURCHASED)  # Missing history.
        ServiceStatusLog.objects.create(request=service, status=waiting, actor=self.actor.app_user)
        newest.purchased_at = None
        newest.save(update_fields=['purchased_at'])
        self.assert_report(ServiceStatus.NO_PURCHASED)  # Missing payment timestamp.

    def test_no_paid_get_keeps_legacy_counts_status_and_metadata_with_or_without_profile(self):
        Purchase.objects.create(owner=self.target.app_user, status=PurchaseStatus.objects.get(code='PENDING'))
        Profile.objects.create(user=self.actor, service_status=ServiceStatus.PENDING,
                               report_filename='historical.txt', report_uploaded_at=self.now)
        for grant in (grant_admin_role, grant_analyst_role):
            grant(self.actor)
            self.assert_report(ServiceStatus.COMPLETED, has_report=True, filename='legacy.txt',
                               date=self.now.strftime('%Y-%m-%d'))
            self.assert_report(ServiceStatus.NO_PURCHASED, user=self.other, has_report=True, count=1)
            self.assert_report(ServiceStatus.PENDING, user=self.actor, count=0, filename='historical.txt',
                               date=self.now.strftime('%Y-%m-%d'))
