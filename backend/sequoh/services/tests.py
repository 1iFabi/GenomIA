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
from importlib import import_module
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, transaction
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
