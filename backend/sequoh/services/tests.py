# Standalone runner for this isolated PostgreSQL slice; never use bare manage.py test.
if __name__ == '__main__':
    import ipaddress
    import os
    import sys
    import uuid as uuid_module
    from pathlib import Path
    from unittest.mock import patch

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sequoh.settings')
    from django.conf import settings
    from django.db.backends.postgresql.base import Database

    target = f'gdb_test_{uuid_module.uuid4().hex}'
    config = settings.DATABASES['default']
    assert config['ENGINE'] == 'django.db.backends.postgresql', 'PostgreSQL required'
    assert config.get('HOST') in ('127.0.0.1', '::1', 'localhost'), 'Loopback required'
    assert config.get('NAME') != target, 'Persistent DB must differ from test DB'
    config.setdefault('TEST', {})['NAME'] = target  # Before django.setup or any connection.

    admin_args = {
        'dbname': 'postgres', 'user': config.get('USER'),
        'password': config.get('PASSWORD'), 'host': config['HOST'],
        'port': config.get('PORT') or 5432, 'connect_timeout': 5,
    }
    with Database.connect(**admin_args) as admin:
        with admin.cursor() as cursor:
            cursor.execute('SELECT current_database(), inet_server_addr()::text')
            database, server = cursor.fetchone()
            assert database == 'postgres', 'Maintenance database must be postgres'
            address = ipaddress.ip_interface(server).ip
            assert address.is_loopback or getattr(address, 'ipv4_mapped', None) and address.ipv4_mapped.is_loopback, 'Maintenance server must be loopback'
            cursor.execute('SELECT rolcreatedb OR rolsuper FROM pg_roles WHERE rolname = current_user')
            assert cursor.fetchone()[0], 'CREATEDB permission required'
            cursor.execute('SELECT 1 FROM pg_database WHERE datname = %s', [target])
            assert cursor.fetchone() is None, 'Test database already exists'

        import django
        django.setup()
        from django.db import connections
        from django.test.utils import get_runner

        assert connections['default'].settings_dict['TEST']['NAME'] == target
        assert connections['default'].settings_dict['HOST'] == config['HOST']
        allowed = {'services.tests', 'accounts.tests', 'accounts.test_registration_email_challenge',
                   'participants.tests', 'profiles.tests', 'reception.tests',
                   'genetics.tests', 'reports.tests'}
        labels = sys.argv[1:]
        assert labels and set(labels) <= allowed, 'Only scoped test labels allowed'
        print(f'ISOLATED_DB={target}; labels={labels}', flush=True)
        try:
            with patch('builtins.input', return_value='no'):
                failures = get_runner(settings)(
                    verbosity=1, interactive=True, keepdb=False,
                ).run_tests(labels)
        finally:
            connections.close_all()
            cursor = admin.cursor()
            cursor.execute('SELECT 1 FROM pg_database WHERE datname = %s', [target])
            remaining = cursor.fetchone() is not None
            cursor.close()
            print(f'TEMP_DB_REMAINING={remaining}', flush=True)
            assert not remaining, 'Isolated database was not removed'
        sys.exit(bool(failures))

import uuid
import json
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from importlib import import_module, reload
from threading import Barrier
from types import SimpleNamespace

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError, connection, connections, transaction
from django.db.migrations.loader import MigrationLoader
from django.db.models.deletion import PROTECT, SET_NULL, ProtectedError
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.jwt_utils import encode_jwt
from accounts.models import AppUser, Role
from accounts.roles import grant_admin_role, grant_reception_role
from participants.models import Participant
from profiles.models import Profile
from services import models as domain
from services.legacy_profile import get_legacy_service_projection


class LegacyProfileProjectionTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='projection-client')
        self.paid = domain.PurchaseStatus.objects.get(code='PAID')
        self.pending = domain.PurchaseStatus.objects.get(code='PENDING')
        self.waiting = domain.ServiceStatus.objects.get(code='WAITING_SAMPLE')
        self.now = timezone.now()

    def purchase(self, status, *, purchased_at=None, created_at=None):
        return domain.Purchase.objects.create(
            owner=self.user.app_user, status=status, purchased_at=purchased_at,
            created_at=created_at or self.now,
        )

    def service(self, purchase, code, *, initial=True, current=True, completed_at=None):
        state = domain.ServiceStatus.objects.get(code=code)
        request = domain.ServiceRequest.objects.create(
            purchase=purchase, status=state, started_at=self.now,
            completed_at=completed_at,
        )
        if initial:
            domain.ServiceStatusLog.objects.create(
                request=request, status=self.waiting, actor=self.user.app_user,
                changed_at=self.now,
            )
        if current and state != self.waiting:
            domain.ServiceStatusLog.objects.create(
                request=request, status=state, actor=self.user.app_user,
                changed_at=self.now + timedelta(seconds=5),
            )
        return request

    def assert_projection(self, status, updated_at):
        projection = get_legacy_service_projection(self.user)
        self.assertEqual((projection.service_status, projection.updated_at, projection.can_view_results),
                         (status, updated_at, status == 'COMPLETED'))

    def test_no_purchase_and_profile_only_complete_fallback(self):
        self.assert_projection('NO_PURCHASED', None)
        self.purchase(self.pending)
        self.assert_projection('NO_PURCHASED', None)  # Pending-only without a Profile.
        profile = Profile.objects.create(user=self.user, service_status='COMPLETED')
        self.assert_projection('COMPLETED', profile.service_updated_at)
        self.purchase(self.pending, created_at=self.now + timedelta(days=1))
        self.assert_projection('COMPLETED', profile.service_updated_at)

    def test_paid_states_require_current_history_and_project_latest_log_time(self):
        for code in ('WAITING_SAMPLE', 'SAMPLE_RECEIVED', 'PROCESSING', 'COMPLETED'):
            with self.subTest(code=code):
                purchase = self.purchase(self.paid, purchased_at=self.now + timedelta(days=1))
                service = self.service(
                    purchase, code,
                    completed_at=self.now + timedelta(seconds=4) if code == 'COMPLETED' else None,
                )
                latest = domain.ServiceStatusLog.objects.filter(request=service).order_by('-changed_at').first()
                self.assert_projection('COMPLETED' if code == 'COMPLETED' else 'PENDING', latest.changed_at)
                # The next paid purchase must outrank this one even if this state was completed.
                self.now += timedelta(days=2)

    def test_pending_purchase_does_not_shadow_paid_and_newer_paid_wins(self):
        old = self.purchase(self.paid, purchased_at=self.now)
        self.service(old, 'COMPLETED', completed_at=self.now + timedelta(seconds=4))
        completed_at = self.now + timedelta(seconds=5)
        self.purchase(self.pending, created_at=self.now + timedelta(days=4))
        self.assert_projection('COMPLETED', completed_at)
        newer = self.purchase(self.paid, purchased_at=self.now + timedelta(days=1))
        new_service = self.service(newer, 'WAITING_SAMPLE')
        log = domain.ServiceStatusLog.objects.get(request=new_service)
        self.assert_projection('PENDING', log.changed_at)

    def test_newest_paid_missing_required_data_never_falls_back_to_old_completion(self):
        Profile.objects.create(user=self.user, service_status='COMPLETED')
        old = self.purchase(self.paid, purchased_at=self.now)
        self.service(old, 'COMPLETED', completed_at=self.now + timedelta(seconds=4))
        newer = self.purchase(self.paid, purchased_at=self.now + timedelta(days=1))
        self.assert_projection('NO_PURCHASED', None)  # Missing request.
        request = self.service(newer, 'WAITING_SAMPLE', initial=False)
        self.assert_projection('NO_PURCHASED', None)  # Missing initial log.
        domain.ServiceStatusLog.objects.create(request=request, status=self.waiting, actor=self.user.app_user)
        newer.purchased_at = None
        newer.save(update_fields=['purchased_at'])
        self.assert_projection('NO_PURCHASED', None)  # Malformed paid purchase must not be skipped.
        newer.purchased_at = self.now + timedelta(days=1)
        newer.save(update_fields=['purchased_at'])
        request.status = domain.ServiceStatus.objects.get(code='COMPLETED')
        request.save(update_fields=['status'])
        self.assert_projection('NO_PURCHASED', None)  # Missing current log.
        domain.ServiceStatusLog.objects.create(request=request, status=request.status, actor=self.user.app_user)
        self.assert_projection('NO_PURCHASED', None)  # Missing completion timestamp.

    def test_paid_ties_break_by_creation_and_pk_and_history_mismatch_fails_closed(self):
        older = self.purchase(self.paid, purchased_at=self.now, created_at=self.now)
        self.service(older, 'COMPLETED', completed_at=self.now + timedelta(seconds=4))
        later = self.purchase(self.paid, purchased_at=self.now, created_at=self.now + timedelta(seconds=1))
        waiting = self.service(later, 'WAITING_SAMPLE')
        self.assert_projection('PENDING', domain.ServiceStatusLog.objects.get(request=waiting).changed_at)
        highest_pk = uuid.UUID('ffffffff-ffff-ffff-ffff-ffffffffffff')
        tie = domain.Purchase.objects.create(
            pk=highest_pk, owner=self.user.app_user, status=self.paid,
            purchased_at=self.now, created_at=later.created_at,
        )
        self.assert_projection('NO_PURCHASED', None)  # A tied newer paid purchase has no request.
        tie.status = self.pending
        tie.save(update_fields=['status'])
        domain.ServiceStatusLog.objects.create(
            request=waiting, status=domain.ServiceStatus.objects.get(code='PROCESSING'),
            actor=self.user.app_user, changed_at=self.now + timedelta(seconds=10),
        )
        self.assert_projection('NO_PURCHASED', None)  # Latest history disagrees with current state.


class PurchaseSchemaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username='purchase-client')
        cls.owner = cls.user.app_user

    def test_tables_keys_and_exact_scope(self):
        for name, table, key in (
            ('Purchase', 'purchase', 'purchase_id'),
            ('PurchaseStatus', 'purchase_status', 'purchase_status_id'),
            ('ServiceStatus', 'service_status', 'service_status_id'),
        ):
            model = getattr(domain, name)
            self.assertEqual((model._meta.db_table, model._meta.pk.name), (table, key))
            self.assertIsInstance(model._meta.pk.get_default(), uuid.UUID)
        with connection.cursor() as cursor:
            tables = set(connection.introspection.table_names(cursor))
        self.assertTrue({'purchase', 'purchase_status', 'service_status'} <= tables)
        self.assertEqual(
            {f.name for f in domain.Purchase._meta.local_fields},
            {'purchase_id', 'owner', 'status', 'purchased_at', 'created_at'},
        )

    def test_catalogs_seed_once_using_historical_models(self):
        expected = (
            (domain.PurchaseStatus, {'PENDING', 'PAID', 'CANCELLED', 'REFUNDED'}),
            (domain.ServiceStatus, {'WAITING_SAMPLE', 'SAMPLE_RECEIVED', 'PROCESSING', 'COMPLETED'}),
        )
        for model, codes in expected:
            self.assertEqual(set(model.objects.values_list('code', flat=True)), codes)
        seed = import_module('services.migrations.0002_seed_statuses').seed_statuses
        historical = MigrationLoader(connection).project_state([('services', '0001_initial')]).apps
        before = {model._meta.label: dict(model.objects.values_list('code', 'pk')) for model, _ in expected}
        for _ in range(2):
            seed(historical, SimpleNamespace(connection=connection))
        for model, codes in expected:
            self.assertEqual(dict(model.objects.values_list('code', 'pk')), before[model._meta.label])
            self.assertTrue(model._meta.get_field('code').unique)
            with self.assertRaises(IntegrityError):
                with transaction.atomic():
                    model.objects.create(code=next(iter(codes)), name='Duplicate')

    def test_owner_and_status_constraints_keep_nullable_sql_status(self):
        status = domain.PurchaseStatus.objects.get(code='PENDING')
        self.assertEqual(domain.Purchase._meta.get_field('owner').remote_field.model._meta.label, 'accounts.AppUser')
        self.assertEqual(domain.Purchase._meta.get_field('owner').column, 'user_id')
        self.assertEqual(domain.Purchase._meta.get_field('status').column, 'purchase_status_id')
        self.assertEqual(domain.Purchase._meta.get_field('owner').remote_field.on_delete, PROTECT)
        self.assertEqual(domain.Purchase._meta.get_field('status').remote_field.on_delete, PROTECT)
        self.assertFalse(domain.Purchase._meta.get_field('owner').null)
        self.assertTrue(domain.Purchase._meta.get_field('status').null)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                domain.Purchase.objects.create(status=status)
        pending = domain.Purchase.objects.create(owner=self.owner, status=status)
        without_status = domain.Purchase.objects.create(owner=self.owner)
        self.assertEqual(pending.status.code, 'PENDING')
        self.assertIsNone(without_status.status)
        self.assertIsNone(pending.purchased_at)
        self.assertTrue(timezone.is_aware(pending.created_at))
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                domain.Purchase.objects.create(owner=self.owner, status_id=uuid.uuid4())
                connection.check_constraints()  # PostgreSQL defers foreign keys until commit.

    def test_repeated_purchases_and_explicit_payment_timestamp(self):
        first = domain.Purchase.objects.create(owner=self.owner)
        paid_at = timezone.now()
        second = domain.Purchase.objects.create(
            owner=self.owner, status=domain.PurchaseStatus.objects.get(code='PAID'), purchased_at=paid_at,
            created_at=first.created_at + timedelta(microseconds=1),
        )
        self.assertNotEqual(first.pk, second.pk)
        self.assertEqual(list(domain.Purchase.objects.filter(owner=self.owner)), [second, first])
        self.assertIsNone(first.purchased_at)
        self.assertEqual(second.purchased_at, paid_at)

    def test_django_flags_do_not_choose_purchase_owner(self):
        staff = get_user_model().objects.create_user(
            username='staff-client', is_staff=True, is_superuser=True,
        )
        purchase = domain.Purchase.objects.create(owner=self.owner)
        self.assertEqual(staff.app_user.role.code, 'CLIENTE')
        self.assertEqual(purchase.owner_id, self.owner.pk)
        self.assertFalse(domain.Purchase.objects.filter(owner=staff.app_user).exists())
        self.assertEqual(purchase.owner.django_user_id, self.user.pk)

    def test_protects_account_and_status_deletion(self):
        status = domain.PurchaseStatus.objects.get(code='PENDING')
        purchase = domain.Purchase.objects.create(owner=self.owner, status=status)
        for delete in (self.owner.delete, self.user.delete, status.delete):
            with self.assertRaises(ProtectedError):
                delete()
        self.assertTrue(domain.Purchase.objects.filter(pk=purchase.pk).exists())

    def test_migration_state_and_physical_ordering_indexes(self):
        state = MigrationLoader(connection).project_state([('services', '0002_seed_statuses')])
        model = state.apps.get_model('services', 'Purchase')
        indexes = {index.name: index.fields for index in model._meta.indexes}
        self.assertEqual(indexes, {
            'purchase_owner_created_idx': ['owner', '-created_at'],
            'purchase_status_created_idx': ['status', '-created_at'],
        })
        with connection.cursor() as cursor:
            constraints = connection.introspection.get_constraints(cursor, 'purchase')
        for name in indexes:
            self.assertTrue(constraints[name]['index'])


class ServiceRequestSchemaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username='service-client')
        cls.other_user = get_user_model().objects.create_user(username='other-service-client')
        cls.purchase = domain.Purchase.objects.create(
            owner=cls.user.app_user, status=domain.PurchaseStatus.objects.get(code='PAID'),
        )
        cls.waiting = domain.ServiceStatus.objects.get(code='WAITING_SAMPLE')
        from participants.models import Participant
        cls.participant = Participant.objects.create(user=cls.user, participant_code='service-owned')
        cls.other_participant = Participant.objects.create(
            user=cls.other_user, participant_code='service-other',
        )

    def test_sql_columns_required_keys_defaults_and_catalog_references(self):
        request = domain.ServiceRequest.objects.create(purchase=self.purchase, status=self.waiting)
        self.assertEqual((request._meta.db_table, request._meta.pk.name),
                         ('service_request', 'service_request_id'))
        self.assertIsInstance(request.pk, uuid.UUID)
        self.assertEqual({f.column for f in request._meta.local_fields}, {
            'service_request_id', 'purchase_id', 'participant_id', 'service_status_id',
            'created_at', 'started_at', 'completed_at',
        })
        self.assertIsNone(request.participant_id)
        self.assertIsNone(request.completed_at)
        self.assertTrue(timezone.is_aware(request.created_at))
        self.assertTrue(timezone.is_aware(request.started_at))
        self.assertEqual(request.status.code, 'WAITING_SAMPLE')
        log = domain.ServiceStatusLog.objects.create(
            request=request, status=self.waiting, actor=self.user.app_user,
        )
        self.assertEqual((log._meta.db_table, log._meta.pk.name),
                         ('service_status_log', 'service_status_log_id'))
        self.assertIsInstance(log.pk, uuid.UUID)
        self.assertEqual({f.column for f in log._meta.local_fields}, {
            'service_status_log_id', 'service_request_id', 'service_status_id',
            'user_id', 'changed_at', 'comment',
        })
        self.assertIsNone(log.comment)
        self.assertTrue(timezone.is_aware(log.changed_at))
        self.assertEqual(log.actor.django_user_id, self.user.pk)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                domain.ServiceStatusLog.objects.create(request=request, status=self.waiting)
        other_purchase = domain.Purchase.objects.create(owner=self.other_user.app_user)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                domain.ServiceRequest.objects.create(purchase=other_purchase)
        for model, required in (
            (domain.ServiceRequest, ('purchase', 'status', 'created_at', 'started_at')),
            (domain.ServiceStatusLog, ('request', 'status', 'actor', 'changed_at')),
        ):
            for field in required:
                self.assertFalse(model._meta.get_field(field).null)
        for model, optional in (
            (domain.ServiceRequest, ('participant', 'completed_at')),
            (domain.ServiceStatusLog, ('comment',)),
        ):
            for field in optional:
                self.assertTrue(model._meta.get_field(field).null)
        self.assertEqual(domain.ServiceStatusLog._meta.get_field('actor').remote_field.model._meta.label,
                         'accounts.AppUser')

    def test_owned_participant_optional_but_cross_user_creation_and_reassignment_rejected(self):
        with self.assertRaises(ValidationError):
            domain.ServiceRequest.objects.create(
                purchase=self.purchase, participant=self.other_participant, status=self.waiting,
            )
        request = domain.ServiceRequest.objects.create(
            purchase=self.purchase, participant=self.participant, status=self.waiting,
        )
        request.participant = self.other_participant
        with self.assertRaises(ValidationError):
            request.clean()
        with self.assertRaises(ValidationError):
            request.save()
        request.refresh_from_db()
        self.assertEqual(request.participant_id, self.participant.pk)
        another_purchase = domain.Purchase.objects.create(owner=self.other_user.app_user)
        request.purchase = another_purchase
        with self.assertRaises(ValidationError):
            request.save()
        request.refresh_from_db()
        self.assertEqual(request.purchase_id, self.purchase.pk)

    def test_multiple_purchases_one_owner_but_unique_purchase_request(self):
        first = domain.ServiceRequest.objects.create(purchase=self.purchase, status=self.waiting)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                domain.ServiceRequest.objects.create(purchase=self.purchase, status=self.waiting)
        second_purchase = domain.Purchase.objects.create(
            owner=self.user.app_user, status=domain.PurchaseStatus.objects.get(code='PAID'),
        )
        second = domain.ServiceRequest.objects.create(purchase=second_purchase, status=self.waiting)
        self.assertNotEqual(first.pk, second.pk)
        self.assertEqual(domain.ServiceRequest.objects.filter(purchase__owner=self.user.app_user).count(), 2)
        with connection.cursor() as cursor:
            constraints = connection.introspection.get_constraints(cursor, 'service_request')
        self.assertTrue(any(info['unique'] and info['columns'] == ['purchase_id']
                            for info in constraints.values()))

    def test_completed_at_is_nullable_and_cannot_precede_started_at_at_database(self):
        start = timezone.now()
        request = domain.ServiceRequest.objects.create(
            purchase=self.purchase, status=self.waiting, started_at=start,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                domain.ServiceRequest.objects.filter(pk=request.pk).update(
                    completed_at=start - timedelta(seconds=1),
                )
        request.completed_at = start + timedelta(seconds=1)
        request.save()
        self.assertEqual(domain.ServiceRequest.objects.get(pk=request.pk).completed_at,
                         start + timedelta(seconds=1))

    def test_protects_purchase_participant_status_actor_and_logged_history(self):
        request = domain.ServiceRequest.objects.create(
            purchase=self.purchase, participant=self.participant, status=self.waiting,
        )
        log = domain.ServiceStatusLog.objects.create(
            request=request, status=self.waiting, actor=self.other_user.app_user,
            comment='Received by staff',
        )
        for field in (domain.ServiceRequest._meta.get_field('purchase'),
                      domain.ServiceRequest._meta.get_field('participant'),
                      domain.ServiceRequest._meta.get_field('status'),
                      domain.ServiceStatusLog._meta.get_field('request'),
                      domain.ServiceStatusLog._meta.get_field('status'),
                      domain.ServiceStatusLog._meta.get_field('actor')):
            self.assertEqual(field.remote_field.on_delete, PROTECT)
        for item in (self.purchase, self.participant, self.waiting,
                     self.other_user.app_user, self.other_user, request):
            with self.assertRaises(ProtectedError):
                item.delete()
        self.assertTrue(domain.ServiceStatusLog.objects.filter(pk=log.pk).exists())

    def test_migration_indexes_and_no_transition_rule_in_schema(self):
        migration = import_module('services.migrations.0003_service_request_status_log').Migration
        self.assertIn(('services', '0002_seed_statuses'), migration.dependencies)
        state = MigrationLoader(connection).project_state([('services', '0003_service_request_status_log')])
        for name, table, indexes in (
            ('ServiceRequest', 'service_request', {'service_req_created_idx': ['-created_at']}),
            ('ServiceStatusLog', 'service_status_log',
             {'service_log_request_time_idx': ['request', '-changed_at']}),
        ):
            model = state.apps.get_model('services', name)
            self.assertEqual(model._meta.db_table, table)
            self.assertEqual({i.name: i.fields for i in model._meta.indexes}, indexes)
            with connection.cursor() as cursor:
                constraints = connection.introspection.get_constraints(cursor, table)
            for index in indexes:
                self.assertTrue(constraints[index]['index'])
        request = domain.ServiceRequest.objects.create(purchase=self.purchase, status=self.waiting)
        completed = domain.ServiceStatus.objects.get(code='COMPLETED')
        log = domain.ServiceStatusLog.objects.create(
            request=request, status=completed, actor=self.user.app_user,
        )
        self.assertEqual(log.status, completed)  # Transition rules belong to the later workflow.


    def test_database_unique_constraint_serializes_competing_inserts(self):
        # Thread-created fixtures commit outside TestCase's transaction; remove them in a
        # worker so this test neither flushes migration seeds nor leaks committed rows.
        def create_purchase():
            try:
                user = get_user_model().objects.create_user(username='concurrent-service-client')
                purchase = domain.Purchase.objects.create(
                    owner=user.app_user, status=domain.PurchaseStatus.objects.get(code='PAID'),
                )
                status = domain.ServiceStatus.objects.get(code='WAITING_SAMPLE')
                return purchase.pk, user.pk, status.pk
            finally:
                connections.close_all()

        def remove_purchase(purchase_id, user_id):
            try:
                domain.ServiceRequest.objects.filter(purchase_id=purchase_id).delete()
                domain.Purchase.objects.filter(pk=purchase_id).delete()
                get_user_model().objects.filter(pk=user_id).delete()
            finally:
                connections.close_all()

        gate = Barrier(2)

        def insert_request(purchase_id, status_id):
            try:
                gate.wait(timeout=10)
                try:
                    with transaction.atomic():
                        domain.ServiceRequest.objects.create(purchase_id=purchase_id, status_id=status_id)
                except IntegrityError:
                    return 'duplicate'
                return 'created'
            finally:
                connections.close_all()  # Threads must release sessions before test DB teardown.

        with ThreadPoolExecutor(max_workers=2) as pool:
            purchase_id, user_id, status_id = pool.submit(create_purchase).result()
            try:
                results = list(pool.map(lambda _: insert_request(purchase_id, status_id), range(2)))
                self.assertEqual(sorted(results), ['created', 'duplicate'])
                self.assertEqual(domain.ServiceRequest.objects.filter(purchase_id=purchase_id).count(), 1)
            finally:
                pool.submit(remove_purchase, purchase_id, user_id).result()


class SampleSchemaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username='schema-sample-owner')
        cls.participant = Participant.objects.create(user=cls.user, participant_code='schema-sample')
        cls.purchase = domain.Purchase.objects.create(owner=cls.user.app_user)
        cls.request = domain.ServiceRequest.objects.create(
            purchase=cls.purchase, participant=cls.participant,
            status=domain.ServiceStatus.objects.get(code='WAITING_SAMPLE'),
        )
        cls.other_user = get_user_model().objects.create_user(username='schema-sample-other')
        cls.other_participant = Participant.objects.create(
            user=cls.other_user, participant_code='schema-sample-other',
        )
        cls.second_request = domain.ServiceRequest.objects.create(
            purchase=domain.Purchase.objects.create(owner=cls.user.app_user),
            participant=cls.participant, status=cls.request.status,
        )
        cls.other_request = domain.ServiceRequest.objects.create(
            purchase=domain.Purchase.objects.create(owner=cls.other_user.app_user),
            participant=cls.other_participant, status=cls.request.status,
        )

    def sample(self, **changes):
        values = dict(service_request=self.request, participant=self.participant,
                      sample_code=f'schema-{uuid.uuid4().hex}', sample_type='saliva')
        return domain.Sample(**(values | changes))

    def assert_invalid(self, sample, field):
        for action in (sample.clean, sample.save):
            with self.subTest(action=action.__name__):
                with self.assertRaises(ValidationError) as error:
                    action()
                self.assertIn(field, error.exception.message_dict)

    def test_creates_sample_bound_to_one_service_and_participant(self):
        profiles = list(Profile.objects.values())
        sample = domain.Sample.objects.create(
            service_request=self.request, participant=self.participant,
            sample_code='schema-sample-001', sample_type='saliva',
        )
        sample.refresh_from_db()
        self.assertEqual(sample.service_request_id, self.request.pk)
        self.assertEqual(sample.participant_id, self.participant.pk)
        self.assertEqual(sample.status, 'available')
        self.assertIsInstance(sample.pk, uuid.UUID)
        self.assertTrue(timezone.is_aware(sample.created_at))
        for field in ('parent_sample', 'material', 'collection_method', 'collected_at',
                      'storage_location', 'metadata'):
            self.assertIsNone(getattr(sample, field))
        optional = dict(material='DNA', collection_method='swab', collected_at=timezone.now(),
                        storage_location='Freezer A', metadata={'batch': ['A1']}, status='stored')
        for field, value in optional.items():
            setattr(sample, field, value)
        sample.full_clean()
        sample.save()
        sample.refresh_from_db()
        for field, value in optional.items():
            self.assertEqual(getattr(sample, field), value)
        self.request.refresh_from_db()
        self.assertEqual(self.request.status.code, 'WAITING_SAMPLE')
        self.assertFalse(domain.ServiceStatusLog.objects.exists())
        self.assertEqual(list(Profile.objects.values()), profiles)

    def test_exact_physical_schema_columns_types_and_foreign_keys(self):
        columns = {
            'sample_id': ('uuid', None, 'NO'),
            'service_request_id': ('uuid', None, 'NO'),
            'participant_id': ('uuid', None, 'NO'),
            'parent_sample_id': ('uuid', None, 'YES'),
            'sample_code': ('character varying', 96, 'NO'),
            'sample_type': ('character varying', 64, 'NO'),
            'material': ('character varying', 64, 'YES'),
            'collection_method': ('character varying', 128, 'YES'),
            'collected_at': ('timestamp with time zone', None, 'YES'),
            'storage_location': ('character varying', 255, 'YES'),
            'metadata': ('jsonb', None, 'YES'),
            'status': ('character varying', 32, 'NO'),
            'created_at': ('timestamp with time zone', None, 'NO'),
        }
        self.assertEqual((domain.Sample._meta.db_table, domain.Sample._meta.pk.name), ('sample', 'sample_id'))
        self.assertEqual({field.column for field in domain.Sample._meta.local_fields}, set(columns))
        for field in domain.Sample._meta.local_fields:
            _, length, nullable = columns[field.column]
            self.assertEqual(field.null, nullable == 'YES')
            self.assertEqual(field.blank, field.null)
            if length is not None:
                self.assertEqual(field.max_length, length)
        self.assertFalse(domain.Sample._meta.get_field('status').choices)
        with connection.cursor() as cursor:
            cursor.execute('SELECT column_name, data_type, character_maximum_length, is_nullable '
                           "FROM information_schema.columns WHERE table_schema = current_schema() AND table_name = 'sample'")
            self.assertEqual({row[0]: row[1:] for row in cursor.fetchall()}, columns)
            constraints = connection.introspection.get_constraints(cursor, 'sample')
        self.assertTrue(any(info['primary_key'] and info['columns'] == ['sample_id']
                            for info in constraints.values()))
        for field, table, deletion in (
            ('service_request', 'service_request', PROTECT),
            ('participant', 'participant', PROTECT), ('parent_sample', 'sample', SET_NULL),
        ):
            relation = domain.Sample._meta.get_field(field)
            self.assertEqual(relation.remote_field.on_delete, deletion)
            self.assertTrue(any(info['foreign_key'] == (table, f'{table}_id')
                                and info['columns'] == [relation.column] for info in constraints.values()))

    def test_postgresql_defaults_support_required_columns_only_insert(self):
        with connection.cursor() as cursor:
            cursor.execute('SELECT column_name, column_default FROM information_schema.columns '
                           "WHERE table_schema = current_schema() AND table_name = 'sample' "
                           "AND column_name IN ('status', 'created_at')")
            defaults = dict(cursor.fetchall())
            self.assertIsNotNone(defaults['status'])
            self.assertIsNotNone(defaults['created_at'])
            cursor.execute('INSERT INTO sample (sample_id, service_request_id, participant_id, sample_code, sample_type) '
                           'VALUES (%s, %s, %s, %s, %s) RETURNING status, created_at, statement_timestamp()',
                           [uuid.uuid4(), self.request.pk, self.participant.pk, 'sql-defaults', 'saliva'])
            status, created_at, database_now = cursor.fetchone()
        self.assertEqual(status, 'available')
        self.assertTrue(timezone.is_aware(created_at))
        self.assertLess(abs(created_at - database_now), timedelta(seconds=1))

    def test_database_uniqueness_and_referential_integrity(self):
        self.sample(sample_code='unique-sample').save()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.sample(sample_code='unique-sample').save()
        for field in ('service_request_id', 'participant_id', 'parent_sample_id'):
            sample = self.sample()
            setattr(sample, field, uuid.uuid4())
            with self.subTest(field=field), self.assertRaises(IntegrityError), transaction.atomic():
                domain.Sample.objects.bulk_create([sample])
                connection.check_constraints()

    def test_rejects_missing_and_mismatched_required_identities(self):
        for changes, field in (
            ({'service_request': None}, 'service_request'),
            ({'participant': None}, 'participant'),
            ({'participant': self.other_participant}, 'participant'),
            ({'service_request': self.other_request}, 'participant'),
        ):
            with self.subTest(changes=changes):
                sample = self.sample(**changes)
                self.assert_invalid(sample, field)
                self.assertFalse(domain.Sample.objects.filter(pk=sample.pk).exists())
        sample = self.sample()
        sample.service_request_id = uuid.uuid4()
        self.assert_invalid(sample, 'service_request')
        sample.participant_id = uuid.uuid4()
        sample.service_request = self.request
        self.assert_invalid(sample, 'participant')

    def test_revalidates_live_request_and_purchase_for_creation_and_ordinary_save(self):
        saved = self.sample()
        saved.save()  # Keep cached relations deliberately; validation must read persisted ownership.
        for participant, field in ((None, 'service_request'), (self.other_participant, 'participant')):
            domain.ServiceRequest.objects.filter(pk=self.request.pk).update(participant=participant)
            for sample in (self.sample(), saved):
                self.assert_invalid(sample, field)
        self.assert_invalid(self.sample(participant=self.other_participant), 'service_request')
        domain.ServiceRequest.objects.filter(pk=self.request.pk).update(participant=self.participant)
        domain.Purchase.objects.filter(pk=self.purchase.pk).update(owner=self.other_user.app_user)
        for sample in (self.sample(), saved):
            self.assert_invalid(sample, 'service_request')
        self.assertEqual(domain.Sample.objects.count(), 1)

    def test_persisted_service_and_participant_are_immutable_even_for_compatible_rebinding(self):
        sample = self.sample()
        sample.save()
        for request, participant in ((self.second_request, self.participant),
                                     (self.other_request, self.other_participant)):
            sample.service_request, sample.participant = request, participant
            self.assert_invalid(sample, 'service_request')
        clone = self.sample(sample_id=sample.pk, service_request=self.other_request,
                            participant=self.other_participant)
        self.assert_invalid(clone, 'service_request')
        sample.refresh_from_db()
        domain.ServiceRequest.objects.filter(pk=self.request.pk).update(participant=self.other_participant)
        domain.Purchase.objects.filter(pk=self.purchase.pk).update(owner=self.other_user.app_user)
        sample.participant = self.other_participant
        self.assert_invalid(sample, 'participant')
        sample.refresh_from_db()
        self.assertEqual((sample.service_request_id, sample.participant_id), (self.request.pk, self.participant.pk))

    def test_parent_must_match_live_service_and_participant_on_create_and_save(self):
        saved = self.sample()
        saved.save()
        for request, participant in ((self.second_request, self.participant),
                                     (self.other_request, self.other_participant)):
            parent = self.sample(service_request=request, participant=participant)
            parent.save()
            self.assert_invalid(self.sample(parent_sample=parent), 'parent_sample')
            saved.parent_sample = parent
            self.assert_invalid(saved, 'parent_sample')
        domain.Sample.objects.filter(pk=parent.pk).update(service_request=self.request)
        self.assert_invalid(self.sample(parent_sample=parent), 'parent_sample')
        self.assert_invalid(self.sample(parent_sample_id=uuid.uuid4()), 'parent_sample')

    def test_rejects_self_indirect_and_preexisting_ancestor_cycles(self):
        root = self.sample()
        root.parent_sample = root
        self.assert_invalid(root, 'parent_sample')
        root.parent_sample = None
        root.save()
        child = self.sample(parent_sample=root)
        child.save()
        grandchild = self.sample(parent_sample=child)
        grandchild.save()
        root.parent_sample = grandchild
        self.assert_invalid(root, 'parent_sample')
        child.parent_sample = child
        self.assert_invalid(child, 'parent_sample')
        domain.Sample.objects.filter(pk=root.pk).update(parent_sample=child)
        self.assert_invalid(self.sample(parent_sample=grandchild), 'parent_sample')

    def test_protects_service_and_participant_and_nulls_deleted_parent(self):
        parent = self.sample()
        parent.save()
        child = self.sample(parent_sample=parent)
        child.save()
        for item in (self.request, self.participant, self.purchase, self.user):
            with self.assertRaises(ProtectedError):
                item.delete()
        parent.delete()
        child.refresh_from_db()
        self.assertIsNone(child.parent_sample_id)
        self.assertEqual(child.service_request_id, self.request.pk)

    def test_bulk_paths_bypass_ownership_validation_but_ordinary_save_rejects_bad_rows(self):
        sample = self.sample(participant=self.other_participant)
        domain.Sample.objects.bulk_create([sample])
        self.assert_invalid(sample, 'participant')
        sample = self.sample()
        sample.save()
        domain.Sample.objects.filter(pk=sample.pk).update(participant=self.other_participant)
        sample.refresh_from_db()
        self.assert_invalid(sample, 'participant')

    def test_migration_is_schema_only_imports_without_queries_and_matches_model(self):
        with self.assertNumQueries(0):
            migration = reload(import_module('services.migrations.0004_sample')).Migration
        self.assertEqual(set(migration.dependencies), {
            ('services', '0003_service_request_status_log'), ('participants', '0001_initial'),
        })
        self.assertEqual([type(operation).__name__ for operation in migration.operations], ['CreateModel'])
        historical = MigrationLoader(connection).project_state([('services', '0004_sample')]).apps.get_model('services', 'Sample')
        self.assertEqual(historical._meta.db_table, 'sample')
        self.assertEqual({field.name: field.deconstruct()[1:] for field in historical._meta.local_fields},
                         {field.name: field.deconstruct()[1:] for field in domain.Sample._meta.local_fields})
        call_command('makemigrations', check=True, dry_run=True)  # Inside the guarded test database only.


class ManualPurchaseFlowTests(APITestCase):
    def setUp(self):
        users = get_user_model().objects
        self.admin = users.create_user(username='payment-admin')
        grant_admin_role(self.admin)
        self.reception = users.create_user(username='payment-reception')
        grant_reception_role(self.reception)
        self.owner = users.create_user(username='payment-client')
        self.other = users.create_user(username='payment-other-client')
        self.client.cookies['csrftoken'] = 'matching-csrf'

    def as_actor(self, user):
        self.client.cookies[settings.AUTH_COOKIE_NAME] = encode_jwt({'sub': str(user.pk)})

    def post_json(self, path, data):
        self.client.cookies['csrftoken'] = 'matching-csrf'
        return self.client.post(
            path, data=json.dumps(data), content_type='application/json',
            HTTP_X_CSRFTOKEN='matching-csrf',
        )

    def test_staff_creates_pending_purchase_for_selected_client(self):
        self.as_actor(self.admin)
        response = self.post_json('/api/services/purchases/', {'userId': self.owner.pk})
        self.assertEqual(response.status_code, 201)
        purchase = domain.Purchase.objects.get(pk=response.data['purchaseId'])
        self.assertEqual(purchase.owner, self.owner.app_user)
        self.assertEqual(purchase.status.code, 'PENDING')
        self.assertIsNone(purchase.purchased_at)

    def test_pay_is_atomic_and_repeating_returns_original_request_and_history(self):
        self.as_actor(self.reception)
        participant = Participant.objects.create(user=self.owner, participant_code='payment-owned')
        purchase = domain.Purchase.objects.create(
            owner=self.owner.app_user, status=domain.PurchaseStatus.objects.get(code='PENDING'),
        )
        path = f'/api/services/purchases/{purchase.pk}/pay/'
        first = self.post_json(path, {})
        self.assertEqual(first.status_code, 200)
        purchase.refresh_from_db()
        self.assertEqual(purchase.status.code, 'PAID')
        service = domain.ServiceRequest.objects.get(purchase=purchase)
        self.assertEqual(service.participant, participant)
        self.assertEqual(service.status.code, 'WAITING_SAMPLE')
        history = domain.ServiceStatusLog.objects.get(request=service)
        self.assertEqual(history.status, service.status)
        self.assertEqual(history.actor, self.reception.app_user)
        second = self.post_json(path, {})
        self.assertEqual(second.status_code, 200, second.data)
        self.assertEqual(second.data, first.data)
        self.assertEqual(domain.ServiceRequest.objects.filter(purchase=purchase).count(), 1)
        self.assertEqual(domain.ServiceStatusLog.objects.filter(request=service).count(), 1)
        purchase.refresh_from_db()
        self.assertEqual(first.data['purchasedAt'], purchase.purchased_at.isoformat().replace('+00:00', 'Z'))

    def test_only_explicit_staff_can_create_or_pay_with_valid_csrf(self):
        staff = get_user_model().objects.create_user(
            username='payment-flag-only', is_staff=True, is_superuser=True,
        )
        staff.groups.add(Group.objects.get_or_create(name='ADMIN')[0])
        analyst = get_user_model().objects.create_user(username='payment-analyst')
        AppUser.objects.filter(django_user=analyst).update(role=Role.objects.get(code='ANALISTA'))
        unmapped = get_user_model().objects.bulk_create(
            [get_user_model()(username='payment-unmapped')],
        )[0]
        purchase = domain.Purchase.objects.create(
            owner=self.owner.app_user, status=domain.PurchaseStatus.objects.get(code='PENDING'),
        )
        for actor in (self.owner, staff, analyst, unmapped):
            self.as_actor(actor)
            for path, payload in (
                ('/api/services/purchases/', {'userId': self.owner.pk}),
                (f'/api/services/purchases/{purchase.pk}/pay/', {}),
            ):
                with self.subTest(actor=actor.username, path=path):
                    response = self.post_json(path, payload)
                    self.assertEqual(response.status_code, 403, response.data)
                    self.assertEqual(domain.Purchase.objects.count(), 1)
                    self.assertEqual(domain.ServiceRequest.objects.count(), 0)
                    self.assertEqual(domain.ServiceStatusLog.objects.count(), 0)
        purchase.refresh_from_db()
        self.assertEqual(purchase.status.code, 'PENDING')
        self.assertIsNone(purchase.purchased_at)

    def test_creation_rejects_spoofed_fields_bad_ids_and_ineligible_targets(self):
        self.as_actor(self.reception)
        for payload in ({}, {'userId': True}, {'userId': '1'}, {'userId': 1.0},
                        {'userId': 0}, {'userId': -2}, {'userId': []},
                        {'user_id': self.owner.pk},
                        {'userId': self.owner.pk, 'owner': str(self.other.app_user.pk)},
                        {'userId': self.owner.pk, 'status': 'PAID'},
                        {'userId': self.owner.pk, 'actor': str(self.reception.app_user.pk)},
                        {'userId': self.owner.pk, 'purchasedAt': timezone.now().isoformat()}):
            with self.subTest(payload=payload):
                response = self.post_json('/api/services/purchases/', payload)
                self.assertEqual(response.status_code, 400, response.data)
        inactive = get_user_model().objects.create_user(username='payment-inactive', is_active=False)
        unmapped = get_user_model().objects.bulk_create(
            [get_user_model()(username='payment-target-unmapped')],
        )[0]
        analyst = get_user_model().objects.create_user(username='payment-target-analyst')
        AppUser.objects.filter(django_user=analyst).update(role=Role.objects.get(code='ANALISTA'))
        for user_id in (self.admin.pk, self.reception.pk, analyst.pk, inactive.pk,
                        unmapped.pk, 999999999):
            response = self.post_json('/api/services/purchases/', {'userId': user_id})
            self.assertEqual(response.status_code, 404, response.data)
            self.assertEqual(response.data, {'error': 'Client not found'})
        self.assertEqual(domain.Purchase.objects.count(), 0)
        self.assertEqual(domain.ServiceRequest.objects.count(), 0)
        self.assertEqual(domain.ServiceStatusLog.objects.count(), 0)
        first = self.post_json('/api/services/purchases/', {'userId': self.owner.pk})
        second = self.post_json('/api/services/purchases/', {'userId': self.owner.pk})
        self.assertEqual((first.status_code, second.status_code), (201, 201))
        self.assertNotEqual(first.data['purchaseId'], second.data['purchaseId'])
        self.assertEqual(domain.Purchase.objects.filter(owner=self.owner.app_user).count(), 2)

    def test_payment_rejects_unknown_state_body_and_no_longer_client_owner(self):
        self.as_actor(self.admin)
        statuses = ('PENDING', 'CANCELLED', 'REFUNDED', None)
        purchases = [domain.Purchase.objects.create(
            owner=self.owner.app_user,
            status=domain.PurchaseStatus.objects.get(code=code) if code else None,
        ) for code in statuses]
        path = f'/api/services/purchases/{purchases[0].pk}/pay/'
        for payload in ({'actor': str(self.admin.app_user.pk)},
                        {'owner': str(self.other.app_user.pk)}, {'status': 'PAID'},
                        {'purchasedAt': timezone.now().isoformat()}, {'userId': self.other.pk}):
            self.assertEqual(self.post_json(path, payload).status_code, 400)
        for purchase in purchases[1:]:
            response = self.post_json(f'/api/services/purchases/{purchase.pk}/pay/', {})
            self.assertEqual(response.status_code, 409, response.data)
        response = self.post_json(f'/api/services/purchases/{uuid.uuid4()}/pay/', {})
        self.assertEqual(response.status_code, 404, response.data)
        AppUser.objects.filter(pk=self.owner.app_user.pk).update(role=Role.objects.get(code='ANALISTA'))
        response = self.post_json(path, {})
        self.assertEqual(response.status_code, 404, response.data)
        self.assertEqual(domain.ServiceRequest.objects.count(), 0)
        self.assertEqual(domain.ServiceStatusLog.objects.count(), 0)
        for purchase in purchases:
            purchase.refresh_from_db()
            self.assertIsNone(purchase.purchased_at)
        self.assertEqual(domain.Purchase.objects.filter(status__code='PAID').count(), 0)

    def test_payment_links_only_owner_participant_and_allows_multiple_services(self):
        self.as_actor(self.admin)
        owned = Participant.objects.create(user=self.owner, participant_code='pay-owned')
        other = Participant.objects.create(user=self.other, participant_code='pay-other')
        requests = []
        for user, expected in ((self.owner, owned), (self.other, other), (self.owner, owned)):
            created = self.post_json('/api/services/purchases/', {'userId': user.pk})
            self.assertEqual(created.status_code, 201, created.data)
            paid = self.post_json(f"/api/services/purchases/{created.data['purchaseId']}/pay/", {})
            self.assertEqual(paid.status_code, 200, paid.data)
            request = domain.ServiceRequest.objects.get(pk=paid.data['serviceRequestId'])
            self.assertEqual(request.participant, expected)
            self.assertEqual(request.purchase.owner.django_user_id, expected.user_id)
            requests.append(request.pk)
        self.assertEqual(len(set(requests)), 3)
        self.assertEqual(domain.ServiceStatusLog.objects.count(), 3)

    def test_payment_uses_purchase_row_lock_and_rolls_back_failed_history(self):
        self.as_actor(self.admin)
        purchase = domain.Purchase.objects.create(
            owner=self.owner.app_user, status=domain.PurchaseStatus.objects.get(code='PENDING'),
        )
        path = f'/api/services/purchases/{purchase.pk}/pay/'
        savepoints = len(connection.savepoint_ids)

        def fail_log(*args, **kwargs):
            self.assertTrue(connection.in_atomic_block)
            self.assertGreater(len(connection.savepoint_ids), savepoints)
            raise RuntimeError('simulated history write failure')

        with CaptureQueriesContext(connection) as queries:
            with patch('services.views.ServiceStatusLog.objects.create', side_effect=fail_log):
                with self.assertRaisesMessage(RuntimeError, 'simulated history write failure'):
                    self.post_json(path, {})
        self.assertTrue(any('FOR UPDATE' in q['sql'] and '"purchase"' in q['sql']
                            for q in queries.captured_queries))
        purchase.refresh_from_db()
        self.assertEqual(purchase.status.code, 'PENDING')
        self.assertIsNone(purchase.purchased_at)
        self.assertEqual(domain.ServiceRequest.objects.count(), 0)
        self.assertEqual(domain.ServiceStatusLog.objects.count(), 0)
        self.assertEqual(self.post_json(path, {}).status_code, 200)

    def test_pay_denies_inactive_owner_without_writes(self):
        self.as_actor(self.reception)
        target = get_user_model().objects.create_user(username='pay-inactive-owner')
        purchase = domain.Purchase.objects.create(
            owner=target.app_user, status=domain.PurchaseStatus.objects.get(code='PENDING'),
        )
        target.is_active = False
        target.save(update_fields=['is_active'])
        response = self.post_json(f'/api/services/purchases/{purchase.pk}/pay/', {})
        self.assertEqual(response.status_code, 404, response.data)
        purchase.refresh_from_db()
        self.assertEqual(purchase.status.code, 'PENDING')
        self.assertIsNone(purchase.purchased_at)
        self.assertFalse(domain.ServiceRequest.objects.exists())
        self.assertFalse(domain.ServiceStatusLog.objects.exists())

    def test_no_participant_remains_optional_and_paid_without_request_conflicts(self):
        self.as_actor(self.admin)
        purchase = domain.Purchase.objects.create(
            owner=self.owner.app_user, status=domain.PurchaseStatus.objects.get(code='PENDING'),
        )
        path = f'/api/services/purchases/{purchase.pk}/pay/'
        paid = self.post_json(path, {})
        self.assertEqual(paid.status_code, 200, paid.data)
        service = domain.ServiceRequest.objects.get(purchase=purchase)
        self.assertIsNone(service.participant_id)
        domain.ServiceStatusLog.objects.filter(request=service).delete()
        response = self.post_json(path, {})
        self.assertEqual(response.status_code, 409, response.data)
        self.assertEqual(domain.ServiceRequest.objects.filter(purchase=purchase).count(), 1)
        self.assertFalse(domain.ServiceStatusLog.objects.exists())

    def test_uniqueness_conflict_returns_409_without_partial_payment(self):
        self.as_actor(self.reception)
        purchase = domain.Purchase.objects.create(
            owner=self.owner.app_user, status=domain.PurchaseStatus.objects.get(code='PENDING'),
        )
        with patch('services.views.ServiceRequest.objects.create', side_effect=IntegrityError):
            response = self.post_json(f'/api/services/purchases/{purchase.pk}/pay/', {})
        self.assertEqual(response.status_code, 409, response.data)
        purchase.refresh_from_db()
        self.assertEqual(purchase.status.code, 'PENDING')
        self.assertIsNone(purchase.purchased_at)
        self.assertFalse(domain.ServiceRequest.objects.exists())
        self.assertFalse(domain.ServiceStatusLog.objects.exists())

    def test_missing_csrf_blocks_authenticated_write(self):
        self.as_actor(self.admin)
        self.client.cookies['csrftoken'] = 'different-csrf'
        response = self.client.post(
            '/api/services/purchases/', data=json.dumps({'userId': self.owner.pk}),
            content_type='application/json', HTTP_X_CSRFTOKEN='matching-csrf',
        )
        self.assertEqual(response.status_code, 403, response.data)
        self.assertEqual(domain.Purchase.objects.count(), 0)


class SampleReceptionTests(APITestCase):
    def setUp(self):
        users = get_user_model().objects
        self.admin = users.create_user(username='sample-admin')
        grant_admin_role(self.admin)
        self.reception = users.create_user(username='sample-reception')
        grant_reception_role(self.reception)
        self.owner = users.create_user(username='sample-owner')
        self.other = users.create_user(username='sample-other')
        self.purchase = domain.Purchase.objects.create(
            owner=self.owner.app_user, status=domain.PurchaseStatus.objects.get(code='PAID'),
            purchased_at=timezone.now(),
        )
        self.waiting = domain.ServiceStatus.objects.get(code='WAITING_SAMPLE')
        self.service = domain.ServiceRequest.objects.create(purchase=self.purchase, status=self.waiting)
        self.initial = domain.ServiceStatusLog.objects.create(
            request=self.service, status=self.waiting, actor=self.admin.app_user,
        )
        self.as_actor(self.admin)
        self.client.cookies['csrftoken'] = 'matching-csrf'

    def as_actor(self, user):
        if user is None:
            self.client.cookies.pop(settings.AUTH_COOKIE_NAME, None)
        else:
            self.client.cookies[settings.AUTH_COOKIE_NAME] = encode_jwt({'sub': str(user.pk)})

    def receive(self, service=None, payload=None):
        service = service or self.service
        self.client.cookies['csrftoken'] = 'matching-csrf'
        return self.client.post(
            f'/api/services/requests/{service.pk}/receive-sample/',
            data=json.dumps({} if payload is None else payload), content_type='application/json',
            HTTP_X_CSRFTOKEN='matching-csrf',
        )

    def assert_unchanged(self):
        self.service.refresh_from_db()
        self.assertEqual(self.service.status.code, 'WAITING_SAMPLE')
        self.assertEqual(list(domain.ServiceStatusLog.objects.filter(request=self.service).values_list(
            'pk', flat=True,
        )), [self.initial.pk])

    def test_explicit_paid_service_transitions_and_keeps_initial_history(self):
        response = self.receive()
        self.assertEqual(response.status_code, 200, getattr(response, 'data', None))
        self.service.refresh_from_db()
        self.assertEqual(self.service.status.code, 'SAMPLE_RECEIVED')
        history = list(domain.ServiceStatusLog.objects.filter(request=self.service).order_by('changed_at'))
        self.assertEqual([log.status.code for log in history], ['WAITING_SAMPLE', 'SAMPLE_RECEIVED'])
        self.assertEqual(history[0].pk, self.initial.pk)
        self.assertEqual(history[1].actor, self.admin.app_user)
        self.assertEqual(response.data, {
            'serviceRequestId': self.service.pk, 'status': 'SAMPLE_RECEIVED',
            'statusLogId': history[1].pk,
        })

    def test_empty_body_is_accepted(self):
        response = self.client.post(
            f'/api/services/requests/{self.service.pk}/receive-sample/',
            data='', content_type='application/json', HTTP_X_CSRFTOKEN='matching-csrf',
        )
        self.assertEqual(response.status_code, 200, getattr(response, 'data', None))
        self.assertEqual(response.data['status'], 'SAMPLE_RECEIVED')

    def test_reception_retry_uses_original_actor_and_log(self):
        self.as_actor(self.reception)
        first = self.receive()
        self.assertEqual(first.status_code, 200, getattr(first, 'data', None))
        self.as_actor(self.admin)
        second = self.receive()
        self.assertEqual(second.status_code, 200, second.data)
        self.assertEqual(second.data, first.data)
        self.assertEqual(domain.ServiceStatusLog.objects.filter(request=self.service).count(), 2)
        log = domain.ServiceStatusLog.objects.get(pk=first.data['statusLogId'])
        self.assertEqual(log.actor, self.reception.app_user)
        self.assertEqual(log.status.code, 'SAMPLE_RECEIVED')

    def test_waiting_service_without_payment_log_conflicts_without_writes(self):
        self.initial.delete()
        response = self.receive()
        self.assertEqual(response.status_code, 409, getattr(response, 'data', None))
        self.service.refresh_from_db()
        self.assertEqual(self.service.status.code, 'WAITING_SAMPLE')
        self.assertFalse(domain.ServiceStatusLog.objects.filter(request=self.service).exists())

    def test_received_retry_without_payment_log_conflicts_without_writes(self):
        first = self.receive()
        self.assertEqual(first.status_code, 200, getattr(first, 'data', None))
        self.initial.delete()
        response = self.receive()
        self.assertEqual(response.status_code, 409, getattr(response, 'data', None))
        self.service.refresh_from_db()
        self.assertEqual(self.service.status.code, 'SAMPLE_RECEIVED')
        self.assertEqual(list(domain.ServiceStatusLog.objects.filter(request=self.service).values_list(
            'pk', flat=True,
        )), [first.data['statusLogId']])

    def test_only_functional_staff_can_receive_even_with_django_flags(self):
        flagged = get_user_model().objects.create_user(
            username='sample-flagged', is_staff=True, is_superuser=True,
        )
        flagged.groups.add(Group.objects.get_or_create(name='RECEPCION')[0])
        analyst = get_user_model().objects.create_user(username='sample-analyst')
        AppUser.objects.filter(django_user=analyst).update(role=Role.objects.get(code='ANALISTA'))
        unmapped = get_user_model().objects.bulk_create(
            [get_user_model()(username='sample-unmapped')],
        )[0]
        for actor in (self.owner, self.other, analyst, flagged, unmapped, None):
            with self.subTest(actor=actor):
                self.as_actor(actor)
                response = self.receive()
                self.assertIn(response.status_code, (401, 403))
                self.assert_unchanged()

    def test_csrf_and_nonempty_or_forged_payloads_fail_without_writes(self):
        self.client.cookies['csrftoken'] = 'different-csrf'
        self.assertEqual(self.client.post(
            f'/api/services/requests/{self.service.pk}/receive-sample/',
            data='{}', content_type='application/json', HTTP_X_CSRFTOKEN='matching-csrf',
        ).status_code, 403)
        for payload in (
            {'actor': str(self.reception.app_user.pk)}, {'owner': str(self.other.app_user.pk)},
            {'userId': self.owner.pk}, {'status': 'PROCESSING'}, {'status': 'COMPLETED'},
            {'status': 'SAMPLE_RECEIVED'}, {'action': 'receive'}, {'comment': 'note'},
            [], None, 'SAMPLE_RECEIVED',
        ):
            with self.subTest(payload=payload):
                self.client.cookies['csrftoken'] = 'matching-csrf'
                response = self.client.post(
                    f'/api/services/requests/{self.service.pk}/receive-sample/',
                    data=json.dumps(payload), content_type='application/json',
                    HTTP_X_CSRFTOKEN='matching-csrf',
                )
                self.assertEqual(response.status_code, 400, getattr(response, 'data', None))
                self.assert_unchanged()

    def test_missing_csrf_cookie_or_header_blocks_receive(self):
        self.client.cookies.pop('csrftoken', None)
        self.assertEqual(self.client.post(
            f'/api/services/requests/{self.service.pk}/receive-sample/',
            data='{}', content_type='application/json', HTTP_X_CSRFTOKEN='matching-csrf',
        ).status_code, 403)
        self.client.cookies['csrftoken'] = 'matching-csrf'
        self.assertEqual(self.client.post(
            f'/api/services/requests/{self.service.pk}/receive-sample/',
            data='{}', content_type='application/json',
        ).status_code, 403)
        self.assert_unchanged()

    def test_selects_only_one_of_two_paid_services_for_same_owner(self):
        another_purchase = domain.Purchase.objects.create(
            owner=self.owner.app_user, status=self.purchase.status, purchased_at=timezone.now(),
        )
        another = domain.ServiceRequest.objects.create(purchase=another_purchase, status=self.waiting)
        another_initial = domain.ServiceStatusLog.objects.create(
            request=another, status=self.waiting, actor=self.admin.app_user,
        )
        self.as_actor(self.reception)
        result = self.receive(another)
        self.assertEqual(result.status_code, 200, getattr(result, 'data', None))
        self.assertEqual(result.data['serviceRequestId'], another.pk)
        self.assert_unchanged()
        another.refresh_from_db()
        self.assertEqual(another.status.code, 'SAMPLE_RECEIVED')
        self.assertEqual(domain.ServiceStatusLog.objects.filter(request=another).count(), 2)
        self.assertTrue(domain.ServiceStatusLog.objects.filter(pk=another_initial.pk).exists())

    def test_missing_or_ineligible_owner_returns_404(self):
        self.assertEqual(self.receive(SimpleNamespace(pk=uuid.uuid4())).status_code, 404)
        self.assertEqual(self.client.post(
            '/api/services/requests/not-a-uuid/receive-sample/',
            data='{}', content_type='application/json', HTTP_X_CSRFTOKEN='matching-csrf',
        ).status_code, 404)
        for change in ('inactive', 'analyst'):
            with self.subTest(change=change):
                if change == 'inactive':
                    self.owner.is_active = False
                    self.owner.save(update_fields=['is_active'])
                else:
                    self.owner.is_active = True
                    self.owner.save(update_fields=['is_active'])
                    AppUser.objects.filter(pk=self.owner.app_user.pk).update(
                        role=Role.objects.get(code='ANALISTA'),
                    )
                self.assertEqual(self.receive().status_code, 404)
                self.assert_unchanged()

    def test_reassigned_purchase_cannot_receive_another_clients_participant(self):
        participant = Participant.objects.create(user=self.other, participant_code='other-sample')
        domain.ServiceRequest.objects.filter(pk=self.service.pk).update(participant=participant)
        self.assertEqual(self.receive().status_code, 404)
        self.assert_unchanged()

    def test_unpaid_or_incomplete_purchase_returns_409(self):
        for code in ('PENDING', 'CANCELLED', 'REFUNDED', None):
            with self.subTest(code=code):
                self.purchase.status = domain.PurchaseStatus.objects.get(code=code) if code else None
                self.purchase.save(update_fields=['status'])
                self.assertEqual(self.receive().status_code, 409)
                self.assert_unchanged()
        self.purchase.status = domain.PurchaseStatus.objects.get(code='PAID')
        self.purchase.purchased_at = None
        self.purchase.save(update_fields=['status', 'purchased_at'])
        self.assertEqual(self.receive().status_code, 409)
        self.assert_unchanged()

    def test_out_of_order_states_and_missing_received_log_conflict(self):
        for code in ('PROCESSING', 'COMPLETED', 'SAMPLE_RECEIVED'):
            with self.subTest(code=code):
                self.service.status = domain.ServiceStatus.objects.get(code=code)
                self.service.save(update_fields=['status'])
                self.assertEqual(self.receive().status_code, 409)
                self.assertEqual(domain.ServiceStatusLog.objects.filter(request=self.service).count(), 1)
                self.assertTrue(domain.ServiceStatusLog.objects.filter(pk=self.initial.pk).exists())

    def test_lock_and_log_failure_roll_back_status_for_retry(self):
        savepoints = len(connection.savepoint_ids)

        def fail_log(*args, **kwargs):
            self.assertTrue(connection.in_atomic_block)
            self.assertGreater(len(connection.savepoint_ids), savepoints)
            raise RuntimeError('simulated reception log failure')

        with CaptureQueriesContext(connection) as queries:
            with patch('services.views.ServiceStatusLog.objects.create', side_effect=fail_log):
                with self.assertRaisesMessage(RuntimeError, 'simulated reception log failure'):
                    self.receive()
        self.assertTrue(any('FOR UPDATE' in q['sql'] and '"service_request"' in q['sql']
                            for q in queries.captured_queries))
        self.assert_unchanged()
        self.assertEqual(self.receive().status_code, 200)
