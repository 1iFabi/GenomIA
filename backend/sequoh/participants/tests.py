import uuid

from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.utils import timezone

from participants.models import Participant


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
