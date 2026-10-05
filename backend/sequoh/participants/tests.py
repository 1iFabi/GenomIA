import uuid
from decimal import Decimal
from importlib import import_module, reload

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.migrations.loader import MigrationLoader
from django.db.models.deletion import PROTECT, ProtectedError
from django.test import TestCase
from django.utils import timezone

from participants import models as domain
from participants.models import Participant
from services.models import Purchase, Sample, ServiceRequest, ServiceStatus, ServiceStatusLog


class ParticipantTests(TestCase):
    def test_create_for_existing_user_without_requiring_staff_participant(self):
        User = get_user_model()
        user = User.objects.create_user(username='client-1')
        staff = User.objects.create_user(username='staff-1', is_staff=True)

        participant = Participant.objects.create(user=user, participant_code='p-001')

        self.assertIsInstance(participant.participant_id, uuid.UUID)
        self.assertEqual(participant.pk, participant.participant_id)
        self.assertEqual(participant.user, user)
        self.assertIsInstance(participant.user_id, int)
        self.assertEqual(user.participant, participant)
        self.assertTrue(timezone.is_aware(participant.enrolled_at))
        self.assertFalse(Participant.objects.filter(user=staff).exists())

    def test_table_and_primary_key_match_domain_schema(self):
        self.assertEqual(Participant._meta.db_table, 'participant')
        self.assertEqual(Participant._meta.pk.name, 'participant_id')
        with connection.cursor() as cursor:
            self.assertIn('participant', connection.introspection.table_names(cursor))
            constraints = connection.introspection.get_constraints(cursor, 'participant')
        self.assertTrue(any(
            details['primary_key'] and details['columns'] == ['participant_id']
            for details in constraints.values()
        ))

    def test_participant_code_is_unique(self):
        User = get_user_model()
        first = User.objects.create_user(username='client-1')
        second = User.objects.create_user(username='client-2')
        Participant.objects.create(user=first, participant_code='p-001')

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Participant.objects.create(user=second, participant_code='p-001')

    def test_user_can_have_only_one_participant(self):
        user = get_user_model().objects.create_user(username='client-1')
        Participant.objects.create(user=user, participant_code='p-001')

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Participant.objects.create(user=user, participant_code='p-002')

    def test_participant_requires_an_existing_user(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Participant.objects.create(participant_code='p-001')

    def test_user_deletion_is_protected(self):
        user = get_user_model().objects.create_user(username='client-1')
        participant = Participant.objects.create(user=user, participant_code='p-001')

        with self.assertRaises(ProtectedError):
            user.delete()

        self.assertTrue(get_user_model().objects.filter(pk=user.pk).exists())
        self.assertTrue(Participant.objects.filter(pk=participant.pk).exists())

    def test_enrollment_and_consent_status_defaults(self):
        user = get_user_model().objects.create_user(username='client-1')
        participant = Participant.objects.create(user=user, participant_code='p-001')

        participant.refresh_from_db()
        self.assertEqual(participant.enrollment_status, 'pending')
        self.assertEqual(participant.consent_status, 'pending')
        self.assertIsNone(participant.consent_version)
        self.assertIsNone(participant.consented_at)

    def test_invalid_enrollment_status_is_rejected_on_save(self):
        user = get_user_model().objects.create_user(username='client-1')

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Participant.objects.create(
                    user=user, participant_code='p-001', enrollment_status='unknown',
                )

    def test_invalid_consent_status_is_rejected_on_save(self):
        user = get_user_model().objects.create_user(username='client-1')

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Participant.objects.create(
                    user=user, participant_code='p-001', consent_status='unknown',
                )

    def test_granted_consent_requires_version_and_timestamp(self):
        consented_at = timezone.now()
        incomplete_grants = [
            (None, consented_at),
            ('', consented_at),
            ('v1', None),
        ]
        for index, (version, recorded_at) in enumerate(incomplete_grants):
            with self.subTest(version=version, recorded_at=recorded_at):
                user = get_user_model().objects.create_user(username=f'client-{index}')
                with self.assertRaises(IntegrityError):
                    with transaction.atomic():
                        Participant.objects.create(
                            user=user, participant_code=f'p-{index}',
                            consent_status='granted', consent_version=version,
                            consented_at=recorded_at,
                        )

    def test_constraints_apply_to_updates_without_model_validation(self):
        user = get_user_model().objects.create_user(username='client-1')
        participant = Participant.objects.create(user=user, participant_code='p-001')

        for updates in (
            {'enrollment_status': 'unknown'},
            {'consent_status': 'unknown'},
            {'consent_status': 'granted'},
        ):
            with self.subTest(updates=updates):
                with self.assertRaises(IntegrityError):
                    with transaction.atomic():
                        Participant.objects.filter(pk=participant.pk).update(**updates)

    def test_consent_can_be_granted_and_withdrawn(self):
        user = get_user_model().objects.create_user(username='client-1')
        participant = Participant.objects.create(user=user, participant_code='p-001')
        consented_at = timezone.now()

        participant.enrollment_status = 'active'
        participant.consent_status = 'granted'
        participant.consent_version = 'v1'
        participant.consented_at = consented_at
        participant.full_clean()
        participant.save()
        participant = Participant.objects.get(pk=participant.pk)
        self.assertEqual(participant.enrollment_status, 'active')
        self.assertEqual(participant.consent_status, 'granted')
        self.assertEqual(participant.consent_version, 'v1')
        self.assertEqual(participant.consented_at, consented_at)

        participant.enrollment_status = 'inactive'
        participant.consent_status = 'withdrawn'
        participant.full_clean()
        participant.save()
        participant = Participant.objects.get(pk=participant.pk)
        self.assertEqual(participant.enrollment_status, 'inactive')
        self.assertEqual(participant.consent_status, 'withdrawn')
        self.assertEqual(participant.consent_version, 'v1')
        self.assertEqual(participant.consented_at, consented_at)

    def test_metadata_default_is_isolated_per_participant(self):
        User = get_user_model()
        first = Participant.objects.create(
            user=User.objects.create_user(username='client-1'), participant_code='p-001',
        )
        second = Participant.objects.create(
            user=User.objects.create_user(username='client-2'), participant_code='p-002',
        )
        self.assertEqual(first.metadata, {})
        self.assertEqual(second.metadata, {})

        first.metadata['synthetic_cohort'] = 'test'
        first.save(update_fields=['metadata'])
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.metadata, {'synthetic_cohort': 'test'})
        self.assertEqual(second.metadata, {})

    def test_participant_has_no_direct_identifier_fields(self):
        field_names = {field.name for field in Participant._meta.local_fields}

        self.assertEqual(field_names, {
            'participant_id', 'user', 'participant_code', 'enrolled_at',
            'enrollment_status', 'consent_status', 'consent_version',
            'consented_at', 'metadata',
        })


class ObservationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username='observation-owner')
        cls.other_user = get_user_model().objects.create_user(username='observation-other')
        cls.participant = Participant.objects.create(user=cls.user, participant_code='observation-owner')
        cls.other_participant = Participant.objects.create(user=cls.other_user, participant_code='observation-other')
        cls.purchase = Purchase.objects.create(owner=cls.user.app_user)
        cls.request = ServiceRequest.objects.create(
            purchase=cls.purchase, participant=cls.participant,
            status=ServiceStatus.objects.get(code='WAITING_SAMPLE'),
        )
        cls.sample = Sample.objects.create(
            service_request=cls.request, participant=cls.participant,
            sample_code='observation-sample', sample_type='saliva',
        )

    def observation(self, **changes):
        observation = domain.Observation(
            participant=self.participant, sample=self.sample, observation_type='laboratory', label='Synthetic result',
        )
        for field, value in changes.items():
            setattr(observation, field, value)
        return observation

    def assert_invalid(self, observation, field):
        for action in (observation.clean, observation.save):
            with self.subTest(action=action.__name__), self.assertRaises(ValidationError) as error:
                action()
            self.assertIn(field, error.exception.message_dict)

    def test_sample_null_observation_is_saved_without_enrollment_or_consent_changes(self):
        user = get_user_model().objects.create_user(username='observation-client')
        participant = Participant.objects.create(user=user, participant_code='observation-client')
        observation = domain.Observation.objects.create(
            participant=participant, observation_type='phenotype', label='Synthetic phenotype',
        )

        observation.refresh_from_db()
        participant.refresh_from_db()
        self.assertIsInstance(observation.pk, uuid.UUID)
        self.assertEqual(observation.participant, participant)
        self.assertIsNone(observation.sample_id)
        self.assertTrue(timezone.is_aware(observation.created_at))
        self.assertEqual((participant.enrollment_status, participant.consent_status), ('pending', 'pending'))
        self.assertIsNone(participant.consented_at)
        self.assertIsNone(participant.consent_version)
        self.assertIsNone(observation.metadata)

    def test_exact_sql_schema_foreign_keys_and_two_composite_indexes(self):
        columns = {
            'observation_id': ('uuid', None, 'NO'), 'participant_id': ('uuid', None, 'NO'),
            'sample_id': ('uuid', None, 'YES'), 'observation_type': ('character varying', 48, 'NO'),
            'code_system': ('character varying', 64, 'YES'), 'code': ('character varying', 128, 'YES'),
            'label': ('character varying', 255, 'NO'), 'value_numeric': ('numeric', None, 'YES'),
            'value_text': ('text', None, 'YES'), 'value_code': ('character varying', 128, 'YES'),
            'value_boolean': ('boolean', None, 'YES'), 'unit': ('character varying', 64, 'YES'),
            'reference_low': ('numeric', None, 'YES'), 'reference_high': ('numeric', None, 'YES'),
            'source_name': ('character varying', 128, 'YES'), 'source_version': ('character varying', 64, 'YES'),
            'observed_at': ('timestamp with time zone', None, 'YES'), 'metadata': ('jsonb', None, 'YES'),
            'created_at': ('timestamp with time zone', None, 'NO'),
        }
        self.assertEqual((domain.Observation._meta.db_table, domain.Observation._meta.pk.name),
                         ('observation', 'observation_id'))
        self.assertEqual({f.column for f in domain.Observation._meta.local_fields}, set(columns))
        for field in domain.Observation._meta.local_fields:
            _, length, nullable = columns[field.column]
            self.assertEqual((field.null, field.blank), (nullable == 'YES', nullable == 'YES'))
            if length:
                self.assertEqual(field.max_length, length)
        with connection.cursor() as cursor:
            cursor.execute('SELECT column_name, data_type, character_maximum_length, is_nullable '
                           "FROM information_schema.columns WHERE table_schema = current_schema() AND table_name = 'observation'")
            self.assertEqual({row[0]: row[1:] for row in cursor.fetchall()}, columns)
            cursor.execute('SELECT column_name, numeric_precision, numeric_scale FROM information_schema.columns '
                           "WHERE table_schema = current_schema() AND table_name = 'observation' AND data_type = 'numeric'")
            self.assertEqual({row[0]: row[1:] for row in cursor.fetchall()},
                             {name: (18, 6) for name in ('value_numeric', 'reference_low', 'reference_high')})
            constraints = connection.introspection.get_constraints(cursor, 'observation')
        self.assertTrue(any(info['primary_key'] and info['columns'] == ['observation_id']
                            for info in constraints.values()))
        for field, table in (('participant', 'participant'), ('sample', 'sample')):
            relation = domain.Observation._meta.get_field(field)
            self.assertEqual(relation.remote_field.on_delete, PROTECT)
            self.assertTrue(any(info['foreign_key'] == (table, f'{table}_id')
                                and info['columns'] == [relation.column] for info in constraints.values()))
        indexes = {'observation_part_time_idx': ['participant_id', 'observed_at'],
                   'observation_code_idx': ['code_system', 'code']}
        self.assertEqual({index.name for index in domain.Observation._meta.indexes}, set(indexes))
        for name, fields in indexes.items():
            self.assertTrue(constraints[name]['index'])
            self.assertEqual(constraints[name]['columns'], fields)

    def test_database_created_at_default_supports_required_columns_only_insert(self):
        with connection.cursor() as cursor:
            cursor.execute('INSERT INTO observation (observation_id, participant_id, observation_type, label) '
                           'VALUES (%s, %s, %s, %s) RETURNING created_at, statement_timestamp()',
                           [uuid.uuid4(), self.participant.pk, 'phenotype', 'Synthetic SQL result'])
            created_at, database_now = cursor.fetchone()
        self.assertTrue(timezone.is_aware(created_at))
        self.assertEqual(created_at, database_now)

    def test_sample_observation_round_trips_all_optional_values_without_advancing_service(self):
        values = dict(code_system='LOINC', code='synthetic', value_numeric=Decimal('123456789012.123456'),
                      value_text='Synthetic narrative', value_code='synthetic-code', value_boolean=False,
                      unit='mg/dL', reference_low=Decimal('-0.000001'), reference_high=Decimal('200.123456'),
                      source_name='Synthetic laboratory', source_version='v1', observed_at=timezone.now(),
                      metadata={'synthetic': ['batch-1']})
        observation = self.observation(**values)
        observation.full_clean()
        observation.save()
        observation.refresh_from_db()
        self.assertEqual(observation.sample_id, self.sample.pk)
        for field, value in values.items():
            self.assertEqual(getattr(observation, field), value)
        self.request.refresh_from_db()
        self.assertEqual(self.request.status.code, 'WAITING_SAMPLE')
        self.assertFalse(ServiceStatusLog.objects.exists())

    def test_database_not_null_and_foreign_key_constraints(self):
        for field, value in (('participant_id', None), ('observation_type', None), ('label', None),
                             ('created_at', None), ('participant_id', uuid.uuid4()), ('sample_id', uuid.uuid4())):
            observation = self.observation(**{field: value})
            with self.subTest(field=field, value=value), self.assertRaises(IntegrityError), transaction.atomic():
                domain.Observation.objects.bulk_create([observation])
                connection.check_constraints()

    def test_rejects_missing_participant_and_missing_or_foreign_sample(self):
        for changes, field in (({'participant': None}, 'participant'),
                               ({'participant_id': uuid.uuid4()}, 'participant'),
                               ({'sample_id': uuid.uuid4()}, 'sample'),
                               ({'participant': self.other_participant}, 'sample')):
            observation = self.observation(**changes)
            with self.subTest(changes=changes):
                self.assert_invalid(observation, field)
                self.assertFalse(domain.Observation.objects.filter(pk=observation.pk).exists())

    def test_revalidates_live_sample_request_purchase_and_participant_despite_cached_relations(self):
        saved = self.observation()
        saved.save()
        replacement = get_user_model().objects.create_user(username='observation-replacement')
        for model, pk, field, invalid, original in (
            (Sample, self.sample.pk, 'participant', self.other_participant, self.participant),
            (ServiceRequest, self.request.pk, 'participant', None, self.participant),
            (ServiceRequest, self.request.pk, 'participant', self.other_participant, self.participant),
            (Purchase, self.purchase.pk, 'owner', self.other_user.app_user, self.user.app_user),
            (Participant, self.participant.pk, 'user', replacement, self.user),
        ):
            with self.subTest(model=model.__name__, invalid=invalid):
                model.objects.filter(pk=pk).update(**{field: invalid})
                for observation in (self.observation(), saved):
                    self.assert_invalid(observation, 'sample')
                with self.assertRaises(ValidationError):
                    saved.save(update_fields=['label'])
                model.objects.filter(pk=pk).update(**{field: original})
        self.assertEqual(domain.Observation.objects.count(), 1)

    def test_partial_save_validates_persisted_sample_when_instance_sample_is_stale(self):
        observation = self.observation(sample=None)
        observation.save()
        domain.Observation.objects.filter(pk=observation.pk).update(sample=self.sample)
        Purchase.objects.filter(pk=self.purchase.pk).update(owner=self.other_user.app_user)
        observation.label = 'Must not be saved'
        with self.assertRaises(ValidationError):
            observation.save(update_fields=['label'])
        observation.refresh_from_db()
        self.assertEqual(observation.sample_id, self.sample.pk)
        self.assertEqual(observation.label, 'Synthetic result')

    def test_persisted_participant_cannot_be_reassigned_even_without_sample_or_from_clone(self):
        observation = self.observation(sample=None)
        observation.save()
        observation.participant = self.other_participant
        self.assert_invalid(observation, 'participant')
        clone = self.observation(observation_id=observation.pk, participant=self.other_participant, sample=None)
        self.assert_invalid(clone, 'participant')
        observation.refresh_from_db()
        self.assertEqual(observation.participant_id, self.participant.pk)
        observation.label = 'Updated synthetic label'
        observation.save(update_fields=['label'])
        self.assertEqual(domain.Observation.objects.get(pk=observation.pk).label, observation.label)

    def test_protects_participant_and_optional_sample_deletion(self):
        observation = self.observation()
        observation.save()
        for item in (self.participant, self.sample):
            with self.assertRaises(ProtectedError):
                item.delete()
        observation.refresh_from_db()
        self.assertEqual(observation.sample_id, self.sample.pk)

    def test_bulk_paths_bypass_validation_but_ordinary_save_rejects_dirty_observation(self):
        observation = self.observation(participant=self.other_participant)
        domain.Observation.objects.bulk_create([observation])
        self.assert_invalid(observation, 'sample')

    def test_migration_is_additive_schema_only_and_matches_model_without_import_queries(self):
        with self.assertNumQueries(0):
            migration = reload(import_module('participants.migrations.0002_observation')).Migration
        self.assertEqual(set(migration.dependencies), {
            ('participants', '0001_initial'), ('services', '0004_sample'),
        })
        self.assertEqual([type(operation).__name__ for operation in migration.operations], ['CreateModel'])
        historical = MigrationLoader(connection).project_state([('participants', '0002_observation')]).apps.get_model(
            'participants', 'Observation',
        )
        self.assertEqual(historical._meta.db_table, 'observation')
        self.assertEqual({f.name: f.deconstruct()[1:] for f in historical._meta.local_fields},
                         {f.name: f.deconstruct()[1:] for f in domain.Observation._meta.local_fields})
