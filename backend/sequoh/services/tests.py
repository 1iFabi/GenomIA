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
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from importlib import import_module
from threading import Barrier
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, connections, transaction
from django.db.migrations.loader import MigrationLoader
from django.db.models.deletion import PROTECT, ProtectedError
from django.test import TestCase
from django.utils import timezone

from services import models as domain


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
