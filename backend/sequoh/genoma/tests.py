import hashlib
import json
import os
import uuid
from copy import deepcopy
from dataclasses import replace
from io import StringIO
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, contextmanager
from datetime import timedelta
from decimal import Decimal
from importlib import import_module, reload
from threading import Barrier
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

from django.apps import apps
from django.conf import settings
from django.contrib import admin
from django.contrib.auth.models import Group, User
from django.contrib.postgres.functions import TransactionNow
from django.core.exceptions import ValidationError
from django.core.management import call_command, get_commands
from django.core.management.base import CommandError
from django.db import DataError, DatabaseError, IntegrityError, connection, connections, models, transaction
from django.db.migrations import CreateModel, DeleteModel, RunPython
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.loader import MigrationLoader
from django.db.migrations.recorder import MigrationRecorder
from django.db.models.deletion import CASCADE, PROTECT, RESTRICT, SET_NULL, ProtectedError, RestrictedError
from django.test import SimpleTestCase, TestCase, TransactionTestCase
from django.test.utils import CaptureQueriesContext
from django.urls import NoReverseMatch, Resolver404, resolve, reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.jwt_utils import encode_jwt
from accounts.models import AppUser, Role
from accounts.roles import grant_admin_role, grant_analyst_role, grant_reception_role
from genoma import models as domain, synthetic_import as bundle
from participants.models import Participant
from profiles.models import Profile
from services.status import ClientStatus
from services.models import (
    Purchase, PurchaseStatus, Sample, ServiceRequest, ServiceStatus as RequestStatus,
    ServiceStatusLog,
)


NORMALIZED_CHAIN = tuple(('genoma', name) for name in (
    '0001_initial', '0002_data_release', '0003_analysis_release', '0004_variant',
    '0005_variant_placement', '0006_external_identifier', '0007_population',
    '0008_epigenetic_feature', '0009_variant_annotation', '0010_allele_frequency',
    '0011_release_variant', '0012_release_epigenetic_feature', '0013_genotype',
    '0014_artifact', '0015_analysis_result',
))
NORMALIZED_INITIAL = NORMALIZED_CHAIN[0]
NORMALIZED_LEAF = NORMALIZED_CHAIN[-1]
NORMALIZED_DEPENDENCIES = [
    ('participants', '0003_participant_metadata_support'), ('services', '0004_sample'),
]
NORMALIZED_TABLE_MIGRATIONS = {
    'Analysis': NORMALIZED_CHAIN[0], 'DataRelease': NORMALIZED_CHAIN[1],
    'Variant': NORMALIZED_CHAIN[3], 'VariantPlacement': NORMALIZED_CHAIN[4],
    'ExternalIdentifier': NORMALIZED_CHAIN[5], 'Population': NORMALIZED_CHAIN[6],
    'EpigeneticFeature': NORMALIZED_CHAIN[7], 'VariantAnnotation': NORMALIZED_CHAIN[8],
    'AlleleFrequency': NORMALIZED_CHAIN[9], 'ReleaseVariant': NORMALIZED_CHAIN[10],
    'ReleaseEpigeneticFeature': NORMALIZED_CHAIN[11], 'Genotype': NORMALIZED_CHAIN[12],
    'Artifact': NORMALIZED_CHAIN[13], 'AnalysisResult': NORMALIZED_CHAIN[14],
}


def normalized_dependencies(model_name):
    position = NORMALIZED_CHAIN.index(NORMALIZED_TABLE_MIGRATIONS[model_name])
    return NORMALIZED_DEPENDENCIES if position == 0 else [NORMALIZED_CHAIN[position - 1]]


def normalized_migration_slice(model_name):
    """Exercise the model's actual table migration and its ordered FK operations."""
    key = NORMALIZED_TABLE_MIGRATIONS[model_name]
    module = import_module(f'genoma.migrations.{key[1]}')
    return module.Migration(*reversed(key))


def normalized_state_before(model_name):
    loader = MigrationLoader(connection)
    migration = loader.disk_migrations[NORMALIZED_TABLE_MIGRATIONS[model_name]]
    return loader.project_state(migration.dependencies)


class RetiredLegacySNPSchemaTests(TestCase):
    legacy_models = ('UserSNP', 'SNP', 'RsidExtraInfo', 'PharmacogeneticSystem')
    legacy_tables = {'user_snps', 'snps', 'rsid_extra_info', 'genetics_pharmacogeneticsystem'}
    normalized_tables = {
        'Analysis': 'analysis', 'AnalysisResult': 'analysis_result', 'DataRelease': 'data_release',
        'Variant': 'variant', 'VariantPlacement': 'variant_placement',
        'ExternalIdentifier': 'external_identifier', 'Population': 'population',
        'EpigeneticFeature': 'epigenetic_feature', 'VariantAnnotation': 'variant_annotation',
        'AlleleFrequency': 'allele_frequency', 'ReleaseVariant': 'release_variant',
        'ReleaseEpigeneticFeature': 'release_epigenetic_feature', 'Genotype': 'genotype',
        'Artifact': 'artifact',
    }

    def setUp(self):
        self.assertTrue(connection.settings_dict['NAME'].startswith('gdb_test_'))

    def test_legacy_classes_are_absent_from_module_and_app_registry(self):
        for name in self.legacy_models:
            with self.subTest(model=name):
                self.assertFalse(hasattr(domain, name))
                with self.assertRaises(LookupError):
                    apps.get_model('genoma', name)

    def test_only_normalized_genoma_models_remain(self):
        self.assertEqual(
            {model.__name__ for model in apps.get_app_config('genoma').get_models()},
            set(self.normalized_tables),
        )
        for name, table in self.normalized_tables.items():
            with self.subTest(model=name):
                self.assertEqual(getattr(domain, name)._meta.db_table, table)

    def test_only_normalized_genoma_tables_remain(self):
        with connection.cursor() as cursor:
            tables = set(connection.introspection.table_names(cursor))
        self.assertTrue(set(self.normalized_tables.values()) <= tables)
        self.assertTrue({User._meta.db_table, Profile._meta.db_table, 'purchase',
                         'service_request', 'sample', 'participant'} <= tables)
        self.assertFalse(self.legacy_tables & tables)


class GenomaAppContractTests(SimpleTestCase):
    package_path = Path(__file__).resolve().parents[1] / 'genoma'
    initial = ('genoma', '0001_initial')
    normalized_tables = RetiredLegacySNPSchemaTests.normalized_tables

    def test_registered_app_uses_genoma_label_module_and_package_path(self):
        self.assertIn('genoma', apps.app_configs, 'The normalized app must be registered as genoma')
        config = apps.get_app_config('genoma')
        self.assertEqual((config.name, config.label), ('genoma', 'genoma'))
        self.assertEqual(type(config).__module__, 'genoma.apps')
        self.assertEqual(type(config).__name__, 'GenomaConfig')
        self.assertEqual(Path(config.path).resolve(), self.package_path)
        self.assertNotIn('genetics', apps.app_configs)

    def test_domain_and_synthetic_bundle_modules_belong_to_genoma(self):
        for module, expected in ((domain, 'genoma.models'), (bundle, 'genoma.synthetic_import')):
            with self.subTest(module=expected):
                self.assertEqual(module.__name__, expected)
                self.assertEqual(Path(module.__file__).resolve().parent, self.package_path)

    def test_genoma_package_and_normalized_migration_chain_exist(self):
        for relative in ('__init__.py', 'apps.py', 'models.py', 'migrations/__init__.py',
                         'migrations/0001_initial.py'):
            with self.subTest(path=relative):
                self.assertTrue((self.package_path / relative).is_file(),
                                f'Expected genoma package file: {relative}')
        migration_path = self.package_path / 'migrations'
        self.assertTrue(migration_path.is_dir(), 'Expected the genoma migration package')
        self.assertEqual({path.name for path in migration_path.glob('*.py')},
                         {'__init__.py'} | {f'{name}.py' for _, name in NORMALIZED_CHAIN})

    def test_normalized_chain_has_no_legacy_history_or_models(self):
        self.assertTrue((self.package_path / 'migrations' / '0001_initial.py').is_file(),
                        'Expected genoma.0001_initial before migration state can be inspected')
        self.assertIn('genoma', apps.app_configs, 'Expected an installed genoma app')
        loader = MigrationLoader(None, replace_migrations=False)
        self.assertEqual({key for key in loader.disk_migrations if key[0] == 'genoma'}, set(NORMALIZED_CHAIN))
        self.assertFalse(any(key[0] == 'genetics' for key in loader.disk_migrations))
        self.assertTrue(loader.disk_migrations[self.initial].initial)
        chain = [loader.disk_migrations[key] for key in NORMALIZED_CHAIN]
        self.assertTrue(all(migration.replaces == [] for migration in chain))
        operations = [operation for migration in chain for operation in migration.operations]
        created = [operation for operation in operations if isinstance(operation, CreateModel)]
        self.assertEqual(len(created), 14)
        self.assertEqual({operation.name: operation.options.get('db_table') for operation in created},
                         self.normalized_tables)
        self.assertFalse(any(isinstance(operation, DeleteModel) for operation in operations))
        self.assertEqual(loader.graph.leaf_nodes('genoma'), [NORMALIZED_LEAF])
        self.assertFalse(loader.detect_conflicts())
        state = loader.project_state([NORMALIZED_LEAF])
        self.assertEqual({name: model.options.get('db_table')
                          for (label, name), model in state.models.items() if label == 'genoma'},
                         {name.lower(): table for name, table in self.normalized_tables.items()})
        self.assertFalse(any(label == 'genetics' for label, _ in state.models))

    def test_exactly_fourteen_normalized_models_keep_their_unprefixed_tables(self):
        self.assertIn('genoma', apps.app_configs, 'Expected normalized models under the genoma label')
        registered = list(apps.get_app_config('genoma').get_models())
        self.assertEqual(len(registered), 14)
        self.assertEqual({model._meta.label: model._meta.db_table for model in registered},
                         {f'genoma.{name}': table for name, table in self.normalized_tables.items()})
        self.assertFalse({model.__name__ for model in registered}
                         & set(RetiredLegacySNPSchemaTests.legacy_models))
        for name in self.normalized_tables:
            with self.subTest(model=name):
                self.assertIs(apps.get_model('genoma', name), getattr(domain, name))

    def test_synthetic_bundle_resolves_the_fixture_from_genoma(self):
        fixture_path = self.package_path / 'fixtures' / 'synthetic_genomics_v2.json'
        self.assertTrue(fixture_path.is_file(), 'Expected the bundled synthetic fixture in genoma')
        self.assertEqual(Path(bundle.__file__).resolve().parent / 'fixtures' / fixture_path.name,
                         fixture_path)
        self.assertEqual(bundle.get_synthetic_bundle('2').manifest,
                         json.loads(fixture_path.read_text(encoding='utf-8')))
        self.assertEqual(bundle.get_synthetic_bundle('2').manifest_checksum, bundle.V2_MANIFEST_CHECKSUM)
        self.assertEqual(bundle.get_synthetic_bundle('1').manifest_checksum, bundle.MANIFEST_CHECKSUM)

    def test_catalog_fixture_labels_deserialize_to_genoma_models_without_queries(self):
        from django.core import serializers

        fixture_path = self.package_path / 'fixtures' / 'synthetic_variant_catalog_v1.json'
        self.assertTrue(fixture_path.is_file(), 'Expected the normalized catalog fixture in genoma')
        serialized = fixture_path.read_text(encoding='utf-8')
        rows = json.loads(serialized)
        expected_counts = {'genoma.datarelease': 1, 'genoma.variant': 8,
                           'genoma.variantplacement': 8, 'genoma.releasevariant': 8}
        self.assertEqual({row['model'] for row in rows}, set(expected_counts))
        self.assertEqual({label: sum(row['model'] == label for row in rows)
                          for label in expected_counts}, expected_counts)
        self.assertIn('genoma', apps.app_configs, 'Expected genoma fixture labels to resolve')
        registered = apps.get_app_config('genoma').models
        for label in expected_counts:
            self.assertIn(label.split('.')[1], registered, f'Expected registered fixture model: {label}')
        objects = list(serializers.deserialize('json', serialized))
        self.assertEqual(len(objects), 25)
        self.assertEqual({obj.object._meta.label_lower for obj in objects}, set(expected_counts))


class GenomaPerTableMigrationLayoutTests(SimpleTestCase):
    def test_normalized_tables_have_separate_unsquashed_acyclic_migrations(self):
        loader = MigrationLoader(None, replace_migrations=False)
        migrations = {key: migration for key, migration in loader.disk_migrations.items()
                      if key[0] == 'genoma'}
        creations = {key: [operation for operation in migration.operations
                           if isinstance(operation, CreateModel)]
                     for key, migration in migrations.items()}
        created = [operation for operations in creations.values() for operation in operations]
        self.assertEqual(len(created), 14)
        self.assertEqual({operation.options.get('db_table') for operation in created}, {
            'analysis', 'analysis_result', 'data_release', 'variant', 'variant_placement',
            'external_identifier', 'population', 'epigenetic_feature', 'variant_annotation',
            'allele_frequency', 'release_variant', 'release_epigenetic_feature', 'genotype',
            'artifact',
        })
        migration_path = Path(__file__).resolve().parent / 'migrations'
        self.assertFalse([path.name for path in migration_path.glob('*.py')
                          if 'squash' in path.stem.lower()], 'Squash migration files are not allowed')
        self.assertFalse([key for key, migration in migrations.items() if migration.replaces],
                         'Genoma migrations must not replace or squash migration history')
        loader.graph.ensure_not_cyclic()
        for key, operations in creations.items():
            with self.subTest(migration=key):
                self.assertLessEqual(len(operations), 1,
                                     f'{key[0]}.{key[1]} creates multiple tables; '
                                     'each migration must contain at most one CreateModel')


class NormalizedInitialMigrationTests(TestCase):
    initial = NORMALIZED_INITIAL
    leaf = NORMALIZED_LEAF
    legacy_tables = RetiredLegacySNPSchemaTests.legacy_tables
    normalized_tables = RetiredLegacySNPSchemaTests.normalized_tables

    def setUp(self):
        self.assertEqual(connection.vendor, 'postgresql')
        self.assertTrue(connection.settings_dict['NAME'].startswith('gdb_test_'))
        self.assertTrue(connection.in_atomic_block, 'DDL and ledger changes must roll back with TestCase')
        with connection.cursor() as cursor:
            cursor.execute('SELECT current_database()')
            self.assertEqual(cursor.fetchone()[0], connection.settings_dict['NAME'])
        self.assertIn(self.initial, MigrationLoader(connection).disk_migrations,
                      'Normalized initial migration is required')
        self.user = User.objects.create_user(username='squash-preserved-owner')
        Profile.objects.create(user=self.user, phone='SQUASH')
        self.preserved_models = (User, AppUser, Role, Group, Profile, Participant,
                                 Purchase, ServiceRequest, Sample)

    def tables(self):
        with connection.cursor() as cursor:
            return set(connection.introspection.table_names(cursor))

    def ledger(self):
        return set(MigrationRecorder(connection).applied_migrations())

    def preserved_rows(self):
        return {model._meta.label: list(model.objects.order_by('pk').values())
                for model in self.preserved_models}

    def normalized_rows(self, state):
        return {name: list(state.apps.get_model('genoma', name).objects.order_by('pk').values())
                for name in self.normalized_tables if ('genoma', name.lower()) in state.models}

    def empty_genoma(self):
        # Only the disposable DB is changed; TestCase rolls back schema AND ledger.
        connection.check_constraints()
        executor = MigrationExecutor(connection)
        plan = executor.migration_plan([('genoma', None)])
        self.assertEqual([(migration.app_label, migration.name, backwards)
                          for migration, backwards in plan], [(*key, True) for key in reversed(NORMALIZED_CHAIN)])
        executor.migrate([('genoma', None)], plan=plan)
        self.assertFalse(set(self.normalized_tables.values()) & self.tables())
        self.assertFalse(self.legacy_tables & self.tables())
        self.assertFalse({key for key in self.ledger() if key[0] == 'genoma'})

    def schema_catalog(self):
        catalog = {}
        with connection.cursor() as cursor:
            for table in self.normalized_tables.values():
                cursor.execute(
                    'SELECT a.attname, format_type(a.atttypid, a.atttypmod), a.attnotnull, '
                    'pg_get_expr(d.adbin, d.adrelid) FROM pg_attribute a '
                    'LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum '
                    'WHERE a.attrelid = %s::regclass AND a.attnum > 0 AND NOT a.attisdropped '
                    'ORDER BY a.attnum', [table],
                )
                columns = cursor.fetchall()
                cursor.execute(
                    'SELECT conname, contype, pg_get_constraintdef(oid), confdeltype, '
                    'confupdtype, condeferrable, condeferred FROM pg_constraint '
                    'WHERE conrelid = %s::regclass ORDER BY conname', [table],
                )
                constraints = cursor.fetchall()
                cursor.execute('SELECT indexname, indexdef FROM pg_indexes '
                               'WHERE schemaname = current_schema() AND tablename = %s '
                               'ORDER BY indexname', [table])
                catalog[table] = (columns, constraints, cursor.fetchall())
        return catalog

    def assert_retirement_sql(self, queries, expected):
        drops = [query['sql'] for query in queries.captured_queries
                 if query['sql'].lstrip().upper().startswith('DROP TABLE')]
        self.assertEqual(len(drops), len(expected), drops)
        self.assertEqual({sql.split('"')[1] for sql in drops}, expected)

    def seed_complete_normalized_graph(self):
        participant = Participant.objects.create(user=self.user, participant_code='squash-participant')
        purchase = Purchase.objects.create(owner=self.user.app_user)
        request = ServiceRequest.objects.create(
            purchase=purchase, participant=participant,
            status=RequestStatus.objects.get(code='WAITING_SAMPLE'),
        )
        sample = Sample.objects.create(
            service_request=request, participant=participant,
            sample_code='squash-sample', sample_type='synthetic',
        )
        release = domain.DataRelease.objects.create(
            name='squash-release', version='1', status='unlisted', reference_assembly='synthetic',
        )
        analysis = domain.Analysis.objects.create(
            participant=participant, sample=sample, service_request=request, release=release,
            module='synthetic', pipeline_name='synthetic', pipeline_version='1', status='unlisted',
        )
        variant = domain.Variant.objects.create(variant_type='synthetic')
        placement = domain.VariantPlacement.objects.create(
            variant=variant, reference_assembly='synthetic', contig='1', start_pos=1, end_pos=1,
        )
        domain.ExternalIdentifier.objects.create(variant=variant, namespace='synthetic', accession='1')
        population = domain.Population.objects.create(code='squash-population', name='Synthetic')
        feature = domain.EpigeneticFeature.objects.create(
            feature_type='synthetic', reference_assembly='synthetic', contig='1', start_pos=1, end_pos=1,
        )
        domain.VariantAnnotation.objects.create(
            variant=variant, placement=placement, analysis=analysis,
            source_name='synthetic', source_version='1', annotation_type='synthetic',
        )
        domain.AlleleFrequency.objects.create(
            release=release, variant=variant, population=population, analysis=analysis,
            source_name='synthetic', source_version='1', allele='A',
        )
        domain.ReleaseVariant.objects.create(
            release=release, variant=variant, placement=placement, included_by_analysis=analysis,
        )
        domain.ReleaseEpigeneticFeature.objects.create(
            release=release, epigenetic_feature=feature, included_by_analysis=analysis,
        )
        domain.Genotype.objects.create(
            release=release, variant=variant, participant=participant,
            sample=sample, analysis=analysis, genotype='AA',
        )
        domain.Artifact.objects.create(
            analysis=analysis, release=release, sample=sample, role='synthetic',
            artifact_type='synthetic', format='txt', uri='object://synthetic', checksum_sha256='0' * 64,
        )
        domain.AnalysisResult.objects.create(
            analysis=analysis, participant=participant, sample=sample, release=release,
            variant=variant, epigenetic_feature=feature, population=population,
            module='synthetic', result_type='synthetic',
        )

    def test_initial_dependencies_and_only_normalized_state(self):
        loader = MigrationLoader(connection)
        migration = loader.disk_migrations[self.initial]
        self.assertTrue(migration.initial)
        self.assertEqual(migration.replaces, [])
        self.assertEqual(migration.dependencies, [
            ('participants', '0003_participant_metadata_support'), ('services', '0004_sample'),
        ])
        self.assertEqual([operation.name for operation in migration.operations
                          if isinstance(operation, CreateModel)], ['Analysis'])
        self.assertNotIn('release', dict(migration.operations[0].fields))
        created = {}
        for position, key in enumerate(NORMALIZED_CHAIN):
            migration = loader.disk_migrations[key]
            with self.subTest(migration=key):
                expected = NORMALIZED_DEPENDENCIES if position == 0 else [NORMALIZED_CHAIN[position - 1]]
                self.assertEqual(migration.dependencies, expected)
                self.assertEqual(migration.replaces, [])
                self.assertFalse(any(isinstance(operation, DeleteModel) for operation in migration.operations))
                self.assertTrue(all(operation.reversible for operation in migration.operations))
                for operation in migration.operations:
                    if isinstance(operation, CreateModel):
                        created[operation.name] = key
                    if isinstance(operation, RunPython):
                        module = f'genoma.migrations.{key[1]}'
                        self.assertEqual(operation.code.__module__, module)
                        self.assertIn(operation.reverse_code.__module__,
                                      (module, 'django.db.migrations.operations.special'))
        self.assertEqual(created, NORMALIZED_TABLE_MIGRATIONS)
        self.assertEqual(loader.graph.leaf_nodes('genoma'), [self.leaf])
        self.assertEqual({key for key in loader.graph.nodes if key[0] == 'genoma'}, set(NORMALIZED_CHAIN))
        self.assertFalse(loader.detect_conflicts())
        loader.check_consistent_history(connection)

    def test_fresh_plan_executes_only_normalized_chain_and_preserves_other_apps(self):
        self.empty_genoma()
        preserved = self.preserved_rows()
        other_ledger = {key for key in self.ledger() if key[0] != 'genoma'}
        tables = self.tables()
        executor = MigrationExecutor(connection)
        plan = executor.migration_plan([self.leaf])
        self.assertEqual([(migration.app_label, migration.name, backwards)
                          for migration, backwards in plan], [(*key, False) for key in NORMALIZED_CHAIN])
        with CaptureQueriesContext(connection) as queries:
            state = executor.migrate([self.leaf], plan=plan)
        self.assert_retirement_sql(queries, set())
        creates = [query['sql'] for query in queries.captured_queries
                   if query['sql'].lstrip().upper().startswith('CREATE TABLE')]
        self.assertEqual({sql.split('"')[1] for sql in creates}, set(self.normalized_tables.values()))
        self.assertEqual(self.tables() - tables, set(self.normalized_tables.values()))
        self.assertFalse(self.legacy_tables & self.tables())
        self.assertEqual(self.ledger(), other_ledger | set(NORMALIZED_CHAIN))
        self.assertEqual(self.preserved_rows(), preserved)
        catalog = self.schema_catalog()
        self.assertEqual(state.models, MigrationLoader(connection).project_state().models)
        self.empty_genoma()
        MigrationExecutor(connection).migrate([self.leaf])
        self.assertEqual(self.schema_catalog(), catalog)
        self.assertEqual(self.preserved_rows(), preserved)

    def test_applied_chain_is_a_noop_for_schema_ledger_and_populated_graph(self):
        self.seed_complete_normalized_graph()
        state = MigrationLoader(connection).project_state([self.leaf])
        before, preserved, catalog, ledger = (
            self.normalized_rows(state), self.preserved_rows(), self.schema_catalog(), self.ledger(),
        )
        self.assertTrue(all(len(rows) == 1 for rows in before.values()))
        executor = MigrationExecutor(connection)
        self.assertEqual(executor.migration_plan([self.leaf]), [])
        with CaptureQueriesContext(connection) as queries:
            executor.migrate([self.leaf])
        self.assertFalse(any(query['sql'].lstrip().upper().startswith(
            ('CREATE', 'ALTER', 'DROP', 'INSERT', 'UPDATE', 'DELETE')) for query in queries.captured_queries))
        self.assertEqual(self.ledger(), ledger)
        self.assertEqual(self.schema_catalog(), catalog)
        self.assertEqual(self.preserved_rows(), preserved)
        self.assertEqual(self.normalized_rows(MigrationLoader(connection).project_state([self.leaf])), before)


class RetiredLegacySNPOperatorCommandTests(SimpleTestCase):
    legacy_commands = (
        'analyze_snps_db', 'assign_snps', 'enrich_variants', 'export_all_snps',
        'import_snps', 'load_genomic_data', 'massive_enrichment', 'normalize_names',
        'populate_pharmacogenetic_systems', 'populate_trait_groups', 'refresh_rsid_extra_info',
    )

    def test_legacy_snp_commands_are_not_registered(self):
        commands = get_commands()
        registered = [name for name in self.legacy_commands if name in commands]
        self.assertFalse(registered, f'Legacy SNP commands still registered: {", ".join(registered)}')

    def test_normalized_synthetic_import_command_remains_registered(self):
        self.assertIn('import_synthetic_genomics', get_commands())


class RetiredSNPCatalogRouteTests(SimpleTestCase):
    url = '/api/genetics/variantes/'

    def test_catalog_url_no_longer_resolves(self):
        with self.assertRaises(Resolver404):
            resolve(self.url)

    def test_anonymous_catalog_requests_return_404_without_queries(self):
        with self.settings(DEBUG=False):
            for method in ('get', 'head', 'post'):
                with self.subTest(method=method):
                    self.assertEqual(getattr(self.client, method)(self.url).status_code, 404)

    def test_django_admin_unregisters_all_legacy_snp_models(self):
        registered = {model.__name__ for model in admin.site._registry if model._meta.app_label == 'genoma'}
        self.assertFalse(registered & set(RetiredLegacySNPSchemaTests.legacy_models))


class RetiredSNPCatalogAuthenticatedTests(APITestCase):
    def test_catalog_reads_and_writes_return_404_without_touching_normalized_rows(self):
        self.assertTrue(connection.settings_dict['NAME'].startswith('gdb_test_'))
        domain.Variant.objects.create(variant_type='synthetic', canonical_name='Preserved normalized row')
        before = list(domain.Variant.objects.values())
        for role, grant in (('client', None), ('admin', grant_admin_role),
                            ('analyst', grant_analyst_role), ('reception', grant_reception_role)):
            user = User.objects.create_user(username=f'retired-catalog-{role}')
            if grant:
                grant(user)
            self.client.cookies[settings.AUTH_COOKIE_NAME] = encode_jwt({'sub': str(user.pk)})
            self.client.cookies['csrftoken'] = 'catalog-csrf'
            for method in ('get', 'head', 'post'):
                with self.subTest(role=role, method=method), self.assertNumQueries(0):
                    response = getattr(self.client, method)(
                        RetiredSNPCatalogRouteTests.url,
                        **({'data': {'rsid': 'rs-new-catalog', 'genotipo': 'AA', 'fenotipo': 'Not stored'},
                            'format': 'json', 'HTTP_X_CSRFTOKEN': 'catalog-csrf'} if method == 'post' else {}),
                    )
                    self.assertEqual(response.status_code, 404)
        self.assertEqual(list(domain.Variant.objects.values()), before)


class RetiredPatientVariantsRouteTests(SimpleTestCase):
    def test_patient_variant_reader_url_no_longer_resolves(self):
        for user_id in (1, 42, 999999):
            with self.subTest(user_id=user_id), self.assertRaises(Resolver404):
                resolve(f'/api/genetics/patient-variants/{user_id}/')

    def test_patient_variant_reader_requests_return_not_found(self):
        with self.settings(DEBUG=False):
            for method in ('get', 'head', 'post'):
                with self.subTest(method=method):
                    response = getattr(self.client, method)('/api/genetics/patient-variants/42/')
                    self.assertEqual(response.status_code, 404)


class RetiredBiomarkerPanelRouteTests(SimpleTestCase):
    paths = ('/api/genetics/biomarkers/', '/api/genetics/biometrics/')

    def test_legacy_panel_urls_no_longer_resolve(self):
        for path in self.paths:
            with self.subTest(path=path), self.assertRaises(Resolver404):
                resolve(path)

    def test_legacy_panel_get_requests_return_not_found(self):
        with self.settings(DEBUG=False):
            for path in self.paths:
                with self.subTest(path=path):
                    self.assertEqual(self.client.get(path).status_code, 404)


class RetiredBiomarkerPanelAuthenticatedTests(APITestCase):
    def test_legacy_panel_gets_return_404_for_every_retired_role(self):
        self.assertTrue(connection.settings_dict['NAME'].startswith('gdb_test_'))
        for role, grant in (('client', None), ('admin', grant_admin_role), ('analyst', grant_analyst_role)):
            user = User.objects.create_user(username=f'retired-panel-{role}')
            if grant:
                grant(user)
            self.client.force_authenticate(user=user)
            for path in RetiredBiomarkerPanelRouteTests.paths:
                with self.subTest(role=role, path=path), self.assertNumQueries(0):
                    self.assertEqual(self.client.get(path).status_code, 404)


class RetiredLegacyGeneticsRouteTests(SimpleTestCase):
    routes = (
        ('/api/genetics/diseases/', 'api_diseases'),
        ('/api/genetics/ancestry/', 'api_ancestry'),
        ('/api/genetics/indigenous/', 'api_indigenous'),
        ('/api/genetics/traits/', 'api_traits'),
        ('/api/genetics/pharmacogenetics/', 'api_pharmacogenetics'),
        ('/api/ingest/upload-genetic-file/', 'api_upload_genetic_file'),
        ('/api/ingest/delete-genetic-file/', 'api_delete_genetic_file'),
        ('/api/ingest/user-report-status/42/', 'api_user_report_status'),
    )
    methods = ('get', 'head', 'post', 'put', 'patch', 'delete')

    def test_legacy_urls_no_longer_resolve(self):
        for path, _ in self.routes:
            with self.subTest(path=path), self.assertRaises(Resolver404):
                resolve(path)

    def test_legacy_url_names_are_retired(self):
        for _, name in self.routes:
            kwargs = {'user_id': 42} if name == 'api_user_report_status' else None
            with self.subTest(name=name), self.assertRaises(NoReverseMatch):
                reverse(name, kwargs=kwargs)

    def test_anonymous_requests_return_404_without_queries(self):
        with self.settings(DEBUG=False):
            for path, _ in self.routes:
                for method in self.methods:
                    with self.subTest(path=path, method=method):
                        self.assertEqual(getattr(self.client, method)(path).status_code, 404)

    def test_normalized_service_and_pdf_urls_still_resolve(self):
        service_id = uuid.uuid4()
        for path, name in (
            ('/api/genoma/v1/services/', 'api_genoma_v1_services'),
            (f'/api/genoma/v1/services/{service_id}/results/', 'api_genoma_v1_service_results'),
            (f'/api/genoma/v1/services/{service_id}/metrics/', 'api_genoma_v1_service_metrics'),
        ):
            with self.subTest(path=path):
                self.assertEqual(resolve(path).view_name, name)


class GenomaRouteContractTests(SimpleTestCase):
    service_id = '00000000-0000-4000-8000-000000000042'
    service_routes = (
        ('services/', 'SyntheticServiceListAPIView'),
        (f'services/{service_id}/results/', 'SyntheticServiceResultsAPIView'),
        (f'services/{service_id}/metrics/', 'SyntheticServiceMetricsAPIView'),
    )

    def test_genoma_v1_routes_resolve_to_authenticated_normalized_views(self):
        with self.settings(DEBUG=False):
            for suffix, view in self.service_routes:
                path = '/api/genoma/v1/' + suffix
                with self.subTest(path=path):
                    # Assert HTTP behavior first: a missing route must be RED, not Resolver404 ERROR.
                    self.assertIn(self.client.get(path).status_code, (401, 403))
                    matched = resolve(path)
                    self.assertEqual(matched.func.view_class.__name__, view)
                    self.assertEqual(matched.func.view_class.__module__, 'genoma.service_result_views')

    def test_genomics_v1_is_not_a_compatibility_alias(self):
        with self.settings(DEBUG=False):
            for suffix, _ in self.service_routes:
                path = '/api/genomics/v1/' + suffix
                for method in RetiredLegacyGeneticsRouteTests.methods:
                    with self.subTest(path=path, method=method):
                        self.assertEqual(getattr(self.client, method)(path).status_code, 404)
                with self.subTest(path=path), self.assertRaises(Resolver404):
                    resolve(path)

    def test_retired_genetics_routes_and_normalized_spelling_stay_not_found(self):
        paths = [path for path, _ in RetiredLegacyGeneticsRouteTests.routes
                 if path.startswith('/api/genetics/')]
        paths += [RetiredSNPCatalogRouteTests.url, '/api/genetics/patient-variants/42/',
                  *RetiredBiomarkerPanelRouteTests.paths]
        paths += ['/api/genetics/v1/' + suffix for suffix, _ in self.service_routes]
        with self.settings(DEBUG=False):
            for path in paths:
                for method in RetiredLegacyGeneticsRouteTests.methods:
                    with self.subTest(path=path, method=method):
                        self.assertEqual(getattr(self.client, method)(path).status_code, 404)
                with self.subTest(path=path), self.assertRaises(Resolver404):
                    resolve(path)

    def test_ingest_paths_remain_retired_without_being_renamed_or_reenabled(self):
        paths = ('/api/ingest/upload-genetic-file/', '/api/ingest/delete-genetic-file/',
                 '/api/ingest/user-report-status/42/')
        with self.settings(DEBUG=False):
            for path in paths:
                for method in RetiredLegacyGeneticsRouteTests.methods:
                    with self.subTest(path=path, method=method):
                        self.assertEqual(getattr(self.client, method)(path).status_code, 404)
                with self.subTest(path=path), self.assertRaises(Resolver404):
                    resolve(path)


class RetiredLegacyGeneticsAuthenticatedTests(APITestCase):
    def test_legacy_requests_return_404_for_all_roles_without_queries_or_row_changes(self):
        self.assertTrue(connection.settings_dict['NAME'].startswith('gdb_test_'))
        owner = User.objects.create_user(username='retired-genetics-owner')
        domain.Variant.objects.create(variant_type='synthetic', canonical_name='Preserved normalized row')
        Profile.objects.create(user=owner)
        paths = [path for path, _ in RetiredLegacyGeneticsRouteTests.routes[:-1]] + [
            f'/api/ingest/user-report-status/{owner.pk}/',
        ]
        for role, grant in (('client', None), ('admin', grant_admin_role),
                            ('analyst', grant_analyst_role), ('reception', grant_reception_role)):
            actor = User.objects.create_user(username=f'retired-genetics-{role}')
            if grant:
                grant(actor)
            self.client.cookies[settings.AUTH_COOKIE_NAME] = encode_jwt({'sub': str(actor.pk)})
            self.client.cookies['csrftoken'] = 'retired-genetics-csrf'
            before = [list(model.objects.order_by('pk').values()) for model in (
                User, AppUser, domain.Variant, Profile, Purchase, ServiceRequest, ServiceStatusLog,
            )]
            for path in paths:
                for method in RetiredLegacyGeneticsRouteTests.methods:
                    with self.subTest(role=role, path=path, method=method), self.assertNumQueries(0):
                        response = getattr(self.client, method)(
                            path, data=json.dumps({'userId': owner.pk}), content_type='application/json',
                            HTTP_X_CSRFTOKEN='retired-genetics-csrf',
                        ) if method not in ('get', 'head') else getattr(self.client, method)(path)
                        self.assertEqual(response.status_code, 404)
            self.assertEqual([list(model.objects.order_by('pk').values()) for model in (
                User, AppUser, domain.Variant, Profile, Purchase, ServiceRequest, ServiceStatusLog,
            )], before)


class SyntheticServiceResultReadTests(APITestCase):
    list_url = '/api/genoma/v1/services/'

    def setUp(self):
        self.assertTrue(connection.settings_dict['NAME'].startswith('gdb_test_'))
        environment = patch.dict(os.environ, {
            'ENVIRONMENT': 'development', 'RENDER': '',
            'RENDER_EXTERNAL_HOSTNAME': '', 'DATABASE_URL': '',
        })
        environment.start()
        self.addCleanup(environment.stop)
        debug = self.settings(DEBUG=True)
        debug.enable()
        self.addCleanup(debug.disable)
        self.user = User.objects.create_user(username='synthetic-read-owner')
        self.other = User.objects.create_user(username='synthetic-read-other')
        self.receipt = bundle.import_synthetic_genomics(user_id=self.user.pk)
        self.other_receipt = bundle.import_synthetic_genomics(user_id=self.other.pk)
        self.request = ServiceRequest.objects.get(pk=self.receipt.service_request_id)
        self.purchase = self.request.purchase
        self.participant = self.request.participant
        self.sample = Sample.objects.get(pk=self.receipt.sample_id)
        self.result = domain.AnalysisResult.objects.get(sample=self.sample, module=bundle.MODULES[0][0])
        self.analysis = self.result.analysis
        self.release = self.result.release
        self.other_sample = Sample.objects.get(pk=self.other_receipt.sample_id)
        self.other_analysis = domain.Analysis.objects.get(sample=self.other_sample, module=self.analysis.module)
        self.authenticate(self.user)

    def authenticate(self, user):
        self.client.cookies[settings.AUTH_COOKIE_NAME] = encode_jwt({'sub': str(user.pk)})

    def detail_url(self, identifier=None):
        return f'{self.list_url}{identifier or self.receipt.service_request_id}/results/'

    def metrics_url(self, identifier=None):
        return f'{self.list_url}{identifier or self.receipt.service_request_id}/metrics/'

    def assert_response(self, response, status, body):
        self.assertEqual(response.status_code, status)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertEqual(response.json(), body)

    def assert_hidden(self):
        self.assert_response(self.client.get(self.detail_url()), 404, {'detail': 'Not found.'})
        self.assert_response(self.client.get(self.metrics_url()), 404, {'detail': 'Not found.'})
        self.assert_response(self.client.get(self.list_url), 200, {'services': []})

    def summary(self, receipt=None, version=bundle.DEMO_VERSION):
        receipt = receipt or self.receipt
        sample = Sample.objects.get(pk=receipt.sample_id)
        demo = bundle.get_synthetic_bundle(version)
        return {
            'service_request_id': str(receipt.service_request_id), 'sample_id': str(receipt.sample_id),
            'sample_code': sample.sample_code, 'release_version': version,
            'synthetic': True, 'non_clinical': True, 'disclaimer': demo.disclaimer,
        }

    def list_item(self, receipt=None, version=bundle.DEMO_VERSION):
        receipt = receipt or self.receipt
        purchase = Purchase.objects.get(pk=receipt.purchase_id)
        return self.summary(receipt, version) | {
            'purchased_at': purchase.purchased_at.isoformat().replace('+00:00', 'Z'),
        }

    def set_bundle_timestamp(self, receipt, timestamp):
        Purchase.objects.filter(pk=receipt.purchase_id).update(purchased_at=timestamp, created_at=timestamp)
        ServiceRequest.objects.filter(pk=receipt.service_request_id).update(
            created_at=timestamp, started_at=timestamp,
        )
        Sample.objects.filter(service_request_id=receipt.service_request_id).update(created_at=timestamp)
        domain.Analysis.objects.filter(service_request_id=receipt.service_request_id).update(created_at=timestamp)
        domain.AnalysisResult.objects.filter(sample__service_request_id=receipt.service_request_id).update(
            created_at=timestamp,
        )

    def state(self):
        return [list(model.objects.order_by('pk').values()) for model in (
            User, AppUser, Participant, Profile, domain.Variant, domain.Genotype, Purchase, ServiceRequest,
            ServiceStatusLog, Sample, domain.DataRelease, domain.Analysis, domain.AnalysisResult,
        )]

    def test_owner_gets_exact_owned_list_and_six_raw_nonclinical_module_results_without_writes(self):
        before = self.state()
        expected_results = [{
            'module': module, 'result_type': 'synthetic_placeholder',
            'value_code': 'SYNTHETIC_NOT_EVALUATED', 'value_text': f'{label}. {bundle.DISCLAIMER}',
            'payload': {
                'demo_id': bundle.DEMO_NAME, 'demo_version': bundle.DEMO_VERSION,
                'synthetic': True, 'non_clinical': True, 'clinically_reviewed': False,
                'disclaimer': bundle.DISCLAIMER, 'module': module, 'label': label,
                'state': 'not_evaluated',
                'rows': [{'label': label, 'state': 'not_evaluated', 'value': None}],
            },
        } for module, label in bundle.MODULES]
        expected = self.summary()
        expected_list_item = self.list_item()
        with CaptureQueriesContext(connection) as queries:
            self.assert_response(self.client.get(self.list_url), 200, {'services': [expected_list_item]})
            self.assert_response(self.client.get(self.detail_url()), 200, expected | {'results': expected_results})
        self.assertFalse(any(query['sql'].lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE'))
                             for query in queries.captured_queries))
        self.assertFalse(any('"genotype"' in query['sql'] or 'COUNT(' in query['sql'].upper()
                             for query in queries.captured_queries))
        self.assertEqual(self.state(), before)

    def test_genoma_v1_preserves_owner_scoped_list_results_and_metrics_without_writes(self):
        list_url = '/api/genoma/v1/services/'
        service_url = f'{list_url}{self.receipt.service_request_id}/'
        before = self.state()
        with CaptureQueriesContext(connection) as queries:
            self.assert_response(self.client.get(list_url), 200, {'services': [self.list_item()]})
            results = self.client.get(service_url + 'results/')
            self.assertEqual(results.status_code, 200)
            self.assertEqual(results['Content-Type'], 'application/json')
            body = results.json()
            self.assertEqual({key: value for key, value in body.items() if key != 'results'}, self.summary())
            self.assertEqual([row['module'] for row in body['results']], [module for module, _ in bundle.MODULES])
            for row in body['results']:
                self.assertEqual(row['result_type'], 'synthetic_placeholder')
                self.assertEqual(row['value_code'], 'SYNTHETIC_NOT_EVALUATED')
                self.assertIs(row['payload']['synthetic'], True)
                self.assertIs(row['payload']['non_clinical'], True)
                self.assertEqual(row['payload']['state'], 'not_evaluated')
            self.assert_response(self.client.get(service_url + 'metrics/'), 200, self.summary() | {
                'metrics': {'kind': 'record_count', 'modules': [{
                    'module': module, 'analysis_record_count': 1,
                    'analysis_synthetic_placeholder_record_count': 1,
                    'analysis_result_record_count': 1, 'result_synthetic_placeholder_record_count': 1,
                } for module, _ in bundle.MODULES]},
            })
        self.assertFalse(any(query['sql'].lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE'))
                             for query in queries.captured_queries))
        self.assertEqual(self.state(), before)

    def test_genoma_v1_does_not_expose_another_owners_service_or_accept_writes(self):
        list_url = '/api/genoma/v1/services/'
        self.authenticate(self.other)
        self.assert_response(self.client.get(list_url), 200, {'services': [self.list_item(self.other_receipt)]})
        for resource in ('results', 'metrics'):
            path = f'{list_url}{self.receipt.service_request_id}/{resource}/'
            with self.subTest(resource=resource):
                self.assert_response(self.client.get(path), 404, {'detail': 'Not found.'})
        self.client.force_authenticate(user=self.user)
        for path in (list_url, *(f'{list_url}{self.receipt.service_request_id}/{resource}/'
                                 for resource in ('results', 'metrics'))):
            for method in ('post', 'put', 'patch', 'delete'):
                with self.subTest(path=path, method=method), self.assertNumQueries(0):
                    self.assertEqual(getattr(self.client, method)(path, {}, format='json').status_code, 405)

    def test_list_returns_paid_timestamps_in_canonical_order_without_account_identifiers(self):
        version_one = self.receipt
        version_two = bundle.import_synthetic_genomics(user_id=self.user.pk, version='2')
        other_version_two = bundle.import_synthetic_genomics(user_id=self.other.pk, version='2')
        now = timezone.now()
        older = now - timedelta(days=2)
        self.set_bundle_timestamp(version_one, older)
        self.set_bundle_timestamp(version_two, now)

        def expected_item(receipt, version, purchased_at):
            return self.summary(receipt, version) | {
                'purchased_at': purchased_at.isoformat().replace('+00:00', 'Z'),
            }

        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'services': [
            expected_item(version_two, '2', now), expected_item(version_one, '1', older),
        ]})
        self.assertEqual(self.client.get(self.list_url).json(), response.json())

        tied_paid_at = now + timedelta(days=1)
        self.set_bundle_timestamp(version_one, tied_paid_at)
        self.set_bundle_timestamp(version_two, tied_paid_at)
        ordered = self.client.get(self.list_url).json()['services']
        self.assertEqual(self.client.get(self.list_url).json()['services'], ordered)
        expected_by_purchase_pk = sorted(
            ((version_one, '1'), (version_two, '2')),
            key=lambda pair: pair[0].purchase_id.int, reverse=True,
        )
        self.assertEqual([item['service_request_id'] for item in ordered], [
            str(receipt.service_request_id) for receipt, _ in expected_by_purchase_pk
        ])

        forbidden = {
            'user_id', 'userid', 'owner_id', 'ownerid', 'account_id', 'accountid',
            'participant_id', 'participantid', 'participant_code', 'purchase_id', 'purchaseid',
        }

        def check(value):
            if isinstance(value, dict):
                for key, item in value.items():
                    self.assertNotIn(key.lower(), forbidden)
                    check(item)
            elif isinstance(value, list):
                for item in value:
                    check(item)

        check(response.json())
        content = response.content.decode()
        for private_value in (self.user.username, str(self.user.app_user.pk), str(self.participant.pk),
                              str(self.purchase.pk), str(other_version_two.purchase_id),
                              str(other_version_two.service_request_id)):
            self.assertNotIn(private_value, content)

        with transaction.atomic():
            Purchase.objects.filter(pk=version_two.purchase_id).update(
                status=PurchaseStatus.objects.get(code='PENDING'),
            )
            paid_only = self.client.get(self.list_url).json()['services']
            self.assertEqual(paid_only, [expected_item(version_one, '1', tied_paid_at)])
            transaction.set_rollback(True)

    def test_owner_gets_exact_service_record_counts_from_validated_placeholders_without_writes(self):
        self.assertEqual([module for module, _ in bundle.MODULES], [
            'global_ancestry', 'local_ancestry', 'polygenic_risk',
            'monogenic_risk', 'traits', 'pharmacogenetics',
        ])
        analyses = list(domain.Analysis.objects.filter(sample=self.sample))
        results = list(domain.AnalysisResult.objects.filter(sample=self.sample))
        expected_modules = [{
            'module': module,
            'analysis_record_count': sum(row.module == module for row in analyses),
            'analysis_synthetic_placeholder_record_count': sum(
                row.module == module and row.status == 'synthetic_placeholder' for row in analyses),
            'analysis_result_record_count': sum(row.module == module for row in results),
            'result_synthetic_placeholder_record_count': sum(
                row.module == module and row.result_type == 'synthetic_placeholder'
                and row.payload['state'] == 'not_evaluated' for row in results),
        } for module, _ in bundle.MODULES]
        self.assertEqual([[value for key, value in item.items() if key != 'module']
                          for item in expected_modules], [[1, 1, 1, 1]] * 6)
        expected = self.summary() | {'metrics': {'kind': 'record_count', 'modules': expected_modules}}
        before = self.state()
        with CaptureQueriesContext(connection) as result_queries:
            self.assertEqual(self.client.get(self.detail_url()).status_code, 200)
        with CaptureQueriesContext(connection) as metric_queries:
            self.assert_response(self.client.get(self.metrics_url()), 200, expected)
            self.assert_response(self.client.get(self.metrics_url()), 200, expected)
        # Metrics reuse the same validated rows, not COUNT queries or a second graph scan.
        expected_sql = [query['sql'] for query in result_queries.captured_queries]
        self.assertEqual([query['sql'] for query in metric_queries.captured_queries], expected_sql * 2)
        self.assertFalse(any(query['sql'].lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE'))
                             for query in metric_queries.captured_queries))
        self.assertEqual(self.state(), before)
        self.assertEqual(resolve(self.metrics_url()).view_name, 'api_genoma_v1_service_metrics')

    def test_responses_never_include_counters_legacy_metrics_or_participant_account_identifiers(self):
        forbidden = {
            'count', 'user_id', 'userId', 'owner_id', 'account_id', 'participant_id', 'participant_code',
            'purchase_id', 'import_id', 'manifest_checksum', 'genotype', 'genotipo', 'rsid',
            'percentage', 'risk_score', 'nivel_riesgo', 'magnitud_efecto', 'total_variants', 'snp_count',
        }

        def check(value):
            if isinstance(value, dict):
                for key, item in value.items():
                    self.assertNotIn(key, forbidden)
                    self.assertFalse(key.startswith('total_') or 'count' in key.lower(), key)
                    check(item)
            elif isinstance(value, list):
                for item in value:
                    check(item)

        for path in (self.list_url, self.detail_url()):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            check(response.json())

    def test_metrics_expose_only_record_counts_not_biological_legacy_or_identity_fields(self):
        allowed_counts = {
            'analysis_record_count', 'analysis_synthetic_placeholder_record_count',
            'analysis_result_record_count', 'result_synthetic_placeholder_record_count',
        }
        forbidden = {
            'analysis_count', 'processed_reports', 'variants_count', 'total_variants', 'snp_count',
            'user_id', 'userId', 'owner_id', 'account_id', 'participant_id', 'participant_code',
            'purchase_id', 'import_id', 'manifest_checksum', 'genotype', 'rsid',
            'percentage', 'country', 'population', 'trait_value', 'risk_score', 'value_numeric',
            'evaluated_count', 'completed_count', 'clinical_count', 'actionable_count',
        }
        response = self.client.get(self.metrics_url())
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(set(body), set(self.summary()) | {'metrics'})
        self.assertEqual(set(body['metrics']), {'kind', 'modules'})
        for item in body['metrics']['modules']:
            self.assertEqual(set(item), {'module'} | allowed_counts)
            for field in allowed_counts:
                self.assertIs(type(item[field]), int)

        def check(value):
            if isinstance(value, dict):
                for key, item in value.items():
                    self.assertNotIn(key, forbidden)
                    self.assertFalse(key.startswith('total_'), key)
                    if 'count' in key.lower():
                        self.assertIn(key, allowed_counts)
                    check(item)
            elif isinstance(value, list):
                for item in value:
                    check(item)

        check(body)

    def test_unauthenticated_gets_are_denied_without_domain_queries(self):
        self.client.cookies.clear()
        for path in (self.list_url, self.detail_url(), self.metrics_url()):
            with self.subTest(path=path), self.assertNumQueries(0):
                self.assertIn(self.client.get(path).status_code, (401, 403))

    def test_other_owner_missing_and_malformed_identifiers_are_indistinguishable_even_with_staff_flags(self):
        self.other.is_staff = self.other.is_superuser = True
        self.other.save(update_fields=['is_staff', 'is_superuser'])
        self.other.groups.add(Group.objects.get_or_create(name='ADMIN')[0])
        self.authenticate(self.other)
        for identifier in (self.receipt.service_request_id, uuid.uuid4(), 'not-a-uuid', '-1'):
            for path in (self.detail_url(identifier), self.metrics_url(identifier)):
                self.assert_response(self.client.get(path), 404, {'detail': 'Not found.'})
        self.assert_response(self.client.get(self.list_url), 200, {'services': [self.list_item(self.other_receipt)]})
        own_metrics = self.client.get(self.metrics_url(self.other_receipt.service_request_id))
        self.assertEqual(own_metrics.status_code, 200)
        self.assertEqual(own_metrics.json()['service_request_id'], str(self.other_receipt.service_request_id))
        for grant in (grant_admin_role, grant_analyst_role, grant_reception_role):
            with self.subTest(role=grant.__name__):
                grant(self.other)
                for identifier in (self.receipt.service_request_id, self.other_receipt.service_request_id, uuid.uuid4()):
                    for path in (self.detail_url(identifier), self.metrics_url(identifier)):
                        self.assert_response(self.client.get(path), 404, {'detail': 'Not found.'})
                self.assert_response(self.client.get(self.list_url), 200, {'services': []})

    def test_active_existing_client_mapping_is_required_and_never_created_or_repaired(self):
        before = self.state()
        unmapped = User.objects.bulk_create([User(username='synthetic-read-unmapped')])[0]
        self.client.force_authenticate(user=unmapped)
        self.assert_hidden()
        self.assertFalse(AppUser.objects.filter(django_user=unmapped).exists())
        self.client.force_authenticate(user=self.user)
        for changes in ({'is_active': False},):
            with transaction.atomic():
                User.objects.filter(pk=self.user.pk).update(**changes)
                self.assert_hidden()  # Even a stale authenticated instance cannot authorize reads.
                transaction.set_rollback(True)
        for code in ('ADMIN', 'ANALISTA', 'RECEPCION'):
            with self.subTest(role=code), transaction.atomic():
                AppUser.objects.filter(django_user=self.user).update(role=Role.objects.get(code=code))
                self.assert_hidden()
                transaction.set_rollback(True)
        User.objects.filter(pk=unmapped.pk).delete()
        self.assertEqual(self.state(), before)

    def test_an_eligible_owner_without_a_bundle_gets_empty_list_and_generic_detail_404(self):
        user = User.objects.create_user(username='synthetic-read-empty')
        self.authenticate(user)
        self.assert_hidden()

    def test_list_ignores_unrelated_paid_services_and_query_parameters_cannot_choose_an_owner(self):
        ServiceRequest.objects.create(
            purchase=Purchase.objects.create(owner=self.user.app_user, status=self.purchase.status),
            participant=self.participant, status=self.request.status,
        )
        query = f'?user_id={self.other.pk}&participant_id={self.other_sample.participant_id}'
        self.assert_response(self.client.get(self.list_url + query), 200, {'services': [self.list_item()]})
        for path in (self.detail_url(), self.metrics_url()):
            response = self.client.get(path + query)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['service_request_id'], str(self.receipt.service_request_id))
            self.assertEqual(response.json(), self.client.get(path).json())

    def test_existing_nonsynthetic_participant_is_supported_without_disclosing_or_rewriting_it(self):
        user = User.objects.create_user(username='synthetic-read-existing-participant')
        participant = Participant.objects.create(
            user=user, participant_code='existing-read-participant', metadata=['existing'],
            consent_status='withdrawn', enrollment_status='inactive',
        )
        receipt = bundle.import_synthetic_genomics(user_id=user.pk)
        before = self.state()
        self.authenticate(user)
        self.assert_response(self.client.get(self.list_url), 200, {'services': [self.list_item(receipt)]})
        for path in (self.detail_url(receipt.service_request_id), self.metrics_url(receipt.service_request_id)):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertNotIn(str(participant.pk), response.content.decode())
            self.assertNotIn(participant.participant_code, response.content.decode())
        self.assertEqual(self.state(), before)

    def test_all_endpoints_use_the_importer_guard_before_any_domain_query(self):
        self.client.force_authenticate(user=self.user)
        paths = (self.list_url, self.detail_url(), self.metrics_url(),
                 self.metrics_url(uuid.uuid4()), self.metrics_url('not-a-uuid'))
        with patch.object(bundle, '_require_local_development', side_effect=CommandError(bundle.LOCAL_ONLY)) as guard:
            for path in paths:
                with self.assertNumQueries(0):
                    self.assert_response(self.client.get(path), 404, {'detail': 'Not found.'})
            self.assertEqual(guard.call_count, len(paths))
        with patch.object(bundle, '_require_local_development', wraps=bundle._require_local_development) as guard:
            for path in (self.list_url, self.detail_url(), self.metrics_url()):
                with CaptureQueriesContext(connection) as queries:
                    self.assertEqual(self.client.get(path).status_code, 200)
                self.assertTrue(queries.captured_queries[0]['sql'].startswith('SELECT current_database()'))
            self.assertEqual(guard.call_count, 3)

    def test_disabled_environment_returns_generic_404_without_domain_queries(self):
        self.client.force_authenticate(user=self.user)
        for environment in ('', 'production', 'staging', 'test', 'dev', 'Development'):
            with self.subTest(environment=environment), patch.dict(os.environ, {'ENVIRONMENT': environment}):
                for path in (self.list_url, self.detail_url(), self.metrics_url()):
                    with self.assertNumQueries(0):
                        self.assert_response(self.client.get(path), 404, {'detail': 'Not found.'})
        with patch.dict(os.environ):
            os.environ.pop('ENVIRONMENT')
            for path in (self.list_url, self.detail_url(), self.metrics_url()):
                with self.assertNumQueries(0):
                    self.assert_response(self.client.get(path), 404, {'detail': 'Not found.'})
        for options in ({'DEBUG': False}, {'DEBUG': 1}, {'DATABASE_ROUTERS': [object()]}):
            with self.subTest(settings=options), self.settings(**options):
                for path in (self.list_url, self.detail_url(), self.metrics_url()):
                    with self.assertNumQueries(0):
                        self.assert_response(self.client.get(path), 404, {'detail': 'Not found.'})
        for key in ('RENDER', 'RENDER_EXTERNAL_HOSTNAME'):
            with patch.dict(os.environ, {key: 'deployment-present'}):
                for path in (self.detail_url(), self.metrics_url()):
                    with self.assertNumQueries(0):
                        self.assert_response(self.client.get(path), 404, {'detail': 'Not found.'})
        for config in ({'HOST': '192.0.2.1'}, {'NAME': 'postgres'},
                       {'ENGINE': 'django.db.backends.sqlite3'}, {'OPTIONS': {'host': 'override'}}):
            with self.subTest(config=config), patch.dict(connection.settings_dict, config):
                for path in (self.list_url, self.detail_url(), self.metrics_url()):
                    with self.assertNumQueries(0):
                        self.assert_response(self.client.get(path), 404, {'detail': 'Not found.'})

    def test_actual_database_guard_rejection_performs_only_the_importers_server_identity_query(self):
        self.client.force_authenticate(user=self.user)
        for database, address in ((connection.settings_dict['NAME'], '192.0.2.1'),
                                  ('unexpected_database', '127.0.0.1')):
            for path in (self.list_url, self.detail_url(), self.metrics_url()):
                with self.subTest(database=database, path=path), patch.object(connection, 'cursor') as cursor:
                    sql = cursor.return_value.__enter__.return_value
                    sql.fetchone.return_value = (database, address)
                    self.assert_response(self.client.get(path), 404, {'detail': 'Not found.'})
                    self.assertEqual(sql.execute.call_args_list, [
                        call('SELECT current_database(), inet_server_addr()::text'),
                    ])

    def test_tampered_ownership_sample_analysis_release_and_results_fail_closed_not_partially(self):
        spare = User.objects.bulk_create([User(username='synthetic-read-displaced-user')])[0]
        unrelated_release = domain.DataRelease.objects.create(
            name='unrelated-read-release', version='other', status='unlisted', reference_assembly='unknown',
        )
        scenarios = (
            (AppUser, self.user.app_user.pk, {'django_user': spare}),
            (Participant, self.participant.pk, {'user': spare}),
            (Purchase, self.purchase.pk, {'owner': self.other.app_user}),
            (Purchase, self.purchase.pk, {'status': PurchaseStatus.objects.get(code='PENDING')}),
            (Purchase, self.purchase.pk, {'status': None}),
            (Purchase, self.purchase.pk, {'purchased_at': None}),
            (ServiceRequest, self.request.pk, {'participant': None}),
            (ServiceRequest, self.request.pk, {'participant': self.other_sample.participant}),
            (ServiceRequest, self.request.pk, {'completed_at': timezone.now()}),
            (Sample, self.sample.pk, {'participant': self.other_sample.participant}),
            (Sample, self.sample.pk, {'service_request': self.other_sample.service_request}),
            (Sample, self.sample.pk, {'sample_type': 'saliva'}),
            (Sample, self.sample.pk, {'sample_code': 'NOT-THE-BUNDLED-SAMPLE'}),
            (Sample, self.sample.pk, {'status': 'available'}),
            (Sample, self.sample.pk, {'parent_sample': self.sample}),
            (Sample, self.sample.pk, {'material': 'biological'}),
            (domain.Analysis, self.analysis.pk, {'participant': None}),
            (domain.Analysis, self.analysis.pk, {'participant': self.other_sample.participant}),
            (domain.Analysis, self.analysis.pk, {'sample': None}),
            (domain.Analysis, self.analysis.pk, {'sample': self.other_sample}),
            (domain.Analysis, self.analysis.pk, {'service_request': None}),
            (domain.Analysis, self.analysis.pk, {'service_request': self.other_sample.service_request}),
            (domain.Analysis, self.analysis.pk, {'release': None}),
            (domain.Analysis, self.analysis.pk, {'release': unrelated_release}),
            (domain.Analysis, self.analysis.pk, {'module': bundle.MODULES[1][0]}),
            (domain.Analysis, self.analysis.pk, {'pipeline_name': 'not-synthetic'}),
            (domain.Analysis, self.analysis.pk, {'pipeline_version': '2'}),
            (domain.Analysis, self.analysis.pk, {'status': 'completed'}),
            (domain.Analysis, self.analysis.pk, {'started_at': timezone.now()}),
            (domain.DataRelease, self.release.pk, {'name': 'not-the-bundle'}),
            (domain.DataRelease, self.release.pk, {'version': '2'}),
            (domain.DataRelease, self.release.pk, {'status': 'published'}),
            (domain.DataRelease, self.release.pk, {'manifest_checksum': '0' * 64}),
            (domain.DataRelease, self.release.pk, {'description': 'clinically reviewed'}),
            (domain.DataRelease, self.release.pk, {'reference_assembly': 'GRCh38'}),
            (domain.AnalysisResult, self.result.pk, {'analysis': self.other_analysis}),
            (domain.AnalysisResult, self.result.pk, {'participant': None}),
            (domain.AnalysisResult, self.result.pk, {'participant': self.other_sample.participant}),
            (domain.AnalysisResult, self.result.pk, {'sample': None}),
            (domain.AnalysisResult, self.result.pk, {'sample': self.other_sample}),
            (domain.AnalysisResult, self.result.pk, {'release': None}),
            (domain.AnalysisResult, self.result.pk, {'release': unrelated_release}),
            (domain.AnalysisResult, self.result.pk, {'module': bundle.MODULES[1][0]}),
            (domain.AnalysisResult, self.result.pk, {'result_type': 'clinical'}),
            (domain.AnalysisResult, self.result.pk, {'value_code': 'EVALUATED'}),
            (domain.AnalysisResult, self.result.pk, {'value_text': 'interpreted result'}),
            (domain.AnalysisResult, self.result.pk, {'value_numeric': Decimal('1')}),
            (domain.AnalysisResult, self.result.pk, {'reference_assembly': 'GRCh38'}),
            (domain.AnalysisResult, self.result.pk, {'haplotype': 1}),
            (domain.AnalysisResult, self.result.pk, {'unit': 'clinical'}),
            (domain.AnalysisResult, self.result.pk, {'percentile': Decimal('50')}),
        )
        for model, pk, changes in scenarios:
            with self.subTest(model=model.__name__, changes=changes), transaction.atomic():
                model.objects.filter(pk=pk).update(**changes)
                before = self.state()
                self.assert_hidden()
                self.assertEqual(self.state(), before)
                transaction.set_rollback(True)

    def test_missing_extra_nonobject_or_tampered_markers_and_placeholder_payloads_are_rejected(self):
        for model, row, field in ((Sample, self.sample, 'metadata'),
                                  (domain.Analysis, self.analysis, 'parameters'),
                                  (domain.AnalysisResult, self.result, 'payload')):
            marker = getattr(row, field)
            changes = [None, [], {}, marker | {'synthetic': False}, marker | {'synthetic': 1},
                       marker | {'non_clinical': False}, marker | {'clinically_reviewed': True},
                       marker | {'clinically_reviewed': 0}, marker | {'demo_id': 'other'},
                       marker | {'demo_version': '2'}, marker | {'import_id': str(uuid.uuid4())},
                       marker | {'manifest_checksum': '0' * 64}, marker | {'disclaimer': ''},
                       marker | {'participant_id': str(self.participant.pk)}, marker | {'count': 6}]
            if field == 'payload':
                changes += [marker | {'module': 'other'}, marker | {'state': 'evaluated'},
                            marker | {'label': 'interpreted'}, marker | {'rows': []},
                            marker | {'rows': [{'label': marker['label'], 'state': 'evaluated', 'value': 1}]}]
            for value in changes:
                with self.subTest(model=model.__name__, marker=value), transaction.atomic():
                    model.objects.filter(pk=row.pk).update(**{field: value})
                    self.assert_hidden()
                    transaction.set_rollback(True)

    def test_missing_graph_rows_never_expose_a_partial_result_set(self):
        chain = (domain.AnalysisResult, domain.Analysis, Sample, ServiceRequest, Purchase, Participant)
        for index, model in enumerate(chain):
            with self.subTest(missing=model.__name__), transaction.atomic():
                for preceding in chain[:index + 1]:
                    if preceding is Purchase:
                        preceding.objects.filter(pk=self.purchase.pk).delete()
                    elif preceding is ServiceRequest:
                        preceding.objects.filter(pk=self.request.pk).delete()
                    elif preceding is Participant:
                        preceding.objects.filter(pk=self.participant.pk).delete()
                    else:
                        preceding.objects.filter(participant=self.participant).delete()
                self.assert_hidden()
                transaction.set_rollback(True)
        with transaction.atomic():
            domain.AnalysisResult.objects.filter(pk=self.result.pk).delete()
            self.assert_hidden()
            transaction.set_rollback(True)
        with transaction.atomic():
            domain.Analysis.objects.filter(participant=self.participant).update(release=None)
            domain.AnalysisResult.objects.filter(participant=self.participant).update(release=None)
            # The shared release may be absent without affecting the account/service rows.
            domain.Analysis.objects.filter(release=self.release).update(release=None)
            domain.AnalysisResult.objects.filter(release=self.release).update(release=None)
            self.release.delete()
            self.assert_hidden()
            transaction.set_rollback(True)

    def test_duplicate_and_displaced_rows_are_rejected_instead_of_filtered_or_deduplicated(self):
        for model, original in ((Sample, self.sample), (domain.Analysis, self.analysis),
                                (domain.AnalysisResult, self.result)):
            for detached in (False, True):
                with self.subTest(model=model.__name__, detached=detached), transaction.atomic():
                    duplicate = model.objects.get(pk=original.pk)
                    duplicate.pk = uuid.uuid4()
                    if model is Sample:
                        duplicate.sample_code += '-duplicate'
                        if detached:
                            duplicate.metadata = duplicate.metadata | {'import_id': str(uuid.uuid4())}
                            duplicate.service_request = ServiceRequest.objects.create(
                                purchase=Purchase.objects.create(owner=self.user.app_user, status=self.purchase.status),
                                participant=self.participant, status=self.request.status,
                            )
                    elif detached and model is domain.Analysis:
                        duplicate.sample = duplicate.service_request = None
                        duplicate.parameters = duplicate.parameters | {'import_id': str(uuid.uuid4())}
                    elif detached:
                        duplicate.analysis = self.other_analysis
                        duplicate.sample = duplicate.participant = duplicate.release = None
                    duplicate.save(force_insert=True)
                    self.assert_hidden()
                    transaction.set_rollback(True)

    def test_only_get_is_supported_and_profile_and_shared_service_status_are_unchanged(self):
        from genoma import urls

        self.assertEqual([str(route.pattern) for route in urls.urlpatterns], [
            'genoma/v1/services/', 'genoma/v1/services/<str:service_request_id>/results/',
            'genoma/v1/services/<str:service_request_id>/metrics/',
        ])
        Profile.objects.create(user=self.user)
        status_path = '/api/auth/me/'
        status_before = (self.client.get(status_path).status_code, self.client.get(status_path).json())
        before = self.state()
        for path in (self.list_url, self.detail_url(), self.metrics_url()):
            self.assertEqual(self.client.get(path).status_code, 200)
            self.assertEqual(self.client.post(path, {}, format='json').status_code, 405)
        self.client.force_authenticate(user=self.user)
        for method in ('post', 'put', 'patch', 'delete'):
            with self.subTest(method=method), self.assertNumQueries(0):
                self.assertEqual(getattr(self.client, method)(self.metrics_url(), {}, format='json').status_code, 405)
        self.client.force_authenticate(user=None)
        self.authenticate(self.user)
        self.assertEqual((self.client.get(status_path).status_code, self.client.get(status_path).json()), status_before)
        self.assertEqual(self.state(), before)


class SyntheticGenomicsImportTests(TestCase):
    modules = {
        'global_ancestry', 'local_ancestry', 'polygenic_risk',
        'monogenic_risk', 'traits', 'pharmacogenetics',
    }

    def setUp(self):
        self.assertTrue(connection.settings_dict['NAME'].startswith('gdb_test_'))
        environment = patch.dict(os.environ, {
            'ENVIRONMENT': 'development', 'RENDER': '',
            'RENDER_EXTERNAL_HOSTNAME': '', 'DATABASE_URL': '',
        })
        environment.start()
        self.addCleanup(environment.stop)
        debug = self.settings(DEBUG=True)
        debug.enable()
        self.addCleanup(debug.disable)
        self.user = User.objects.create_user(username=f'synthetic-target-{uuid.uuid4().hex}')
        self.other = User.objects.create_user(username=f'synthetic-other-{uuid.uuid4().hex}')

    def import_demo(self, user=None):
        output = StringIO()
        call_command('import_synthetic_genomics', '--user-id', str((user or self.user).pk),
                     '--demo-version', '1', stdout=output)
        return output.getvalue()

    def legacy_state(self):
        return [list(model.objects.order_by('pk').values()) for model in (
            User, AppUser, Profile, domain.Genotype, domain.Variant,
            domain.Population, domain.EpigeneticFeature, domain.Artifact,
        )]

    def import_state(self):
        from participants.models import Participant

        return self.legacy_state() + [list(model.objects.order_by('pk').values()) for model in (
            Participant, PurchaseStatus, RequestStatus, Purchase, ServiceRequest, ServiceStatusLog,
            Sample, domain.DataRelease, domain.Analysis, domain.AnalysisResult,
        )]

    def assert_rejected_without_changes(self, message='Inconsistent|duplicate'):
        before = self.import_state()
        with CaptureQueriesContext(connection) as queries:
            with self.assertRaisesRegex(CommandError, message):
                self.import_demo()
        self.assertFalse(any(query['sql'].lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE'))
                             for query in queries.captured_queries))
        self.assertEqual(self.import_state(), before)

    def test_seeds_owned_pending_nonclinical_placeholders_without_legacy_changes(self):
        from participants.models import Participant

        before = self.legacy_state()
        output = self.import_demo()
        participant = Participant.objects.get(user=self.user)
        purchase = Purchase.objects.get(owner=self.user.app_user)
        request = ServiceRequest.objects.get(purchase=purchase)
        sample = Sample.objects.get(service_request=request)
        self.assertFalse(ServiceStatusLog.objects.exists())
        self.assertEqual(purchase.status.code, 'PAID')
        self.assertIsNotNone(purchase.purchased_at)
        self.assertEqual((request.participant, sample.participant), (participant, participant))
        self.assertEqual(request.status.code, 'WAITING_SAMPLE')
        self.assertIsNone(request.completed_at)
        self.assertTrue(sample.metadata['synthetic'])
        self.assertEqual(sample.sample_type, 'synthetic')
        self.assertTrue(sample.sample_code.startswith('SYNTHETIC-'))
        self.assertEqual(participant.consent_status, 'pending')
        self.assertEqual(participant.enrollment_status, 'pending')
        self.assertIsNone(participant.consent_version)
        self.assertIsNone(participant.consented_at)
        self.assertEqual(domain.AnalysisResult.objects.count(), 6)
        self.assertEqual(set(domain.AnalysisResult.objects.values_list('module', flat=True)), self.modules)
        for result in domain.AnalysisResult.objects.all():
            self.assertEqual((result.participant, result.sample), (participant, sample))
            self.assertTrue(result.payload['synthetic'])
            self.assertTrue(result.payload['non_clinical'])
            self.assertFalse(result.payload['clinically_reviewed'])
            self.assertIn('non-clinical', result.payload['disclaimer'])
        self.assertIn('SYNTHETIC', output)
        self.assertIn('non-clinical', output)
        self.assertFalse(Purchase.objects.filter(owner=self.other.app_user).exists())
        self.assertFalse(Participant.objects.filter(user=self.other).exists())
        self.assertEqual(self.legacy_state(), before)
        self.assertNotIn(self.user.username, participant.participant_code)
        self.assertTrue(participant.participant_code.startswith('SYNTHETIC-'))
        self.assertEqual(domain.Analysis.objects.count(), 6)
        release = domain.DataRelease.objects.get()
        self.assertEqual((release.name, release.version, release.status, release.reference_assembly),
                         ('gdb-04f1-synthetic-genomics', '1', 'synthetic', 'not-applicable'))
        self.assertIn('non-clinical', release.description)
        self.assertEqual(len(release.manifest_checksum), 64)
        self.assertIsNone(release.frozen_at)
        for result in domain.AnalysisResult.objects.all():
            analysis = result.analysis
            self.assertEqual((analysis.participant, analysis.sample, analysis.service_request, analysis.release),
                             (participant, sample, request, release))
            self.assertEqual((analysis.module, analysis.pipeline_version, analysis.status),
                             (result.module, '1', 'synthetic_placeholder'))
            self.assertIsNone(analysis.started_at)
            self.assertIsNone(analysis.finished_at)
            self.assertTrue(analysis.parameters['synthetic'])
            self.assertEqual(result.release, release)
            self.assertEqual(result.result_type, 'synthetic_placeholder')
            self.assertEqual(result.value_code, 'SYNTHETIC_NOT_EVALUATED')
            self.assertIn('SYNTHETIC', result.value_text)
            self.assertEqual(result.payload['module'], result.module)
            self.assertEqual(result.payload['demo_version'], '1')
            self.assertEqual(result.payload['state'], 'not_evaluated')
            self.assertEqual(result.payload['rows'], [{
                'label': result.payload['label'], 'state': 'not_evaluated', 'value': None,
            }])
            for field in ('variant_id', 'epigenetic_feature_id', 'population_id', 'reference_assembly',
                          'contig', 'start_pos', 'end_pos', 'haplotype', 'value_numeric', 'unit',
                          'percentile', 'confidence'):
                self.assertIsNone(getattr(result, field), field)
            self.assertEqual((result.created_at, analysis.created_at), (purchase.created_at,) * 2)
        self.assertEqual((request.started_at, sample.created_at, purchase.purchased_at),
                         (purchase.created_at,) * 3)
        from services.status import get_service_projection
        projection = get_service_projection(self.user)
        # No history is fabricated to satisfy the unchanged fail-closed legacy projection.
        self.assertEqual(projection.service_status, ClientStatus.NO_PURCHASED)
        self.assertFalse(projection.can_view_results)

    def test_demo_never_attributes_a_user_action_or_owns_independent_status_history(self):
        output = self.import_demo()
        request = ServiceRequest.objects.get(purchase__owner=self.user.app_user)
        self.assertFalse(ServiceStatusLog.objects.exists())
        self.assertEqual(request.status.code, 'WAITING_SAMPLE')
        self.assertIsNone(request.completed_at)
        self.assertIn('SYNTHETIC', output)
        self.assertIn('Simulated PAID', output)
        self.assertIn('non-clinical', output)
        ServiceStatusLog.objects.create(
            request=request, status=request.status, actor=self.other.app_user,
            comment='Independently recorded history, not owned by the demo importer.',
        )
        before = self.import_state()
        with CaptureQueriesContext(connection) as queries:
            self.assertIn('already imported', self.import_demo())
        self.assertFalse(any(query['sql'].lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE'))
                             for query in queries.captured_queries))
        self.assertEqual(self.import_state(), before)

    def test_retry_identifiers_and_participant_code_are_scoped_to_the_opaque_app_user_uuid(self):
        from genoma.synthetic_import import DEMO_NAME, DEMO_VERSION
        from participants.models import Participant

        self.import_demo()
        participant = Participant.objects.get(user=self.user)
        purchase = Purchase.objects.get(owner=self.user.app_user)
        request = ServiceRequest.objects.get(purchase=purchase)
        sample = Sample.objects.get(service_request=request)
        kinds = ['import', 'participant', 'purchase', 'request', 'sample'] + [
            f'{kind}:{module}' for module in self.modules for kind in ('analysis', 'result')
        ]
        expected = {kind: uuid.uuid5(
            uuid.NAMESPACE_URL,
            f'genomia:{DEMO_NAME}:{DEMO_VERSION}:app-user:{self.user.app_user.user_id}:{kind}',
        ) for kind in kinds}
        actual = {
            'import': uuid.UUID(sample.metadata['import_id']), 'participant': participant.pk,
            'purchase': purchase.pk, 'request': request.pk, 'sample': sample.pk,
        } | {f'analysis:{row.module}': row.pk for row in domain.Analysis.objects.all()} | {
            f'result:{row.module}': row.pk for row in domain.AnalysisResult.objects.all()
        }
        self.assertEqual(actual, expected)
        self.assertEqual(participant.participant_code, f'SYNTHETIC-{expected["participant"].hex}')
        self.assertEqual(sample.sample_code, f'SYNTHETIC-DEMO-V{DEMO_VERSION}-{expected["sample"].hex}')
        before = self.import_state()
        self.assertIn('already imported', self.import_demo())
        self.assertEqual(self.import_state(), before)

    def test_safe_local_database_url_is_accepted_only_after_actual_server_verification(self):
        from dj_database_url import parse

        for index, host in enumerate(('127.0.0.1', 'localhost', '[::1]')):
            database_url = f'postgresql://{host}/{connection.settings_dict["NAME"]}'
            resolved = parse(database_url)
            config = {key: resolved[key] for key in ('ENGINE', 'HOST', 'NAME')}
            with self.subTest(host=host), patch.dict(os.environ, {'DATABASE_URL': database_url}), \
                    patch.dict(connection.settings_dict, config):
                with CaptureQueriesContext(connection) as queries:
                    self.assertIn('created' if index == 0 else 'already imported', self.import_demo())
                self.assertTrue(queries.captured_queries[0]['sql'].startswith('SELECT current_database()'))
                before = self.import_state()
                with CaptureQueriesContext(connection) as queries:
                    self.assertIn('already imported', self.import_demo())
                self.assertFalse(any(query['sql'].lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE'))
                                     for query in queries.captured_queries))
                self.assertEqual(self.import_state(), before)
        self.assertEqual(domain.AnalysisResult.objects.count(), 6)

    def test_remote_or_maintenance_database_urls_are_rejected_before_database_access(self):
        from dj_database_url import parse

        database = connection.settings_dict['NAME']
        before = self.import_state()
        for database_url in (
            f'postgresql://db.example.test/{database}', f'postgresql://192.0.2.1/{database}',
            f'postgresql://[2001:db8::1]/{database}', 'postgresql://127.0.0.1/postgres',
            'postgresql://localhost/template0', 'postgresql://[::1]/template1',
        ):
            resolved = parse(database_url)
            config = {key: resolved[key] for key in ('ENGINE', 'HOST', 'NAME')}
            with self.subTest(database_url=database_url), patch.dict(os.environ, {'DATABASE_URL': database_url}), \
                    patch.dict(connection.settings_dict, config), self.assertNumQueries(0):
                with self.assertRaisesRegex(CommandError, 'local development'):
                    self.import_demo()
        self.assertEqual(self.import_state(), before)

    def test_requires_explicit_positive_django_user_id_and_has_no_file_or_owner_options(self):
        before = self.import_state()
        for arguments in ((), ('--user-id', '0'), ('--user-id', '-1'), ('--user-id', '01'),
                          ('--user-id', '+1'), ('--user-id', '1.0'), ('--user-id', 'true'),
                          ('--user-id', ' 1'), ('--user-id', '١'), ('--user-id', str(2**63)),
                          ('--user-id', str(self.user.pk), '--file', 'arbitrary.json'),
                          ('--user-id', str(self.user.pk), '--owner', str(self.other.app_user.pk)),
                          ('--user-id', str(self.other.app_user.pk))):
            with self.subTest(arguments=arguments), self.assertNumQueries(0):
                with self.assertRaises(CommandError):
                    call_command('import_synthetic_genomics', *arguments, stdout=StringIO())
        for value in (None, True, False, 0, -1, 1.0, str(self.user.pk), 2**63):
            with self.subTest(keyword=value), self.assertNumQueries(0):
                with self.assertRaises(CommandError):
                    call_command('import_synthetic_genomics', user_id=value, stdout=StringIO())
        self.assertEqual(self.import_state(), before)

    def test_rejects_every_environment_except_explicit_exact_development_before_database_access(self):
        for environment in (None, '', 'production', 'staging', 'test', 'dev', 'Development', ' development '):
            with self.subTest(environment=environment), patch.dict(os.environ):
                if environment is None:
                    os.environ.pop('ENVIRONMENT', None)
                else:
                    os.environ['ENVIRONMENT'] = environment
                with self.assertNumQueries(0), self.assertRaisesRegex(CommandError, 'local development'):
                    self.import_demo()

    def test_requires_exact_debug_true_and_rejects_deployment_signals_before_database_access(self):
        for debug in (False, None, 1, 'True'):
            with self.subTest(debug=debug), self.settings(DEBUG=debug), self.assertNumQueries(0):
                with self.assertRaisesRegex(CommandError, 'local development'):
                    self.import_demo()
        for key in ('RENDER', 'RENDER_EXTERNAL_HOSTNAME'):
            with self.subTest(signal=key), patch.dict(os.environ, {key: 'deployment-present'}):
                with self.assertNumQueries(0), self.assertRaisesRegex(CommandError, 'local development'):
                    self.import_demo()

    def test_requires_postgresql_exact_loopback_host_and_nonmaintenance_database_without_overrides(self):
        invalid = [
            {'ENGINE': 'django.db.backends.sqlite3'}, {'HOST': ''}, {'HOST': None},
            {'HOST': '/var/run/postgresql'}, {'HOST': 'db.example.test'}, {'HOST': 'localhost.example.test'},
            {'HOST': '127.0.0.1,remote.example.test'}, {'HOST': '192.0.2.1'},
            {'HOST': '0.0.0.0'}, {'HOST': '[::1]'}, {'NAME': ''}, {'NAME': 'postgres'},
            {'NAME': 'template0'}, {'NAME': 'template1'},
        ] + [{'OPTIONS': {key: 'override'}} for key in ('service', 'host', 'hostaddr', 'dbname', 'database')]
        for config in invalid:
            with self.subTest(config=config), patch.dict(connection.settings_dict, config):
                with self.assertNumQueries(0), self.assertRaisesRegex(CommandError, 'local development'):
                    self.import_demo()
        for host in ('127.0.0.1', '::1', 'localhost'):
            with self.subTest(host=host), patch.dict(connection.settings_dict, {'HOST': host}):
                self.import_demo()
        self.assertEqual(domain.AnalysisResult.objects.count(), 6)

    def test_configured_database_routers_are_rejected_before_access_to_any_database(self):
        # A default-connection guard must not authorize ORM routing to another alias.
        with self.settings(DATABASE_ROUTERS=[object()]), self.assertNumQueries(0):
            with self.assertRaisesRegex(CommandError, 'local development'):
                self.import_demo()

    def test_actual_server_identity_must_be_loopback_and_match_the_configured_database(self):
        before = self.import_state()
        database_url = f'postgresql://localhost/{connection.settings_dict["NAME"]}'
        for database, address in (
            (connection.settings_dict['NAME'], '192.0.2.10'),
            (connection.settings_dict['NAME'], None),
            (connection.settings_dict['NAME'], 'invalid-address'),
            ('unexpected_database', '127.0.0.1'),
            ('postgres', '127.0.0.1'), ('template0', '127.0.0.1'), ('template1', '127.0.0.1'),
        ):
            with self.subTest(database=database, address=address), \
                    patch.dict(os.environ, {'DATABASE_URL': database_url}), \
                    patch.object(connection, 'cursor') as cursor:
                cursor.return_value.__enter__.return_value.fetchone.return_value = (database, address)
                with self.assertRaisesRegex(CommandError, 'local development'):
                    self.import_demo()
                executed = cursor.return_value.__enter__.return_value.execute.call_args_list
                self.assertEqual(len(executed), 1)
                self.assertTrue(executed[0].args[0].startswith('SELECT current_database()'))
        self.assertEqual(self.import_state(), before)

    def test_requires_existing_active_client_mapping_and_never_creates_accounts(self):
        inactive = User.objects.create_user(username='synthetic-inactive', is_active=False)
        unmapped = User.objects.bulk_create([User(username='synthetic-unmapped')])[0]
        privileged = []
        for suffix, grant in (('admin', grant_admin_role), ('analyst', grant_analyst_role),
                              ('reception', grant_reception_role)):
            user = User.objects.create_user(username=f'synthetic-{suffix}')
            grant(user)
            privileged.append(user)
        before = self.import_state()
        for identifier in (inactive.pk, unmapped.pk, *(user.pk for user in privileged), 2**31 - 1):
            with self.subTest(user_id=identifier), self.assertRaisesRegex(CommandError, 'existing active client'):
                call_command('import_synthetic_genomics', '--user-id', str(identifier), stdout=StringIO())
        self.assertEqual(self.import_state(), before)
        self.assertFalse(AppUser.objects.filter(django_user=unmapped).exists())

    def test_reuses_existing_participant_and_preserves_all_consent_and_enrollment_fields(self):
        from participants.models import Participant

        for consent in ('pending', 'withdrawn', 'granted'):
            with self.subTest(consent=consent), transaction.atomic():
                participant = Participant.objects.create(
                    user=self.user, participant_code='existing-pseudonymous-participant',
                    consent_status=consent, enrollment_status='inactive',
                    consent_version='existing-v1' if consent == 'granted' else None,
                    consented_at=timezone.now() if consent == 'granted' else None,
                    metadata={'existing': 'non-identifying'},
                )
                before = list(Participant.objects.values())
                self.import_demo()
                self.import_demo()
                self.assertEqual(list(Participant.objects.values()), before)
                self.assertEqual(Sample.objects.get().participant, participant)
                transaction.set_rollback(True)

    def test_existing_nonobject_participant_metadata_is_preserved_not_interpreted_as_import_provenance(self):
        from participants.models import Participant

        participant = Participant.objects.create(
            user=self.user, participant_code='existing-nonobject-metadata', metadata=['existing'],
        )
        before = list(Participant.objects.values())
        self.import_demo()
        self.import_demo()
        self.assertEqual(list(Participant.objects.values()), before)
        self.assertEqual(Sample.objects.get().participant, participant)

    def test_normalized_rows_and_profile_metadata_are_preserved_without_publishing_placeholders(self):
        grant_admin_role(self.other)
        domain.Variant.objects.create(variant_type='synthetic', canonical_name='Preserved normalized row')
        Profile.objects.create(user=self.user, phone='LEGACY-SYNTHETIC')
        before = self.legacy_state()
        self.import_demo()
        self.assertEqual(self.legacy_state(), before)
        self.client.cookies[settings.AUTH_COOKIE_NAME] = encode_jwt({'sub': str(self.other.pk)})
        with self.assertNumQueries(0):
            self.assertEqual(self.client.get(f'/api/ingest/user-report-status/{self.user.pk}/').status_code, 404)
        self.assertEqual(self.legacy_state(), before)
        self.assertEqual(domain.Variant.objects.count(), 1)

    def test_retry_is_a_read_only_noop_preserving_all_rows_timestamps_and_keys(self):
        first = self.import_demo()
        before = self.import_state()
        with CaptureQueriesContext(connection) as queries:
            second = self.import_demo()
        self.assertFalse(any(query['sql'].lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE'))
                             for query in queries.captured_queries))
        self.assertIn('created', first)
        self.assertIn('already imported', second)
        self.assertEqual(self.import_state(), before)
        self.assertEqual(domain.Analysis.objects.count(), 6)
        self.assertEqual(domain.AnalysisResult.objects.count(), 6)
        self.assertEqual(Purchase.objects.count(), 1)
        self.assertEqual(ServiceStatusLog.objects.count(), 0)

    def test_each_explicit_target_has_an_independent_owned_chain_and_shared_versioned_release(self):
        self.import_demo()
        first = list(domain.AnalysisResult.objects.order_by('pk').values())
        self.import_demo(self.other)
        self.assertEqual(list(domain.AnalysisResult.objects.filter(
            participant__user=self.user,
        ).order_by('pk').values()), first)
        self.assertEqual(domain.DataRelease.objects.count(), 1)
        for user in (self.user, self.other):
            sample = Sample.objects.get(participant__user=user)
            self.assertEqual(sample.service_request.purchase.owner.django_user, user)
            results = domain.AnalysisResult.objects.filter(sample=sample)
            self.assertEqual(results.count(), 6)
            self.assertEqual(set(results.values_list('module', flat=True)), self.modules)
        self.assertEqual(domain.AnalysisResult.objects.count(), 12)

    def test_partial_result_import_is_rejected_without_silent_repair(self):
        self.import_demo()
        domain.AnalysisResult.objects.filter(pk=domain.AnalysisResult.objects.first().pk).delete()
        self.assert_rejected_without_changes()

    def test_purchase_only_and_synthetic_participant_only_partial_imports_are_not_resumed(self):
        from participants.models import Participant

        with transaction.atomic():
            self.import_demo()
            purchase_id = Purchase.objects.get().pk
            seeded_participant = Participant.objects.get(user=self.user)
            transaction.set_rollback(True)
        with transaction.atomic():
            Purchase.objects.create(pk=purchase_id, owner=self.user.app_user,
                                    status=PurchaseStatus.objects.get(code='PAID'), purchased_at=timezone.now())
            self.assert_rejected_without_changes()
            transaction.set_rollback(True)
        Participant.objects.create(
            pk=seeded_participant.pk, user=self.user, participant_code=seeded_participant.participant_code,
            metadata=seeded_participant.metadata,
        )
        self.assert_rejected_without_changes()

    def test_rejects_inconsistent_links_markers_payload_values_and_provenance_without_writes(self):
        self.import_demo()
        result = domain.AnalysisResult.objects.first()
        analysis = result.analysis
        sample = result.sample
        request = sample.service_request
        purchase = request.purchase
        release = result.release
        scenarios = (
            (Purchase, purchase.pk, {'owner': self.other.app_user}),
            (Purchase, purchase.pk, {'status': PurchaseStatus.objects.get(code='PENDING')}),
            (Purchase, purchase.pk, {'purchased_at': None}),
            (ServiceRequest, request.pk, {'participant': None}),
            (ServiceRequest, request.pk, {'status': RequestStatus.objects.get(code='COMPLETED')}),
            (ServiceRequest, request.pk, {'completed_at': timezone.now()}),
            (Sample, sample.pk, {'metadata': {'synthetic': False}}),
            (Sample, sample.pk, {'material': 'biological material'}),
            (domain.Analysis, analysis.pk, {'participant': None}),
            (domain.Analysis, analysis.pk, {'module': 'incorrect'}),
            (domain.Analysis, analysis.pk, {'parameters': {}}),
            (domain.Analysis, analysis.pk, {'status': 'completed'}),
            (domain.AnalysisResult, result.pk, {'sample': None}),
            (domain.AnalysisResult, result.pk, {'release': None}),
            (domain.AnalysisResult, result.pk, {'payload': result.payload | {'clinically_reviewed': True}}),
            (domain.AnalysisResult, result.pk, {'value_numeric': Decimal('1')}),
            (domain.AnalysisResult, result.pk, {'module': 'incorrect'}),
            (domain.AnalysisResult, result.pk, {'haplotype': 1}),
            (domain.DataRelease, release.pk, {'manifest_checksum': '0' * 64}),
            (domain.DataRelease, release.pk, {'description': 'clinically reviewed'}),
            (domain.DataRelease, release.pk, {'status': 'published'}),
        )
        for model, pk, changes in scenarios:
            with self.subTest(model=model.__name__, changes=changes), transaction.atomic():
                model.objects.filter(pk=pk).update(**changes)
                self.assert_rejected_without_changes()
                transaction.set_rollback(True)

    def test_duplicate_results_analyses_and_samples_are_rejected_not_deduplicated(self):
        self.import_demo()
        for model in (domain.AnalysisResult, domain.Analysis, Sample):
            with self.subTest(duplicate=model.__name__), transaction.atomic():
                duplicate = model.objects.first()
                duplicate.pk = uuid.uuid4()
                if model is Sample:
                    duplicate.sample_code += '-duplicate'
                duplicate.save(force_insert=True)
                self.assert_rejected_without_changes()
                transaction.set_rollback(True)

    def test_detached_duplicate_partial_sample_with_wrong_import_token_is_not_ignored(self):
        self.import_demo()
        sample = Sample.objects.get()
        request = ServiceRequest.objects.create(
            purchase=Purchase.objects.create(
                owner=self.user.app_user, status=PurchaseStatus.objects.get(code='PAID'),
                purchased_at=timezone.now(),
            ),
            participant=sample.participant, status=RequestStatus.objects.get(code='WAITING_SAMPLE'),
        )
        Sample.objects.create(
            service_request=request, participant=sample.participant, sample_type='synthetic',
            sample_code='SYNTHETIC-DETACHED-DUPLICATE',
            metadata=sample.metadata | {'import_id': str(uuid.uuid4())},
        )
        self.assert_rejected_without_changes()

    def test_missing_required_catalogs_fail_without_creating_or_repairing_them(self):
        for model, code in ((PurchaseStatus, 'PAID'), (RequestStatus, 'WAITING_SAMPLE')):
            with self.subTest(catalog=code), transaction.atomic():
                model.objects.filter(code=code).update(code='UNAVAILABLE')
                self.assert_rejected_without_changes('catalog')
                transaction.set_rollback(True)

    def test_late_failure_rolls_back_every_created_row_including_participant_and_release(self):
        from participants.models import Participant

        before = self.import_state()
        save = domain.AnalysisResult.save
        written = []

        def fail_after_third_save(instance, *args, **kwargs):
            self.assertTrue(connection.in_atomic_block)
            save(instance, *args, **kwargs)
            written.append(instance.pk)
            if len(written) == 3:
                self.assertEqual(Participant.objects.filter(user=self.user).count(), 1)
                self.assertEqual(Purchase.objects.count(), 1)
                self.assertEqual(Sample.objects.count(), 1)
                self.assertEqual(domain.AnalysisResult.objects.count(), 3)
                raise RuntimeError('injected synthetic result failure')

        with patch.object(domain.AnalysisResult, 'save', autospec=True, side_effect=fail_after_third_save):
            with self.assertRaisesRegex(RuntimeError, 'injected synthetic result failure'):
                self.import_demo()
        self.assertEqual(len(written), 3)
        self.assertEqual(self.import_state(), before)
        self.import_demo()
        self.assertEqual(domain.AnalysisResult.objects.count(), 6)

    def test_concurrent_retries_create_one_chain_and_close_worker_connections(self):
        from participants.models import Participant

        gate = Barrier(2)

        def create_target():
            try:
                self.assertTrue(connections['default'].settings_dict['NAME'].startswith('gdb_test_'))
                return User.objects.create_user(username=f'synthetic-concurrent-{uuid.uuid4().hex}').pk
            finally:
                connections.close_all()

        def import_target(user_id):
            try:
                gate.wait(timeout=10)
                output = StringIO()
                call_command('import_synthetic_genomics', '--user-id', str(user_id),
                             '--demo-version', '1', stdout=output)
                return output.getvalue()
            finally:
                connections.close_all()

        def remove_target(user_id):
            try:
                release_ids = list(domain.Analysis.objects.filter(
                    participant__user_id=user_id,
                ).values_list('release_id', flat=True))
                domain.AnalysisResult.objects.filter(participant__user_id=user_id).delete()
                domain.Analysis.objects.filter(participant__user_id=user_id).delete()
                Sample.objects.filter(participant__user_id=user_id).delete()
                ServiceRequest.objects.filter(purchase__owner__django_user_id=user_id).delete()
                Purchase.objects.filter(owner__django_user_id=user_id).delete()
                Participant.objects.filter(user_id=user_id).delete()
                domain.DataRelease.objects.filter(pk__in=release_ids).delete()
                User.objects.filter(pk=user_id).delete()
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            user_id = pool.submit(create_target).result(timeout=10)
            try:
                outputs = list(pool.map(import_target, [user_id, user_id]))
                self.assertEqual(sum('already imported' in output for output in outputs), 1)
                self.assertEqual(sum('created' in output for output in outputs), 1)
                self.assertEqual(Participant.objects.filter(user_id=user_id).count(), 1)
                self.assertEqual(Purchase.objects.filter(owner__django_user_id=user_id).count(), 1)
                self.assertFalse(ServiceStatusLog.objects.filter(
                    request__purchase__owner__django_user_id=user_id,
                ).exists())
                self.assertEqual(Sample.objects.filter(participant__user_id=user_id).count(), 1)
                self.assertEqual(domain.AnalysisResult.objects.filter(participant__user_id=user_id).count(), 6)
            finally:
                pool.submit(remove_target, user_id).result(timeout=10)
        self.assertFalse(User.objects.filter(pk=user_id).exists())

    def test_command_and_bundle_import_without_queries_and_have_no_migration_drift(self):
        with self.assertNumQueries(0):
            reload(import_module('genoma.synthetic_import'))
            reload(import_module('genoma.management.commands.import_synthetic_genomics'))
        output = StringIO()
        call_command('makemigrations', check=True, dry_run=True, stdout=output)
        self.assertIn('No changes detected', output.getvalue())


class SyntheticGenomicsV2Tests(APITestCase):
    # Reuse the established guarded, isolated-db setup; do not inherit v1 tests.
    setUp = SyntheticGenomicsImportTests.setUp
    legacy_state = SyntheticGenomicsImportTests.legacy_state
    import_state = SyntheticGenomicsImportTests.import_state
    module_order = ('global_ancestry', 'local_ancestry', 'polygenic_risk',
                    'monogenic_risk', 'traits', 'pharmacogenetics')
    list_url = '/api/genoma/v1/services/'

    def v2_manifest(self):
        return {
            'demo_id': 'gdb-04f1-synthetic-genomics', 'demo_version': '2', 'schema_version': '2',
            'synthetic': True, 'non_clinical': True, 'clinically_reviewed': False,
            'display_only': True, 'numeric_semantics': 'arbitrary_demo_only_not_evaluated',
            'disclaimer': (
                'SYNTHETIC DEMO ONLY: fictional non-clinical display fixtures, not derived from a biological sample. '
                'All numeric values are arbitrary demo-only display fixtures and are not evaluated. '
                'No biological, risk, actionability, or clinical interpretation is provided. '
                'Not for diagnosis, treatment, or medical decisions. No clinical review or consent is implied.'
            ),
            'modules': [
                {'module': 'global_ancestry', 'label': 'Demo group A', 'state': 'not_evaluated',
                 'display': {'kind': 'fictional_components', 'components': [
                     {'label': 'Demo group A', 'display_percentage': 60},
                     {'label': 'Demo group B', 'display_percentage': 40},
                 ]}},
                {'module': 'local_ancestry', 'label': 'Demo group A', 'state': 'not_evaluated',
                 'display': {'kind': 'abstract_segments',
                             'axis': {'label': 'Demo axis A', 'extent': 100, 'unit': 'abstract_demo_units'},
                             'segments': [{'label': 'Demo group A', 'offset': 0, 'length': 60},
                                          {'label': 'Demo group B', 'offset': 60, 'length': 40}]}},
                {'module': 'polygenic_risk', 'label': 'Demo index A', 'state': 'not_evaluated',
                 'display': {'kind': 'demo_index', 'items': [{'label': 'Demo index A', 'display_value': 37}]}},
                {'module': 'monogenic_risk', 'label': 'Demo index A', 'state': 'not_evaluated',
                 'display': {'kind': 'demo_entries', 'items': [{'label': 'Demo index A', 'display_value': 12}]}},
                {'module': 'traits', 'label': 'Demo trait A', 'state': 'not_evaluated',
                 'display': {'kind': 'demo_traits', 'items': [{'label': 'Demo trait A', 'display_value': 24}]}},
                {'module': 'pharmacogenetics', 'label': 'Demo interaction A', 'state': 'not_evaluated',
                 'display': {'kind': 'demo_interactions',
                             'items': [{'label': 'Demo interaction A', 'display_value': 8}]}},
            ],
        }

    def import_demo(self, version='2', user=None):
        return bundle.import_synthetic_genomics(user_id=(user or self.user).pk, version=version)

    def paths(self, receipt):
        return tuple(f'{self.list_url}{receipt.service_request_id}/{suffix}/' for suffix in ('results', 'metrics'))

    def authenticate(self, user=None):
        self.client.force_authenticate(user=user or self.user)

    def assert_no_writes(self, queries):
        self.assertFalse(any(query['sql'].lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE'))
                             for query in queries.captured_queries))

    def test_management_command_defaults_to_version_two(self):
        output = StringIO()
        call_command('import_synthetic_genomics', '--user-id', str(self.user.pk), stdout=output)
        self.assertIn('v2: created', output.getvalue())
        self.assertIn('arbitrary demo-only', output.getvalue())
        self.assertEqual(domain.DataRelease.objects.get().version, '2')
        self.assertEqual(domain.AnalysisResult.objects.count(), 6)

    def test_v1_manifest_checksum_identifiers_payloads_and_python_default_are_exactly_immutable(self):
        disclaimer = (
            'SYNTHETIC DEMO ONLY: non-clinical placeholders, not derived from a biological sample. '
            'Not for diagnosis, treatment, or medical decisions. No clinical review or consent is implied.'
        )
        expected = {
            'demo_id': 'gdb-04f1-synthetic-genomics', 'demo_version': '1',
            'synthetic': True, 'non_clinical': True, 'clinically_reviewed': False, 'disclaimer': disclaimer,
            'modules': [{'module': module, 'label': f'Synthetic {module.replace("_", " ")} placeholder',
                         'state': 'not_evaluated', 'rows': [{
                             'label': f'Synthetic {module.replace("_", " ")} placeholder',
                             'state': 'not_evaluated', 'value': None,
                         }]} for module in self.module_order],
        }
        checksum = hashlib.sha256(json.dumps(expected, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        with patch('genoma.synthetic_import.Path.read_text', side_effect=AssertionError('v1 must not read v2')):
            demo = bundle.get_synthetic_bundle('1')
            receipt = bundle.import_synthetic_genomics(user_id=self.user.pk)
        self.assertEqual((bundle.DEMO_VERSION, bundle.DISCLAIMER, bundle.MANIFEST_CHECKSUM), ('1', disclaimer, checksum))
        self.assertEqual(demo.manifest, expected)
        self.assertEqual(demo.manifest_checksum, checksum)
        self.assertEqual(bundle.RELEASE_ID, uuid.uuid5(uuid.NAMESPACE_URL,
                         'genomia:gdb-04f1-synthetic-genomics:1:bundle:release'))
        scope = f'app-user:{self.user.app_user.pk}'
        for kind, identifier in (('purchase', receipt.purchase_id), ('request', receipt.service_request_id),
                                 ('sample', receipt.sample_id), ('participant', Participant.objects.get(user=self.user).pk)):
            self.assertEqual(identifier, uuid.uuid5(uuid.NAMESPACE_URL,
                             f'genomia:gdb-04f1-synthetic-genomics:1:{scope}:{kind}'))
        marker = {key: value for key, value in expected.items() if key != 'modules'}
        for module in expected['modules']:
            result = domain.AnalysisResult.objects.get(sample_id=receipt.sample_id, module=module['module'])
            self.assertEqual(result.pk, uuid.uuid5(uuid.NAMESPACE_URL,
                             f'genomia:gdb-04f1-synthetic-genomics:1:{scope}:result:{result.module}'))
            self.assertEqual(result.analysis_id, uuid.uuid5(uuid.NAMESPACE_URL,
                             f'genomia:gdb-04f1-synthetic-genomics:1:{scope}:analysis:{result.module}'))
            self.assertEqual({key: value for key, value in result.payload.items()
                              if key not in ('manifest_checksum', 'import_id')}, marker | module)

    def test_v2_packaged_fixture_schema_manifest_checksum_and_all_versioned_identifiers(self):
        fixture = Path(bundle.__file__).parent / 'fixtures' / 'synthetic_genomics_v2.json'
        expected = self.v2_manifest()
        self.assertEqual(json.loads(fixture.read_text(encoding='utf-8')), expected)
        with self.assertNumQueries(0):
            demo = bundle.get_synthetic_bundle('2')
        checksum = hashlib.sha256(json.dumps(expected, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        self.assertEqual(demo.manifest, expected)
        self.assertEqual(demo.manifest_checksum, checksum)
        self.assertNotEqual(checksum, bundle.MANIFEST_CHECKSUM)
        receipt = self.import_demo()
        scope = f'app-user:{self.user.app_user.pk}'
        ids = {kind: uuid.uuid5(uuid.NAMESPACE_URL, f'genomia:gdb-04f1-synthetic-genomics:2:{scope}:{kind}')
               for kind in ('import', 'participant', 'purchase', 'request', 'sample')}
        self.assertEqual((receipt.purchase_id, receipt.service_request_id, receipt.sample_id),
                         (ids['purchase'], ids['request'], ids['sample']))
        self.assertEqual(Participant.objects.get(user=self.user).pk, ids['participant'])
        release = domain.DataRelease.objects.get()
        self.assertEqual(release.pk, uuid.uuid5(uuid.NAMESPACE_URL,
                         'genomia:gdb-04f1-synthetic-genomics:2:bundle:release'))
        self.assertEqual((release.version, release.manifest_checksum, release.status, release.frozen_at),
                         ('2', checksum, 'synthetic', None))
        for result in domain.AnalysisResult.objects.all():
            for kind, identifier in (('result', result.pk), ('analysis', result.analysis_id)):
                self.assertEqual(identifier, uuid.uuid5(uuid.NAMESPACE_URL,
                                 f'genomia:gdb-04f1-synthetic-genomics:2:{scope}:{kind}:{result.module}'))
            self.assertEqual(result.payload['manifest_checksum'], checksum)
            self.assertEqual(result.payload['import_id'], str(ids['import']))

    def test_schema_rejects_unknown_fields_labels_bad_types_order_and_non_demo_semantics(self):
        valid = self.v2_manifest()
        invalid = [None, [], valid | {'owner_id': 'not-permitted'}, valid | {'synthetic': 1},
                   valid | {'non_clinical': False}, valid | {'clinically_reviewed': True},
                   valid | {'display_only': 1}, valid | {'numeric_semantics': 'evaluated'},
                   valid | {'schema_version': '1'}, valid | {'demo_version': '1'},
                   valid | {'modules': list(reversed(valid['modules']))}, valid | {'modules': valid['modules'][:5]}]
        for field, value in (('label', 'not-a-demo-label'), ('state', 'evaluated'), ('country', 'not-permitted')):
            changed = deepcopy(valid)
            changed['modules'][0][field] = value
            invalid.append(changed)
        for field, value in (('display_percentage', True), ('display_percentage', 60.0),
                             ('display_percentage', -1), ('display_percentage', 59),
                             ('population', 'not-permitted')):
            changed = deepcopy(valid)
            changed['modules'][0]['display']['components'][0][field] = value
            invalid.append(changed)
        for field, value in (('contig', 'not-permitted'), ('unit', 'physical'), ('extent', 0)):
            changed = deepcopy(valid)
            changed['modules'][1]['display']['axis'][field] = value
            invalid.append(changed)
        changed = deepcopy(valid)
        changed['modules'][1]['display']['segments'][1]['offset'] = 61
        invalid.append(changed)
        for index in range(2, 6):
            for field, value in (('display_value', False), ('display_value', 101), ('risk_category', 'not-permitted'),
                                 ('gene', 'not-permitted'), ('drug', 'not-permitted'), ('recommendation', 'not-permitted')):
                changed = deepcopy(valid)
                changed['modules'][index]['display']['items'][0][field] = value
                invalid.append(changed)
        for value in invalid:
            with self.subTest(value=value), patch('genoma.synthetic_import.Path.read_text', return_value=json.dumps(value)):
                with self.assertNumQueries(0), self.assertRaisesRegex(CommandError, 'schema'):
                    bundle.get_synthetic_bundle('2')
        raw = json.dumps(valid)[:-1] + ', "synthetic": true}'
        with patch('genoma.synthetic_import.Path.read_text', return_value=raw):
            with self.assertRaisesRegex(CommandError, 'schema'):
                bundle.get_synthetic_bundle('2')

    def test_valid_shaped_but_modified_fixture_and_unreadable_fixture_fail_closed_before_domain_queries(self):
        changed = self.v2_manifest()
        changed['modules'][2]['display']['items'][0]['display_value'] = 38
        for raw in (json.dumps(changed), '{invalid-json'):
            with self.subTest(raw=raw), patch('genoma.synthetic_import.Path.read_text', return_value=raw):
                with CaptureQueriesContext(connection) as queries, self.assertRaises(CommandError):
                    self.import_demo()
                self.assertEqual(len(queries), 1)  # Only actual local DB/server verification.
                self.assertTrue(queries[0]['sql'].startswith('SELECT current_database()'))
        with patch('genoma.synthetic_import.Path.read_text', side_effect=OSError('missing fixture')):
            with self.assertRaises(CommandError):
                self.import_demo()
        self.assertFalse(Purchase.objects.exists())

    def test_only_explicit_bundled_versions_are_accepted_and_no_caller_paths_are_supported(self):
        for value in (None, True, 1, 2, 'v2', '3', '../fixtures/arbitrary.json', '/arbitrary.json'):
            with self.subTest(value=value), self.assertNumQueries(0), self.assertRaises(CommandError):
                bundle.get_synthetic_bundle(value)
        for args in (('--demo-version', '3'), ('--demo-version', '../arbitrary.json'), ('--file', 'arbitrary.json')):
            with self.subTest(args=args), self.assertNumQueries(0), self.assertRaises(CommandError):
                call_command('import_synthetic_genomics', '--user-id', str(self.user.pk), *args, stdout=StringIO())

    def test_both_import_orders_preserve_existing_rows_consent_and_v1_reads_and_repeat_without_writes(self):
        self.authenticate()
        for versions in (('1', '2'), ('2', '1')):
            with self.subTest(versions=versions), transaction.atomic():
                first = self.import_demo(versions[0])
                first_path = self.paths(first)[0]
                first_body = self.client.get(first_path).json()
                sample = Sample.objects.get(pk=first.sample_id)
                participant_before = list(Participant.objects.filter(user=self.user).values())
                rows_before = {model: list(model.objects.filter(pk__in=keys).order_by('pk').values())
                               for model, keys in ((Purchase, [first.purchase_id]), (ServiceRequest, [first.service_request_id]),
                                                   (Sample, [first.sample_id]),
                                                   (domain.Analysis, domain.Analysis.objects.filter(sample=sample).values_list('pk', flat=True)),
                                                   (domain.AnalysisResult, domain.AnalysisResult.objects.filter(sample=sample).values_list('pk', flat=True)))}
                second = self.import_demo(versions[1])
                self.assertEqual(list(Participant.objects.filter(user=self.user).values()), participant_before)
                for model, expected in rows_before.items():
                    self.assertEqual(list(model.objects.filter(pk__in=[row[model._meta.pk.name] for row in expected])
                                          .order_by('pk').values()), expected)
                self.assertEqual(self.client.get(first_path).json(), first_body)
                before = self.import_state()
                with CaptureQueriesContext(connection) as queries:
                    for version in versions:
                        self.assertFalse(self.import_demo(version).created)
                self.assert_no_writes(queries)
                self.assertEqual(self.import_state(), before)
                services = self.client.get(self.list_url).json()['services']
                purchase_order = list(Purchase.objects.filter(
                    pk__in=(first.purchase_id, second.purchase_id),
                ).order_by('-purchased_at', '-created_at', '-pk').values_list('pk', flat=True))
                version_by_purchase = {first.purchase_id: versions[0], second.purchase_id: versions[1]}
                self.assertEqual([item['release_version'] for item in services], [
                    version_by_purchase[purchase_id] for purchase_id in purchase_order
                ])
                self.assertEqual({item['service_request_id'] for item in services},
                                 {str(first.service_request_id), str(second.service_request_id)})
                self.assertEqual(domain.DataRelease.objects.count(), 2)
                self.assertFalse(ServiceStatusLog.objects.exists())
                participant = Participant.objects.get(user=self.user)
                self.assertEqual((participant.consent_status, participant.enrollment_status), ('pending', 'pending'))
                transaction.set_rollback(True)

    def test_explicit_v1_command_is_compatible_and_existing_consent_is_never_granted_or_overwritten(self):
        participant = Participant.objects.create(user=self.user, participant_code='existing-v2-owner',
                                               consent_status='withdrawn', enrollment_status='inactive', metadata=['existing'])
        before = list(Participant.objects.values())
        output = StringIO()
        call_command('import_synthetic_genomics', '--user-id', str(self.user.pk), '--demo-version', '1', stdout=output)
        self.assertIn('v1: created', output.getvalue())
        self.import_demo()
        self.assertEqual(list(Participant.objects.values()), before)
        self.assertEqual(set(Sample.objects.values_list('participant_id', flat=True)), {participant.pk})

    def test_all_six_display_payloads_are_raw_demo_only_with_null_biological_columns_and_accurate_metrics(self):
        legacy = self.legacy_state()
        receipt = self.import_demo()
        self.authenticate()
        expected = self.v2_manifest()
        provenance = {key: value for key, value in expected.items() if key != 'modules'}
        before = self.import_state()
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(self.paths(receipt)[0])
        self.assertEqual(response.status_code, 200)
        self.assert_no_writes(queries)
        self.assertEqual(response.json()['release_version'], '2')
        self.assertEqual(response.json()['results'], [{
            'module': item['module'], 'result_type': 'synthetic_placeholder', 'value_code': 'SYNTHETIC_NOT_EVALUATED',
            'value_text': f'{item["label"]}. {expected["disclaimer"]}', 'payload': provenance | item,
        } for item in expected['modules']])
        self.assertEqual([row['module'] for row in response.json()['results']], list(self.module_order))
        self.assertEqual(sum(row['display_percentage'] for row in expected['modules'][0]['display']['components']), 100)
        for result in domain.AnalysisResult.objects.all():
            for field in ('variant_id', 'epigenetic_feature_id', 'population_id', 'reference_assembly',
                          'contig', 'start_pos', 'end_pos', 'haplotype', 'value_numeric', 'unit', 'percentile', 'confidence'):
                self.assertIsNone(getattr(result, field), field)
            self.assertEqual((result.analysis.status, result.analysis.pipeline_version), ('synthetic_placeholder', '2'))
            self.assertIsNone(result.analysis.started_at)
            self.assertIsNone(result.analysis.finished_at)
        with CaptureQueriesContext(connection) as metrics_queries:
            metrics_response = self.client.get(self.paths(receipt)[1])
        self.assertEqual(metrics_response.status_code, 200)
        self.assertEqual(metrics_response.json()['metrics'], {'kind': 'record_count', 'modules': [{
            'module': module, 'analysis_record_count': 1, 'analysis_synthetic_placeholder_record_count': 1,
            'analysis_result_record_count': 1, 'result_synthetic_placeholder_record_count': 1,
        } for module in self.module_order]})
        self.assertEqual([row['sql'] for row in queries], [row['sql'] for row in metrics_queries])
        self.assertEqual(self.import_state(), before)
        self.assertEqual(self.legacy_state(), legacy)
        self.assertFalse(ServiceRequest.objects.exclude(completed_at=None).exists())

    def test_display_and_api_exclude_forbidden_semantics_and_account_identifiers(self):
        receipt = self.import_demo()
        self.authenticate()
        forbidden = {'country', 'population', 'chromosome', 'contig', 'start_pos', 'end_pos', 'genotype', 'variant',
                     'rsid', 'disease', 'phenotype', 'gene', 'drug', 'risk_score', 'risk_category', 'treatment',
                     'recommendation', 'clinical_outcome', 'value_numeric', 'percentile', 'confidence',
                     'owner_id', 'user_id', 'userId', 'account_id', 'participant_id', 'participant_code',
                     'purchase_id', 'import_id', 'manifest_checksum', 'snp_count', 'total_variants'}

        def check(value):
            if isinstance(value, dict):
                self.assertTrue(forbidden.isdisjoint(value))
                for key, item in value.items():
                    if key == 'label':
                        self.assertIn(item, {'Demo group A', 'Demo group B', 'Demo axis A',
                                             'Demo index A', 'Demo trait A', 'Demo interaction A'})
                    check(item)
            elif isinstance(value, list):
                for item in value:
                    check(item)

        for path in (self.list_url, *self.paths(receipt)):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            check(response.json())
            for private in (self.user.username, str(self.user.app_user.pk), str(Participant.objects.get(user=self.user).pk)):
                self.assertNotIn(private, response.content.decode())

    def test_list_only_contains_imported_valid_owned_versions_and_detail_metrics_are_owner_only(self):
        first = self.import_demo('1')
        second = self.import_demo('2', self.other)
        empty = User.objects.create_user(username='v2-empty-owner')
        for user, expected in ((self.user, first), (self.other, second), (empty, None)):
            self.authenticate(user)
            services = self.client.get(self.list_url + f'?user_id={self.other.pk}&demo_version=2').json()['services']
            self.assertEqual([row['service_request_id'] for row in services],
                             [str(expected.service_request_id)] if expected else [])
            for receipt in (first, second):
                for path in self.paths(receipt):
                    response = self.client.get(path)
                    self.assertEqual(response.status_code, 200 if receipt == expected else 404)
                    if receipt != expected:
                        self.assertEqual(response.json(), {'detail': 'Not found.'})
        self.other.is_staff = self.other.is_superuser = True
        self.other.save(update_fields=['is_staff', 'is_superuser'])
        self.authenticate(self.other)
        self.assertEqual(self.client.get(self.paths(first)[0]).status_code, 404)
        for grant in (grant_admin_role, grant_analyst_role, grant_reception_role):
            grant(self.other)
            self.assertEqual(self.client.get(self.list_url).json(), {'services': []})
            for path in (*self.paths(first), *self.paths(second)):
                self.assertEqual(self.client.get(path).status_code, 404)

    def test_partial_corrupt_duplicate_and_cross_account_graphs_are_hidden_and_not_repaired(self):
        first = self.import_demo('1')
        second = self.import_demo()
        other = self.import_demo(user=self.other)
        self.authenticate()
        sample = Sample.objects.get(pk=second.sample_id)
        result = domain.AnalysisResult.objects.get(sample=sample, module='global_ancestry')
        changed_display = deepcopy(result.payload)
        changed_display['display']['components'][0]['display_percentage'] = 61
        scenarios = (
            (Purchase, second.purchase_id, {'owner': self.other.app_user}),
            (ServiceRequest, second.service_request_id, {'participant': Sample.objects.get(pk=other.sample_id).participant}),
            (Sample, sample.pk, {'metadata': sample.metadata | {'synthetic': 1}}),
            (domain.Analysis, result.analysis_id, {'status': 'completed'}),
            (domain.AnalysisResult, result.pk, {'payload': changed_display}),
            (domain.AnalysisResult, result.pk, {'payload': result.payload | {'clinically_reviewed': 0}}),
            (domain.AnalysisResult, result.pk, {'value_numeric': 1}),
            (domain.DataRelease, result.release_id, {'manifest_checksum': '0' * 64}),
        )
        for model, pk, changes in scenarios:
            with self.subTest(changes=changes), transaction.atomic():
                model.objects.filter(pk=pk).update(**changes)
                before = self.import_state()
                with CaptureQueriesContext(connection) as queries, self.assertRaises(CommandError):
                    self.import_demo()
                self.assert_no_writes(queries)
                for path in self.paths(second):
                    self.assertEqual(self.client.get(path).status_code, 404)
                self.assertEqual([row['release_version'] for row in self.client.get(self.list_url).json()['services']], ['1'])
                self.assertEqual(self.client.get(self.paths(first)[0]).status_code, 200)
                self.assertEqual(self.import_state(), before)
                transaction.set_rollback(True)
        for duplicate in (False, True):
            with self.subTest(duplicate=duplicate), transaction.atomic():
                if duplicate:
                    row = domain.AnalysisResult.objects.get(pk=result.pk)
                    row.pk = uuid.uuid4()
                    row.save(force_insert=True)
                else:
                    domain.AnalysisResult.objects.filter(pk=result.pk).delete()
                before = self.import_state()
                with CaptureQueriesContext(connection) as queries, self.assertRaises(CommandError):
                    self.import_demo()
                self.assert_no_writes(queries)
                for path in self.paths(second):
                    self.assertEqual(self.client.get(path).status_code, 404)
                self.assertEqual(self.import_state(), before)
                transaction.set_rollback(True)

    def test_v2_seeded_participant_provenance_corruption_is_hidden_without_repairing_consent(self):
        receipt = self.import_demo()
        self.authenticate()
        participant = Participant.objects.get(user=self.user)
        for changes in ({'metadata': participant.metadata | {'synthetic': 1}},
                        {'participant_code': 'NOT-THE-SEEDED-DEMO-PARTICIPANT'}):
            with self.subTest(changes=changes), transaction.atomic():
                Participant.objects.filter(pk=participant.pk).update(**changes)
                before = self.import_state()
                with CaptureQueriesContext(connection) as queries, self.assertRaises(CommandError):
                    self.import_demo()
                self.assert_no_writes(queries)
                for path in self.paths(receipt):
                    self.assertEqual(self.client.get(path).status_code, 404)
                self.assertEqual(self.client.get(self.list_url).json(), {'services': []})
                self.assertEqual(self.import_state(), before)
                transaction.set_rollback(True)

    def test_v2_guard_precedes_all_domain_queries_for_command_list_detail_and_metrics(self):
        receipt = self.import_demo()
        self.authenticate()
        with patch.object(bundle, '_require_local_development', side_effect=CommandError(bundle.LOCAL_ONLY)) as guard:
            for path in (self.list_url, *self.paths(receipt), f'{self.list_url}unknown/results/'):
                with self.assertNumQueries(0):
                    self.assertEqual(self.client.get(path).status_code, 404)
            with self.assertNumQueries(0), self.assertRaisesRegex(CommandError, 'local development'):
                call_command('import_synthetic_genomics', '--user-id', str(self.user.pk), stdout=StringIO())
            self.assertEqual(guard.call_count, 5)
        self.client.force_authenticate(user=None)
        for path in (self.list_url, *self.paths(receipt)):
            with self.assertNumQueries(0):
                self.assertIn(self.client.get(path).status_code, (401, 403))

    def test_v2_profile_and_shared_service_status_do_not_change(self):
        domain.Variant.objects.create(variant_type='synthetic', canonical_name='Preserved normalized row')
        Profile.objects.create(user=self.user)
        self.import_demo('1')
        self.authenticate()
        paths = ('/api/auth/me/',)
        responses = [(self.client.get(path).status_code, self.client.get(path).json()) for path in paths]
        legacy = self.legacy_state()
        receipt = self.import_demo()
        for path in (self.list_url, *self.paths(receipt)):
            self.assertEqual(self.client.get(path).status_code, 200)
        self.assertEqual([(self.client.get(path).status_code, self.client.get(path).json()) for path in paths], responses)
        self.assertEqual(self.legacy_state(), legacy)
        grant_admin_role(self.other)
        self.authenticate(self.other)
        with self.assertNumQueries(0):
            self.assertEqual(self.client.get(f'/api/ingest/user-report-status/{self.user.pk}/').status_code, 404)


class ArtifactSchemaTests(TestCase):
    def setUp(self):
        self.assertTrue(connection.settings_dict['NAME'].startswith('gdb_test_'))
        from participants.models import Participant
        self.user = User.objects.create_user(username=f'artifact-{uuid.uuid4().hex}')
        self.participant = Participant.objects.create(
            user=self.user, participant_code=f'artifact-{uuid.uuid4().hex}',
        )
        self.release = domain.DataRelease.objects.create(
            name=uuid.uuid4().hex, version='v1', status='unlisted', reference_assembly='synthetic',
        )
        self.analysis = domain.Analysis.objects.create(
            module='synthetic', pipeline_name='artifact-pipeline', pipeline_version='v1', status='unlisted',
        )
        request = ServiceRequest.objects.create(
            purchase=Purchase.objects.create(owner=self.user.app_user), participant=self.participant,
            status=RequestStatus.objects.get(code='WAITING_SAMPLE'),
        )
        self.sample = Sample.objects.create(
            service_request=request, participant=self.participant,
            sample_code=f'artifact-{uuid.uuid4().hex}', sample_type='synthetic',
        )

    def artifact(self, **changes):
        self.assertTrue(hasattr(domain, 'Artifact'), 'Artifact schema model is missing.')
        values = {
            'role': 'input', 'artifact_type': 'vcf', 'format': 'vcf.gz',
            'uri': 'object://synthetic/artifact.vcf.gz', 'checksum_sha256': 'a' * 64,
        }
        return domain.Artifact(**(values | changes))

    def test_exact_physical_columns_custom_char_jsonb_and_only_two_declared_indexes(self):
        self.assertTrue(hasattr(domain, 'Artifact'), 'Artifact schema model is missing.')
        columns = {
            'artifact_id': ('uuid', None, 'NO', None),
            'analysis_id': ('uuid', None, 'YES', None),
            'release_id': ('uuid', None, 'YES', None),
            'sample_id': ('uuid', None, 'YES', None),
            'role': ('character varying', 32, 'NO', None),
            'artifact_type': ('character varying', 64, 'NO', None),
            'format': ('character varying', 64, 'NO', None),
            'uri': ('text', None, 'NO', None),
            'checksum_sha256': ('character', 64, 'NO', None),
            'size_bytes': ('bigint', None, 'YES', None),
            'reference_assembly': ('character varying', 32, 'YES', None),
            'metadata': ('jsonb', None, 'YES', None),
            'created_at': ('timestamp with time zone', None, 'NO', 'CURRENT_TIMESTAMP'),
        }
        with connection.cursor() as cursor:
            cursor.execute(
                'SELECT column_name, data_type, character_maximum_length, is_nullable, column_default '
                'FROM information_schema.columns WHERE table_schema = current_schema() '
                "AND table_name = 'artifact' ORDER BY ordinal_position"
            )
            physical_columns = cursor.fetchall()
            constraints = connection.introspection.get_constraints(cursor, 'artifact')
            cursor.execute(
                'SELECT indexname, indexdef FROM pg_indexes '
                'WHERE schemaname = current_schema() AND tablename = %s', ['artifact'],
            )
            index_definitions = dict(cursor.fetchall())
            cursor.execute(
                'SELECT conname, confdeltype, confupdtype, condeferrable, condeferred '
                'FROM pg_constraint WHERE conrelid = %s::regclass AND contype = %s', ['artifact', 'f'],
            )
            fk_actions = {row[0]: row[1:] for row in cursor.fetchall()}
        self.assertEqual(physical_columns, [(name, *spec) for name, spec in columns.items()])
        model = domain.Artifact
        self.assertEqual((model._meta.db_table, model._meta.pk.name), ('artifact', 'artifact_id'))
        self.assertEqual([field.column for field in model._meta.local_fields], list(columns))
        self.assertEqual(
            {field.name for field in model._meta.local_fields},
            {'artifact_id', 'analysis', 'release', 'sample', 'role', 'artifact_type', 'format', 'uri',
             'checksum_sha256', 'size_bytes', 'reference_assembly', 'metadata', 'created_at'},
        )
        for field in model._meta.local_fields:
            nullable = columns[field.column][2] == 'YES'
            self.assertEqual((field.null, field.blank), (nullable, nullable))
        self.assertEqual(model._meta.get_field('uri').get_internal_type(), 'TextField')
        self.assertNotIsInstance(model._meta.get_field('uri'), models.FileField)
        self.assertEqual((model._meta.get_field('checksum_sha256').max_length,
                          model._meta.get_field('checksum_sha256').db_type(connection)), (64, 'char(64)'))
        self.assertIsInstance(model._meta.get_field('created_at').db_default, TransactionNow)
        self.assertEqual(
            {index.name: index.fields for index in model._meta.indexes},
            {'idx_artifact_analysis': ['analysis'], 'idx_artifact_checksum': ['checksum_sha256']},
        )
        self.assertEqual(set(index_definitions), {
            'artifact_pkey', 'idx_artifact_analysis', 'idx_artifact_checksum',
        })
        self.assertIn('(analysis_id)', index_definitions['idx_artifact_analysis'])
        self.assertIn('(checksum_sha256)', index_definitions['idx_artifact_checksum'])
        self.assertEqual({constraint.name for constraint in model._meta.constraints},
                         {'artifact_size_bytes_gte_0'})
        self.assertEqual(set(constraints), {
            'artifact_pkey', 'artifact_size_bytes_gte_0', 'idx_artifact_analysis', 'idx_artifact_checksum',
            'fk_artifact_analysis', 'fk_artifact_release', 'fk_artifact_sample',
        })
        self.assertEqual(
            {name: (info['columns'], info['foreign_key']) for name, info in constraints.items()
             if info['foreign_key']},
            {
                'fk_artifact_analysis': (['analysis_id'], ('analysis', 'analysis_id')),
                'fk_artifact_release': (['release_id'], ('data_release', 'release_id')),
                'fk_artifact_sample': (['sample_id'], ('sample', 'sample_id')),
            },
        )
        self.assertEqual(fk_actions, {
            'fk_artifact_analysis': ('n', 'c', False, False),
            'fk_artifact_release': ('n', 'c', False, False),
            'fk_artifact_sample': ('n', 'c', False, False),
        })
        for field_name, target, target_key in (
            ('analysis', domain.Analysis, 'analysis_id'),
            ('release', domain.DataRelease, 'release_id'),
            ('sample', Sample, 'sample_id'),
        ):
            field = model._meta.get_field(field_name)
            self.assertIs(field.remote_field.model, target)
            self.assertIs(field.remote_field.on_delete, SET_NULL)
            self.assertEqual((field.column, field.target_field.name, field.db_index, field.db_constraint),
                             (field_name + '_id', target_key, False, True))

    def test_database_defaults_nullable_metadata_and_uri_remain_storage_metadata(self):
        self.assertTrue(hasattr(domain, 'Artifact'), 'Artifact schema model is missing.')
        identifier = uuid.uuid4()
        checksum = 'b' * 64
        with connection.cursor() as cursor:
            cursor.execute(
                'INSERT INTO artifact (artifact_id, role, artifact_type, format, uri, checksum_sha256) '
                'VALUES (%s, %s, %s, %s, %s, %s) '
                'RETURNING analysis_id, release_id, sample_id, size_bytes, metadata, created_at, '
                'transaction_timestamp(), pg_typeof(metadata)',
                [identifier, 'manifest', 'opaque', 'unknown', 'object://synthetic/manifest', checksum],
            )
            row = cursor.fetchone()
        self.assertEqual(row[:5], (None, None, None, None, None))
        self.assertEqual(row[5], row[6])
        self.assertEqual(row[7], 'jsonb')
        self.assertTrue(domain.Artifact.objects.filter(pk=identifier, uri='object://synthetic/manifest').exists())
        defaulted = self.artifact(analysis=self.analysis, release=self.release, sample=self.sample,
                                  size_bytes=0, metadata={'synthetic': True})
        created = defaulted.created_at
        self.assertIsInstance(defaulted.pk, uuid.UUID)
        self.assertTrue(timezone.is_aware(created))
        self.assertIs(domain.Artifact._meta.get_field('artifact_id').default, uuid.uuid4)
        self.assertIs(domain.Artifact._meta.get_field('created_at').default, timezone.now)
        defaulted.full_clean()
        defaulted.save()
        defaulted.refresh_from_db()
        self.assertEqual(defaulted.created_at, created)
        self.assertEqual(defaulted.metadata, {'synthetic': True})
        duplicate_checksum = self.artifact(checksum_sha256='a' * 64)
        duplicate_checksum.save()
        self.assertEqual(domain.Artifact.objects.filter(checksum_sha256='a' * 64).count(), 2)

    def test_nullable_nonnegative_size_and_only_declared_check(self):
        self.assertTrue(hasattr(domain, 'Artifact'), 'Artifact schema model is missing.')
        self.artifact(size_bytes=None).save()
        self.artifact(size_bytes=0).save()
        invalid = self.artifact(size_bytes=-1)
        with self.assertRaises(ValidationError):
            invalid.full_clean()
        with self.assertRaises(IntegrityError) as error, transaction.atomic():
            invalid.save(force_insert=True)
        self.assertEqual(error.exception.__cause__.diag.constraint_name, 'artifact_size_bytes_gte_0')

    def test_raw_updates_cascade_analysis_release_and_sample_keys(self):
        self.assertTrue(hasattr(domain, 'Artifact'), 'Artifact schema model is missing.')
        artifact = self.artifact(analysis=self.analysis, release=self.release, sample=self.sample)
        artifact.save()
        parents = (
            ('analysis', self.analysis, domain.Analysis, 'analysis_id'),
            ('release', self.release, domain.DataRelease, 'release_id'),
            ('sample', self.sample, Sample, 'sample_id'),
        )
        with connection.cursor() as cursor:
            for relation, parent, model, key in parents:
                new_id = uuid.uuid4()
                table = connection.ops.quote_name(model._meta.db_table)
                column = connection.ops.quote_name(key)
                cursor.execute(f'UPDATE {table} SET {column} = %s WHERE {column} = %s', [new_id, parent.pk])
                parent.pk = new_id
                artifact.refresh_from_db()
                self.assertEqual(getattr(artifact, relation + '_id'), new_id)

    def test_raw_deletes_set_each_optional_reference_null(self):
        self.assertTrue(hasattr(domain, 'Artifact'), 'Artifact schema model is missing.')
        artifact = self.artifact(analysis=self.analysis, release=self.release, sample=self.sample)
        artifact.save()
        for relation, table, key, value in (
            ('analysis', 'analysis', 'analysis_id', self.analysis.pk),
            ('release', 'data_release', 'release_id', self.release.pk),
            ('sample', 'sample', 'sample_id', self.sample.pk),
        ):
            with connection.cursor() as cursor:
                cursor.execute(
                    f'DELETE FROM {connection.ops.quote_name(table)} WHERE {connection.ops.quote_name(key)} = %s',
                    [value],
                )
            artifact.refresh_from_db()
            self.assertIsNone(getattr(artifact, relation + '_id'))
        self.assertTrue(domain.Artifact.objects.filter(pk=artifact.pk).exists())

    def test_orm_reverse_relations_and_delete_policy_keep_artifact_metadata(self):
        self.assertTrue(hasattr(domain, 'Artifact'), 'Artifact schema model is missing.')
        artifact = self.artifact(analysis=self.analysis, release=self.release, sample=self.sample)
        artifact.save()
        for parent in (self.analysis, self.release, self.sample):
            self.assertEqual(list(parent.artifacts.all()), [artifact])
        for parent, relation in (
            (self.analysis, 'analysis_id'), (self.release, 'release_id'), (self.sample, 'sample_id'),
        ):
            parent.delete()
            artifact.refresh_from_db()
            self.assertIsNone(getattr(artifact, relation))
        self.assertEqual(domain.Artifact.objects.get(pk=artifact.pk).uri, 'object://synthetic/artifact.vcf.gz')

    def test_migration_state_matches_model_and_has_no_dependency_cycle(self):
        self.assertTrue(hasattr(domain, 'Artifact'), 'Artifact schema model is missing.')
        migration = normalized_migration_slice('Artifact')
        self.assertEqual(migration.dependencies, normalized_dependencies('Artifact'))
        loader = MigrationLoader(connection, replace_migrations=False)
        state = loader.project_state([NORMALIZED_LEAF])
        historical = state.apps.get_model('genoma', 'Artifact')
        self.assertEqual(
            {field.name: field.deconstruct()[1:] for field in historical._meta.local_fields},
            {field.name: field.deconstruct()[1:] for field in domain.Artifact._meta.local_fields},
        )
        self.assertEqual(historical._meta.indexes, domain.Artifact._meta.indexes)
        self.assertEqual(historical._meta.constraints, domain.Artifact._meta.constraints)
        self.assertIn(NORMALIZED_INITIAL, loader.graph.forwards_plan(NORMALIZED_LEAF))


class ArtifactMigrationTests(TransactionTestCase):
    def fk_actions(self):
        with connection.cursor() as cursor:
            cursor.execute(
                'SELECT conname, confdeltype, confupdtype, condeferrable, condeferred '
                'FROM pg_constraint WHERE conrelid = %s::regclass AND contype = %s', ['artifact', 'f'],
            )
            return {row[0]: row[1:] for row in cursor.fetchall()}

    def test_fk_reverse_restores_deferred_no_action_and_forward_is_physical(self):
        self.assertTrue(hasattr(domain, 'Artifact'), 'Artifact schema model is missing.')
        migration = import_module('genoma.migrations.0014_artifact')
        editor = connection.SchemaEditorClass(connection)
        with transaction.atomic():
            migration.restore_artifact_fks(None, editor)
            self.assertEqual(self.fk_actions(), {
                name: ('a', 'a', True, True) for name in (
                    'fk_artifact_analysis', 'fk_artifact_release', 'fk_artifact_sample',
                )
            })
            migration.replace_artifact_fks(None, editor, physical=True)
            self.assertEqual(self.fk_actions(), {
                'fk_artifact_analysis': ('n', 'c', False, False),
                'fk_artifact_release': ('n', 'c', False, False),
                'fk_artifact_sample': ('n', 'c', False, False),
            })
        self.assertIs(normalized_migration_slice('Artifact').operations[-1].reverse_code,
                      migration.restore_artifact_fks)

    def test_fk_lookup_failure_does_not_partially_replace_constraints(self):
        self.assertTrue(hasattr(domain, 'Artifact'), 'Artifact schema model is missing.')
        migration = import_module('genoma.migrations.0014_artifact')
        editor = connection.SchemaEditorClass(connection)
        with transaction.atomic():
            try:
                with connection.cursor() as cursor:
                    cursor.execute('ALTER TABLE artifact DROP CONSTRAINT fk_artifact_release')
                before = self.fk_actions()
                with self.assertRaisesRegex(RuntimeError, 'artifact.release_id -> data_release.release_id'):
                    migration.replace_artifact_fks(None, editor, physical=True)
                self.assertEqual(self.fk_actions(), before)
            finally:
                transaction.set_rollback(True)


class AnalysisResultSchemaTests(TestCase):
    def setUp(self):
        self.assertTrue(connection.settings_dict['NAME'].startswith('gdb_test_'))
        from participants.models import Participant

        self.user = User.objects.create_user(username=f'result-{uuid.uuid4().hex}')
        self.participant = Participant.objects.create(
            user=self.user, participant_code=f'result-{uuid.uuid4().hex}',
        )
        self.isolated_participant = Participant.objects.create(
            user=User.objects.create_user(username=f'result-isolated-{uuid.uuid4().hex}'),
            participant_code=f'result-isolated-{uuid.uuid4().hex}',
        )
        self.purchase = Purchase.objects.create(owner=self.user.app_user)
        self.request = ServiceRequest.objects.create(
            purchase=self.purchase, participant=self.participant,
            status=RequestStatus.objects.get(code='WAITING_SAMPLE'),
        )
        self.sample = Sample.objects.create(
            service_request=self.request, participant=self.participant,
            sample_code=f'result-{uuid.uuid4().hex}', sample_type='synthetic',
        )
        self.release = domain.DataRelease.objects.create(
            name=uuid.uuid4().hex, version='v1', status='unlisted', reference_assembly='synthetic',
        )
        self.analysis = domain.Analysis.objects.create(
            module='synthetic', pipeline_name='result-pipeline', pipeline_version='v1', status='unlisted',
        )
        self.variant = domain.Variant.objects.create(variant_type='synthetic')
        self.epigenetic_feature = domain.EpigeneticFeature.objects.create(
            feature_type='synthetic', reference_assembly='synthetic', contig='chr1', start_pos=1, end_pos=1,
        )
        self.population = domain.Population.objects.create(
            code=uuid.uuid4().hex, name='Synthetic population',
        )

    def result(self, **changes):
        self.assertTrue(hasattr(domain, 'AnalysisResult'), 'AnalysisResult schema model is missing.')
        values = {'analysis': self.analysis, 'module': 'synthetic', 'result_type': 'summary'}
        return domain.AnalysisResult(**(values | changes))

    def insert_raw(self, **values):
        columns = ['result_id', 'analysis_id', 'module', 'result_type', *values]
        parameters = [uuid.uuid4(), self.analysis.pk, 'synthetic', 'summary', *values.values()]
        with connection.cursor() as cursor:
            cursor.execute(
                f"INSERT INTO analysis_result ({', '.join(columns)}) "
                f"VALUES ({', '.join(['%s'] * len(columns))})",
                parameters,
            )

    def assert_check_rejects(self, fields, constraint_name):
        with self.assertRaises(IntegrityError) as error, transaction.atomic():
            self.insert_raw(**fields)
        self.assertEqual(error.exception.__cause__.diag.constraint_name, constraint_name)

    def test_exact_physical_columns_precision_indexes_checks_and_fk_actions(self):
        self.assertTrue(hasattr(domain, 'AnalysisResult'), 'AnalysisResult schema model is missing.')
        columns = {
            'result_id': ('uuid', None, None, None, 'NO', None),
            'analysis_id': ('uuid', None, None, None, 'NO', None),
            'participant_id': ('uuid', None, None, None, 'YES', None),
            'sample_id': ('uuid', None, None, None, 'YES', None),
            'release_id': ('uuid', None, None, None, 'YES', None),
            'variant_id': ('uuid', None, None, None, 'YES', None),
            'epigenetic_feature_id': ('uuid', None, None, None, 'YES', None),
            'population_id': ('uuid', None, None, None, 'YES', None),
            'module': ('character varying', 64, None, None, 'NO', None),
            'result_type': ('character varying', 96, None, None, 'NO', None),
            'reference_assembly': ('character varying', 32, None, None, 'YES', None),
            'contig': ('character varying', 64, None, None, 'YES', None),
            'start_pos': ('bigint', None, 64, 0, 'YES', None),
            'end_pos': ('bigint', None, 64, 0, 'YES', None),
            'haplotype': ('smallint', None, 16, 0, 'YES', None),
            'value_numeric': ('numeric', None, 20, 10, 'YES', None),
            'value_text': ('text', None, None, None, 'YES', None),
            'value_code': ('character varying', 128, None, None, 'YES', None),
            'unit': ('character varying', 64, None, None, 'YES', None),
            'percentile': ('numeric', None, 7, 4, 'YES', None),
            'confidence': ('numeric', None, 7, 6, 'YES', None),
            'payload': ('jsonb', None, None, None, 'YES', None),
            'created_at': ('timestamp with time zone', None, None, None, 'NO', 'CURRENT_TIMESTAMP'),
        }
        check_names = {
            'analysis_result_start_pos_gte_1', 'analysis_result_end_pos_gte_start',
            'analysis_result_haplotype_gte_0', 'analysis_result_percentile_0_100',
            'analysis_result_confidence_0_1',
        }
        with connection.cursor() as cursor:
            cursor.execute(
                'SELECT column_name, data_type, character_maximum_length, numeric_precision, numeric_scale, '
                'is_nullable, column_default FROM information_schema.columns '
                'WHERE table_schema = current_schema() AND table_name = %s ORDER BY ordinal_position',
                ['analysis_result'],
            )
            physical_columns = cursor.fetchall()
            constraints = connection.introspection.get_constraints(cursor, 'analysis_result')
            cursor.execute(
                'SELECT indexname, indexdef FROM pg_indexes '
                'WHERE schemaname = current_schema() AND tablename = %s', ['analysis_result'],
            )
            index_definitions = dict(cursor.fetchall())
            cursor.execute(
                'SELECT conname, confdeltype, confupdtype, condeferrable, condeferred '
                'FROM pg_constraint WHERE conrelid = %s::regclass AND contype = %s',
                ['analysis_result', 'f'],
            )
            fk_actions = {row[0]: row[1:] for row in cursor.fetchall()}
        self.assertEqual(physical_columns, [(name, *spec) for name, spec in columns.items()])
        model = domain.AnalysisResult
        self.assertEqual((model._meta.db_table, model._meta.pk.name), ('analysis_result', 'result_id'))
        self.assertEqual([field.column for field in model._meta.local_fields], list(columns))
        self.assertEqual(
            {field.name for field in model._meta.local_fields},
            {'result_id', 'analysis', 'participant', 'sample', 'release', 'variant', 'epigenetic_feature',
             'population', 'module', 'result_type', 'reference_assembly', 'contig', 'start_pos', 'end_pos',
             'haplotype', 'value_numeric', 'value_text', 'value_code', 'unit', 'percentile', 'confidence',
             'payload', 'created_at'},
        )
        for field in model._meta.local_fields:
            self.assertEqual(field.null, columns[field.column][4] == 'YES')
            if field.column != 'result_id':
                self.assertEqual(field.blank, field.null)
        self.assertEqual(
            [(model._meta.get_field(name).max_digits, model._meta.get_field(name).decimal_places)
             for name in ('value_numeric', 'percentile', 'confidence')],
            [(20, 10), (7, 4), (7, 6)],
        )
        self.assertEqual(
            {index.name: index.fields for index in model._meta.indexes},
            {
                'idx_result_participant_module': ['participant', 'module'],
                'idx_result_analysis': ['analysis'],
                'idx_result_interval': ['reference_assembly', 'contig', 'start_pos', 'end_pos'],
            },
        )
        self.assertEqual(set(index_definitions), {
            'analysis_result_pkey', 'idx_result_participant_module', 'idx_result_analysis', 'idx_result_interval',
        })
        for name, columns_sql in (
            ('idx_result_participant_module', '(participant_id, module)'),
            ('idx_result_analysis', '(analysis_id)'),
            ('idx_result_interval', '(reference_assembly, contig, start_pos, end_pos)'),
        ):
            self.assertIn(columns_sql, index_definitions[name])
        self.assertEqual({constraint.name for constraint in model._meta.constraints}, check_names)
        fk_names = {
            'fk_result_analysis', 'fk_result_participant', 'fk_result_sample', 'fk_result_release',
            'fk_result_variant', 'fk_result_epigenetic_feature', 'fk_result_population',
        }
        self.assertEqual(set(constraints), {'analysis_result_pkey', *check_names, *fk_names,
                                            'idx_result_participant_module', 'idx_result_analysis',
                                            'idx_result_interval'})
        targets = {
            'fk_result_analysis': ('analysis_id', ('analysis', 'analysis_id')),
            'fk_result_participant': ('participant_id', ('participant', 'participant_id')),
            'fk_result_sample': ('sample_id', ('sample', 'sample_id')),
            'fk_result_release': ('release_id', ('data_release', 'release_id')),
            'fk_result_variant': ('variant_id', ('variant', 'variant_id')),
            'fk_result_epigenetic_feature': ('epigenetic_feature_id', ('epigenetic_feature', 'epigenetic_feature_id')),
            'fk_result_population': ('population_id', ('population', 'population_id')),
        }
        self.assertEqual(
            {name: (info['columns'], info['foreign_key']) for name, info in constraints.items()
             if info['foreign_key']},
            {name: ([column], target) for name, (column, target) in targets.items()},
        )
        self.assertEqual(fk_actions, {
            'fk_result_analysis': ('r', 'c', False, False),
            **{name: ('n', 'c', False, False) for name in fk_names - {'fk_result_analysis'}},
        })
        relations = (
            ('analysis', domain.Analysis, 'analysis_id', PROTECT, False),
            ('participant', self.participant.__class__, 'participant_id', SET_NULL, True),
            ('sample', Sample, 'sample_id', SET_NULL, True),
            ('release', domain.DataRelease, 'release_id', SET_NULL, True),
            ('variant', domain.Variant, 'variant_id', SET_NULL, True),
            ('epigenetic_feature', domain.EpigeneticFeature, 'epigenetic_feature_id', SET_NULL, True),
            ('population', domain.Population, 'population_id', SET_NULL, True),
        )
        for relation, target, column, on_delete, nullable in relations:
            field = model._meta.get_field(relation)
            self.assertIs(field.remote_field.model, target)
            self.assertIs(field.remote_field.on_delete, on_delete)
            self.assertEqual((field.column, field.target_field.name, field.null, field.db_index, field.db_constraint),
                             (column, column, nullable, False, True))

    def test_database_defaults_nullable_values_and_unpaired_interval_are_preserved(self):
        self.assertTrue(hasattr(domain, 'AnalysisResult'), 'AnalysisResult schema model is missing.')
        result = self.result()
        self.assertIsInstance(result.pk, uuid.UUID)
        created = result.created_at
        self.assertIsInstance(domain.AnalysisResult._meta.get_field('result_id').default, type(uuid.uuid4))
        self.assertIs(domain.AnalysisResult._meta.get_field('created_at').default, timezone.now)
        self.assertTrue(timezone.is_aware(created))
        with connection.cursor() as cursor:
            cursor.execute(
                'INSERT INTO analysis_result (result_id, analysis_id, module, result_type) '
                'VALUES (%s, %s, %s, %s) RETURNING participant_id, sample_id, release_id, variant_id, '
                'epigenetic_feature_id, population_id, reference_assembly, contig, start_pos, end_pos, '
                'haplotype, value_numeric, value_text, value_code, unit, percentile, confidence, payload, '
                'created_at, transaction_timestamp(), pg_typeof(payload)',
                [uuid.uuid4(), self.analysis.pk, 'synthetic', 'nullable'],
            )
            row = cursor.fetchone()
        self.assertEqual(row[:18], (None,) * 18)
        self.assertEqual(row[18], row[19])
        self.assertEqual(row[20], 'jsonb')
        self.insert_raw(start_pos=None, end_pos=5, percentile=Decimal('100.0000'), confidence=Decimal('1.000000'))
        values = self.result(
            reference_assembly='synthetic', contig='chr1', start_pos=None, end_pos=5, haplotype=0,
            value_numeric=Decimal('12.3400000000'), value_text='synthetic', value_code='SYN',
            unit='unit', percentile=Decimal('100.0000'), confidence=Decimal('1.000000'), payload={'synthetic': True},
        )
        values.save()
        values.refresh_from_db()
        self.assertEqual(values.payload, {'synthetic': True})
        self.assertEqual(values.end_pos, 5)

    def test_only_declared_position_haplotype_percentile_and_confidence_checks_apply(self):
        self.assertTrue(hasattr(domain, 'AnalysisResult'), 'AnalysisResult schema model is missing.')
        for fields, constraint in (
            ({'start_pos': 0}, 'analysis_result_start_pos_gte_1'),
            ({'start_pos': 1, 'end_pos': 0}, 'analysis_result_end_pos_gte_start'),
            ({'haplotype': -1}, 'analysis_result_haplotype_gte_0'),
            ({'percentile': Decimal('-0.0001')}, 'analysis_result_percentile_0_100'),
            ({'percentile': Decimal('100.0001')}, 'analysis_result_percentile_0_100'),
            ({'confidence': Decimal('-0.000001')}, 'analysis_result_confidence_0_1'),
            ({'confidence': Decimal('1.000001')}, 'analysis_result_confidence_0_1'),
        ):
            self.assert_check_rejects(fields, constraint)

    def test_raw_parent_key_updates_cascade_across_all_seven_foreign_keys(self):
        self.assertTrue(hasattr(domain, 'AnalysisResult'), 'AnalysisResult schema model is missing.')
        result = self.result(
            participant=self.isolated_participant, sample=self.sample, release=self.release, variant=self.variant,
            epigenetic_feature=self.epigenetic_feature, population=self.population,
        )
        result.save()
        parents = (
            ('analysis', self.analysis, domain.Analysis, 'analysis_id'),
            ('participant', self.isolated_participant, self.isolated_participant.__class__, 'participant_id'),
            ('sample', self.sample, Sample, 'sample_id'),
            ('release', self.release, domain.DataRelease, 'release_id'),
            ('variant', self.variant, domain.Variant, 'variant_id'),
            ('epigenetic_feature', self.epigenetic_feature, domain.EpigeneticFeature, 'epigenetic_feature_id'),
            ('population', self.population, domain.Population, 'population_id'),
        )
        with connection.cursor() as cursor:
            for relation, parent, model, key in parents:
                new_id = uuid.uuid4()
                table = connection.ops.quote_name(model._meta.db_table)
                column = connection.ops.quote_name(key)
                cursor.execute(f'UPDATE {table} SET {column} = %s WHERE {column} = %s', [new_id, parent.pk])
                parent.pk = new_id
                result.refresh_from_db()
                self.assertEqual(getattr(result, relation + '_id'), new_id)

    def test_optional_raw_parent_deletes_set_null_but_analysis_delete_is_restricted(self):
        self.assertTrue(hasattr(domain, 'AnalysisResult'), 'AnalysisResult schema model is missing.')
        result = self.result(
            participant=self.isolated_participant, sample=self.sample, release=self.release, variant=self.variant,
            epigenetic_feature=self.epigenetic_feature, population=self.population,
        )
        result.save()
        optional = (
            ('participant', 'participant', 'participant_id', self.isolated_participant.pk),
            ('sample', 'sample', 'sample_id', self.sample.pk),
            ('release', 'data_release', 'release_id', self.release.pk),
            ('variant', 'variant', 'variant_id', self.variant.pk),
            ('epigenetic_feature', 'epigenetic_feature', 'epigenetic_feature_id', self.epigenetic_feature.pk),
            ('population', 'population', 'population_id', self.population.pk),
        )
        for relation, table, key, value in optional:
            with connection.cursor() as cursor:
                cursor.execute(
                    f'DELETE FROM {connection.ops.quote_name(table)} WHERE {connection.ops.quote_name(key)} = %s',
                    [value],
                )
            result.refresh_from_db()
            self.assertIsNone(getattr(result, relation + '_id'))
        with self.assertRaises(IntegrityError) as error, transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute('DELETE FROM analysis WHERE analysis_id = %s', [self.analysis.pk])
        self.assertEqual(error.exception.__cause__.diag.constraint_name, 'fk_result_analysis')
        with self.assertRaises(ProtectedError):
            self.analysis.delete()
        self.assertTrue(domain.AnalysisResult.objects.filter(pk=result.pk).exists())

    def test_migration_state_matches_model_and_has_no_dependency_cycle(self):
        self.assertTrue(hasattr(domain, 'AnalysisResult'), 'AnalysisResult schema model is missing.')
        migration = normalized_migration_slice('AnalysisResult')
        self.assertEqual(migration.dependencies, normalized_dependencies('AnalysisResult'))
        loader = MigrationLoader(connection, replace_migrations=False)
        state = loader.project_state([NORMALIZED_LEAF])
        historical = state.apps.get_model('genoma', 'AnalysisResult')
        self.assertEqual(
            {field.name: field.deconstruct()[1:] for field in historical._meta.local_fields},
            {field.name: field.deconstruct()[1:] for field in domain.AnalysisResult._meta.local_fields},
        )
        self.assertEqual(historical._meta.indexes, domain.AnalysisResult._meta.indexes)
        self.assertEqual(historical._meta.constraints, domain.AnalysisResult._meta.constraints)
        self.assertEqual(loader.graph.leaf_nodes('genoma'), [NORMALIZED_LEAF])


class AnalysisResultMigrationTests(TransactionTestCase):
    def fk_actions(self):
        with connection.cursor() as cursor:
            cursor.execute(
                'SELECT conname, confdeltype, confupdtype, condeferrable, condeferred '
                'FROM pg_constraint WHERE conrelid = %s::regclass AND contype = %s',
                ['analysis_result', 'f'],
            )
            return {row[0]: row[1:] for row in cursor.fetchall()}

    def test_fk_reverse_and_forward_have_exact_physical_actions(self):
        self.assertTrue(hasattr(domain, 'AnalysisResult'), 'AnalysisResult schema model is missing.')
        migration = import_module('genoma.migrations.0015_analysis_result')
        editor = connection.SchemaEditorClass(connection)
        with transaction.atomic():
            migration.restore_analysis_result_fks(None, editor)
            self.assertEqual(self.fk_actions(), {
                name: ('a', 'a', True, True) for name in (
                    'fk_result_analysis', 'fk_result_participant', 'fk_result_sample', 'fk_result_release',
                    'fk_result_variant', 'fk_result_epigenetic_feature', 'fk_result_population',
                )
            })
            migration.replace_analysis_result_fks(None, editor, physical=True)
            self.assertEqual(self.fk_actions(), {
                'fk_result_analysis': ('r', 'c', False, False),
                **{name: ('n', 'c', False, False) for name in (
                    'fk_result_participant', 'fk_result_sample', 'fk_result_release', 'fk_result_variant',
                    'fk_result_epigenetic_feature', 'fk_result_population',
                )},
            })
        self.assertIs(
            migration.Migration.operations[-1].reverse_code, migration.restore_analysis_result_fks,
        )

    def test_fk_resolution_failure_does_not_partially_replace_constraints(self):
        self.assertTrue(hasattr(domain, 'AnalysisResult'), 'AnalysisResult schema model is missing.')
        migration = import_module('genoma.migrations.0015_analysis_result')
        editor = connection.SchemaEditorClass(connection)
        with transaction.atomic():
            try:
                with connection.cursor() as cursor:
                    cursor.execute('ALTER TABLE analysis_result DROP CONSTRAINT fk_result_sample')
                before = self.fk_actions()
                with self.assertRaisesRegex(RuntimeError, 'analysis_result.sample_id -> sample.sample_id'):
                    migration.replace_analysis_result_fks(None, editor, physical=True)
                self.assertEqual(self.fk_actions(), before)
            finally:
                transaction.set_rollback(True)


class GenotypeTests(TestCase):
    def setUp(self):
        self.assertTrue(connection.settings_dict['NAME'].startswith('gdb_test_'))
        from participants.models import Participant
        self.user = User.objects.create_user(username=f'genotype-{uuid.uuid4().hex}')
        self.participant = Participant.objects.create(
            user=self.user, participant_code=f'genotype-{uuid.uuid4().hex}',
        )
        self.release = self.new_release()
        self.variant = self.new_variant()
        self.analysis = self.new_analysis()

    def new_release(self):
        return domain.DataRelease.objects.create(
            name=uuid.uuid4().hex, version='v1', status='unlisted', reference_assembly='synthetic',
        )

    def new_variant(self):
        return domain.Variant.objects.create(variant_type='synthetic-genotype')

    def new_analysis(self):
        return domain.Analysis.objects.create(
            module='synthetic', pipeline_name='synthetic', pipeline_version='v1', status='unlisted',
        )

    def new_sample(self, *, independent_participant=False):
        user, participant = self.user, self.participant
        if independent_participant:
            from participants.models import Participant
            user = User.objects.create_user(username=f'genotype-sample-{uuid.uuid4().hex}')
            participant = Participant.objects.create(
                user=user, participant_code=f'genotype-sample-{uuid.uuid4().hex}',
            )
        request = ServiceRequest.objects.create(
            purchase=Purchase.objects.create(owner=user.app_user), participant=participant,
            status=RequestStatus.objects.get(code='WAITING_SAMPLE'),
        )
        return Sample.objects.create(
            service_request=request, participant=participant,
            sample_code=f'genotype-{uuid.uuid4().hex}', sample_type='synthetic',
        )

    def genotype_row(self, **changes):
        values = {
            'release': self.release, 'variant': self.variant, 'participant': self.participant,
            'analysis': self.analysis, 'genotype': 'unlisted-call',
        }
        return domain.Genotype(**(values | changes))

    def fk_actions(self):
        with connection.cursor() as cursor:
            cursor.execute(
                'SELECT conname, confdeltype, confupdtype, condeferrable, condeferred '
                'FROM pg_constraint WHERE conrelid = %s::regclass AND contype = %s', ['genotype', 'f'],
            )
            return {row[0]: row[1:] for row in cursor.fetchall()}

    def test_exact_columns_defaults_types_constraints_and_two_explicit_indexes(self):
        columns = {
            'genotype_id': ('uuid', None, 'NO', None),
            'release_id': ('uuid', None, 'NO', None),
            'variant_id': ('uuid', None, 'NO', None),
            'participant_id': ('uuid', None, 'NO', None),
            'sample_id': ('uuid', None, 'YES', None),
            'analysis_id': ('uuid', None, 'NO', None),
            'genotype': ('character varying', 32, 'NO', None),
            'phased': ('boolean', None, 'NO', 'false'),
            'phase_set': ('character varying', 64, 'YES', None),
            'dosage': ('numeric', None, 'YES', None),
            'genotype_quality': ('numeric', None, 'YES', None),
            'read_depth': ('integer', None, 'YES', None),
            'allele_depths': ('jsonb', None, 'YES', None),
            'filters': ('jsonb', None, 'YES', None),
            'created_at': ('timestamp with time zone', None, 'NO', 'CURRENT_TIMESTAMP'),
        }
        with connection.cursor() as cursor:
            cursor.execute(
                'SELECT column_name, data_type, character_maximum_length, is_nullable, column_default '
                'FROM information_schema.columns WHERE table_schema = current_schema() '
                "AND table_name = 'genotype' ORDER BY ordinal_position"
            )
            physical_columns = cursor.fetchall()
            indexes = connection.introspection.get_constraints(cursor, 'genotype')
            cursor.execute(
                'SELECT indexname, indexdef FROM pg_indexes WHERE schemaname = current_schema() AND tablename = %s',
                ['genotype'],
            )
            index_definitions = dict(cursor.fetchall())
            index_names = set(index_definitions)
            cursor.execute(
                'SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint '
                'WHERE conrelid = %s::regclass AND contype IN (%s, %s)', ['genotype', 'u', 'c'],
            )
            unique_and_checks = dict(cursor.fetchall())
        self.assertEqual(physical_columns, [(name, *spec) for name, spec in columns.items()])
        model = domain.Genotype
        self.assertEqual((model._meta.db_table, model._meta.pk.name), ('genotype', 'genotype_id'))
        self.assertEqual([field.column for field in model._meta.local_fields], list(columns))
        self.assertEqual(
            {field.name for field in model._meta.local_fields},
            {'genotype_id', 'release', 'variant', 'participant', 'sample', 'analysis', 'genotype', 'phased',
             'phase_set', 'dosage', 'genotype_quality', 'read_depth', 'allele_depths', 'filters', 'created_at'},
        )
        for field in model._meta.local_fields:
            expected_null = columns[field.column][2] == 'YES'
            self.assertEqual((field.null, field.blank), (expected_null, expected_null))
        self.assertEqual((model._meta.get_field('dosage').max_digits, model._meta.get_field('dosage').decimal_places), (6, 3))
        self.assertEqual((model._meta.get_field('genotype_quality').max_digits,
                          model._meta.get_field('genotype_quality').decimal_places), (8, 2))
        self.assertEqual(model._meta.get_field('phased').default, False)
        self.assertIsInstance(model._meta.get_field('created_at').db_default, TransactionNow)
        self.assertEqual(
            {index.name: index.fields for index in model._meta.indexes},
            {
                'idx_genotype_participant_release': ['participant', 'release'],
                'idx_genotype_variant_release': ['variant', 'release'],
            },
        )
        self.assertEqual(
            index_names,
            {'genotype_pkey', 'uq_genotype_analysis_sample_variant',
             'idx_genotype_participant_release', 'idx_genotype_variant_release'},
        )
        self.assertIn('(participant_id, release_id)', index_definitions['idx_genotype_participant_release'])
        self.assertIn('(variant_id, release_id)', index_definitions['idx_genotype_variant_release'])
        self.assertEqual(set(unique_and_checks), {
            'uq_genotype_analysis_sample_variant', 'genotype_quality_gte_0', 'genotype_read_depth_gte_0',
        })
        self.assertEqual(unique_and_checks['uq_genotype_analysis_sample_variant'],
                         'UNIQUE (analysis_id, participant_id, sample_id, variant_id)')
        self.assertIn('genotype_quality >=', unique_and_checks['genotype_quality_gte_0'])
        self.assertIn('read_depth >=', unique_and_checks['genotype_read_depth_gte_0'])
        unique = next(constraint for constraint in model._meta.constraints
                      if isinstance(constraint, models.UniqueConstraint))
        self.assertEqual(unique.fields, ('analysis', 'participant', 'sample', 'variant'))
        self.assertIsNone(unique.nulls_distinct)  # PostgreSQL default: NULLS DISTINCT.
        self.assertEqual(self.fk_actions(), {
            'fk_genotype_release': ('c', 'c', False, False),
            'fk_genotype_variant': ('r', 'c', False, False),
            'fk_genotype_participant': ('r', 'c', False, False),
            'fk_genotype_sample': ('n', 'c', False, False),
            'fk_genotype_analysis': ('r', 'c', False, False),
        })
        expected_targets = {
            'release': ('data_release', 'release_id', CASCADE),
            'variant': ('variant', 'variant_id', PROTECT),
            'participant': ('participant', 'participant_id', PROTECT),
            'sample': ('sample', 'sample_id', SET_NULL),
            'analysis': ('analysis', 'analysis_id', PROTECT),
        }
        for field_name, (table, key, on_delete) in expected_targets.items():
            field = model._meta.get_field(field_name)
            self.assertEqual((field.column, field.target_field.name, field.remote_field.on_delete),
                             (field_name + '_id', key, on_delete))
            self.assertEqual(field.remote_field.model._meta.db_table, table)
            self.assertFalse(field.db_index)
            self.assertTrue(field.db_constraint)
        self.assertEqual(
            {name: (info['columns'], info['foreign_key']) for name, info in indexes.items()
             if info['foreign_key']},
            {
                'fk_genotype_release': (['release_id'], ('data_release', 'release_id')),
                'fk_genotype_variant': (['variant_id'], ('variant', 'variant_id')),
                'fk_genotype_participant': (['participant_id'], ('participant', 'participant_id')),
                'fk_genotype_sample': (['sample_id'], ('sample', 'sample_id')),
                'fk_genotype_analysis': (['analysis_id'], ('analysis', 'analysis_id')),
            },
        )
        self.assertEqual(set(indexes), {
            'genotype_pkey', 'uq_genotype_analysis_sample_variant',
            'genotype_quality_gte_0', 'genotype_read_depth_gte_0',
            'idx_genotype_participant_release', 'idx_genotype_variant_release',
            'fk_genotype_release', 'fk_genotype_variant', 'fk_genotype_participant',
            'fk_genotype_sample', 'fk_genotype_analysis',
        })

    def test_insert_uses_database_defaults_and_jsonb_without_extra_call_semantics(self):
        identifier = uuid.uuid4()
        with connection.cursor() as cursor:
            cursor.execute(
                'INSERT INTO genotype (genotype_id, release_id, variant_id, participant_id, analysis_id, genotype) '
                'VALUES (%s, %s, %s, %s, %s, %s) '
                'RETURNING phased, allele_depths, filters, created_at, transaction_timestamp(), '
                'pg_typeof(allele_depths), pg_typeof(filters)',
                [identifier, self.release.pk, self.variant.pk, self.participant.pk, self.analysis.pk, 'not-interpreted'],
            )
            phased, depths, filters, created, transaction_time, depths_type, filters_type = cursor.fetchone()
        self.assertFalse(phased)
        self.assertIsNone(depths)
        self.assertIsNone(filters)
        self.assertEqual(created, transaction_time)
        self.assertEqual((depths_type, filters_type), ('jsonb', 'jsonb'))
        self.assertTrue(domain.Genotype.objects.filter(pk=identifier, genotype='not-interpreted').exists())
        defaulted = self.genotype_row()
        created_by_python = defaulted.created_at
        self.assertIsInstance(defaulted.pk, uuid.UUID)
        self.assertTrue(timezone.is_aware(created_by_python))
        self.assertFalse(defaulted.phased)
        self.assertIs(domain.Genotype._meta.get_field('genotype_id').default, uuid.uuid4)
        self.assertIs(domain.Genotype._meta.get_field('created_at').default, timezone.now)
        defaulted.full_clean()
        defaulted.save()
        defaulted.refresh_from_db()
        self.assertEqual(defaulted.created_at, created_by_python)
        genotype = self.genotype_row(dosage=Decimal('-1.000'), allele_depths={'A': 3}, filters=['synthetic-filter'])
        genotype.full_clean()
        genotype.save()
        genotype.refresh_from_db()
        self.assertEqual((genotype.dosage, genotype.allele_depths, genotype.filters),
                         (Decimal('-1.000'), {'A': 3}, ['synthetic-filter']))

    def test_composite_uniqueness_preserves_null_sample_distinct_and_checks_only_declared_bounds(self):
        first = self.genotype_row()
        first.save()
        second = self.genotype_row()
        second.save()  # SQL UNIQUE treats each NULL sample_id as distinct.
        sample = self.new_sample()
        third = self.genotype_row(sample=sample)
        third.save()
        self.assertEqual(domain.Genotype.objects.count(), 3)
        duplicate = self.genotype_row(sample=sample)
        with self.assertRaises(ValidationError):
            duplicate.full_clean()
        with self.assertRaises(IntegrityError) as error, transaction.atomic():
            duplicate.save(force_insert=True)
        self.assertEqual(error.exception.__cause__.diag.constraint_name, 'uq_genotype_analysis_sample_variant')
        for field, value, constraint in (
            ('genotype_quality', Decimal('-0.01'), 'genotype_quality_gte_0'),
            ('read_depth', -1, 'genotype_read_depth_gte_0'),
        ):
            with self.subTest(field=field):
                invalid = self.genotype_row(**{field: value})
                with self.assertRaises(ValidationError):
                    invalid.full_clean()
                with self.assertRaises(IntegrityError) as error, transaction.atomic():
                    invalid.save(force_insert=True)
                self.assertEqual(error.exception.__cause__.diag.constraint_name, constraint)

    def test_raw_updates_cascade_all_five_parent_keys(self):
        sample = self.new_sample(independent_participant=True)
        genotype = self.genotype_row(sample=sample)
        genotype.save()
        from participants.models import Participant
        parents = {
            'release': (self.release, domain.DataRelease, 'release_id'),
            'variant': (self.variant, domain.Variant, 'variant_id'),
            'participant': (self.participant, Participant, 'participant_id'),
            'sample': (sample, Sample, 'sample_id'),
            'analysis': (self.analysis, domain.Analysis, 'analysis_id'),
        }
        with connection.cursor() as cursor:
            for field_name, (parent, target, key) in parents.items():
                new_id = uuid.uuid4()
                table_name = connection.ops.quote_name(target._meta.db_table)
                column_name = connection.ops.quote_name(key)
                cursor.execute(
                    f'UPDATE {table_name} SET {column_name} = %s WHERE {column_name} = %s',
                    [new_id, parent.pk],
                )
                parent.pk = new_id
                genotype.refresh_from_db()
                self.assertEqual(getattr(genotype, field_name + '_id'), new_id)

    def test_raw_deletes_cascade_restrict_and_set_null_immediately(self):
        sample = self.new_sample(independent_participant=True)
        genotype = self.genotype_row(sample=sample)
        genotype.save()
        for field_name, table, key, constraint in (
            ('variant', 'variant', 'variant_id', 'fk_genotype_variant'),
            ('participant', 'participant', 'participant_id', 'fk_genotype_participant'),
            ('analysis', 'analysis', 'analysis_id', 'fk_genotype_analysis'),
        ):
            value = getattr(genotype, field_name + '_id')
            with self.subTest(field=field_name):
                with self.assertRaises(IntegrityError) as error, transaction.atomic():
                    with connection.cursor() as cursor:
                        cursor.execute(f'DELETE FROM {connection.ops.quote_name(table)} '
                                       f'WHERE {connection.ops.quote_name(key)} = %s', [value])
                self.assertEqual(error.exception.__cause__.diag.constraint_name, constraint)
        with connection.cursor() as cursor:
            cursor.execute('DELETE FROM sample WHERE sample_id = %s', [sample.pk])
        genotype.refresh_from_db()
        self.assertIsNone(genotype.sample_id)
        with connection.cursor() as cursor:
            cursor.execute('DELETE FROM data_release WHERE release_id = %s', [self.release.pk])
        self.assertFalse(domain.Genotype.objects.filter(pk=genotype.pk).exists())
        self.assertTrue(domain.Variant.objects.filter(pk=self.variant.pk).exists())
        self.assertTrue(domain.Analysis.objects.filter(pk=self.analysis.pk).exists())

    def test_orm_reverse_relations_and_deletion_policy_match_the_physical_schema(self):
        sample = self.new_sample(independent_participant=True)
        genotype = self.genotype_row(sample=sample)
        genotype.save()
        for parent in (self.release, self.variant, self.participant, sample, self.analysis):
            self.assertEqual(list(parent.genotypes.all()), [genotype])
        for parent in (self.variant, self.participant, self.analysis):
            with self.assertRaises(ProtectedError):
                parent.delete()
        sample.delete()
        genotype.refresh_from_db()
        self.assertIsNone(genotype.sample_id)
        key = genotype.pk
        self.release.delete()
        self.assertFalse(domain.Genotype.objects.filter(pk=key).exists())

    def test_migration_state_matches_model_and_has_no_dependency_cycle(self):
        migration = normalized_migration_slice('Genotype')
        self.assertEqual(migration.dependencies, normalized_dependencies('Genotype'))
        loader = MigrationLoader(connection, replace_migrations=False)
        state = loader.project_state([NORMALIZED_LEAF])
        historical = state.apps.get_model('genoma', 'Genotype')
        self.assertEqual(
            {field.name: field.deconstruct()[1:] for field in historical._meta.local_fields},
            {field.name: field.deconstruct()[1:] for field in domain.Genotype._meta.local_fields},
        )
        self.assertEqual(historical._meta.indexes, domain.Genotype._meta.indexes)
        self.assertEqual(historical._meta.constraints, domain.Genotype._meta.constraints)
        self.assertIn(NORMALIZED_INITIAL, loader.graph.nodes)
        for dependency in NORMALIZED_DEPENDENCIES:
            self.assertIn(dependency, loader.graph.forwards_plan(NORMALIZED_LEAF))


class GenotypeMigrationTests(TransactionTestCase):
    def setUp(self):
        self.assertTrue(connection.settings_dict['NAME'].startswith('gdb_test_'))

    def fk_actions(self):
        with connection.cursor() as cursor:
            cursor.execute(
                'SELECT conname, confdeltype, confupdtype, condeferrable, condeferred '
                'FROM pg_constraint WHERE conrelid = %s::regclass AND contype = %s', ['genotype', 'f'],
            )
            return {row[0]: row[1:] for row in cursor.fetchall()}

    def test_fk_reverse_restores_deferred_no_action_and_forward_is_physical(self):
        migration = import_module('genoma.migrations.0013_genotype')
        editor = connection.SchemaEditorClass(connection)
        with transaction.atomic():
            migration.restore_genotype_fks(None, editor)
            self.assertEqual(self.fk_actions(), {
                name: ('a', 'a', True, True) for name in (
                    'fk_genotype_release', 'fk_genotype_variant', 'fk_genotype_participant',
                    'fk_genotype_sample', 'fk_genotype_analysis',
                )
            })
            migration.replace_genotype_fks(None, editor, physical=True)
            self.assertEqual(self.fk_actions(), {
                'fk_genotype_release': ('c', 'c', False, False),
                'fk_genotype_variant': ('r', 'c', False, False),
                'fk_genotype_participant': ('r', 'c', False, False),
                'fk_genotype_sample': ('n', 'c', False, False),
                'fk_genotype_analysis': ('r', 'c', False, False),
            })
        self.assertIs(normalized_migration_slice('Genotype').operations[-1].reverse_code,
                      migration.restore_genotype_fks)

    def test_fk_lookup_resolves_every_relation_before_any_constraint_ddl(self):
        migration = import_module('genoma.migrations.0013_genotype')
        editor = connection.SchemaEditorClass(connection)
        with transaction.atomic():
            try:
                with connection.cursor() as cursor:
                    cursor.execute('ALTER TABLE genotype DROP CONSTRAINT fk_genotype_variant')
                before = self.fk_actions()
                self.assertNotIn('fk_genotype_variant', before)
                with self.assertRaisesRegex(RuntimeError, 'genotype.variant_id -> variant.variant_id'):
                    migration.replace_genotype_fks(None, editor, physical=True)
                self.assertEqual(self.fk_actions(), before)
            finally:
                transaction.set_rollback(True)


class ReleaseEpigeneticFeatureTests(TestCase):
    fk_specs = (
        ('release', domain.DataRelease, 'release_id', 'fk_release_epi_feature_release', CASCADE, 'c'),
        ('epigenetic_feature', domain.EpigeneticFeature, 'epigenetic_feature_id', 'fk_release_epi_feature_feature', RESTRICT, 'r'),
        ('included_by_analysis', domain.Analysis, 'analysis_id', 'fk_release_epi_feature_analysis', SET_NULL, 'n'),
    )

    def setUp(self):
        self.assertTrue(connection.settings_dict['NAME'].startswith('gdb_test_'))
        self.release, self.feature = self.new_release(), self.new_feature()

    def new_release(self):
        return domain.DataRelease.objects.create(
            name=uuid.uuid4().hex, version='v1', status='unlisted', reference_assembly='release-assembly',
        )

    def new_feature(self):
        return domain.EpigeneticFeature.objects.create(
            feature_type='synthetic', reference_assembly='feature-assembly', contig='synthetic', start_pos=1, end_pos=1,
        )

    def membership(self, **changes):
        return domain.ReleaseEpigeneticFeature(**(dict(release_id=self.release.pk, epigenetic_feature_id=self.feature.pk) | changes))

    def linked_membership(self):
        analysis = domain.Analysis.objects.create(
            release=self.new_release(), module='synthetic', pipeline_name='synthetic', pipeline_version='v1', status='unlisted',
        )
        membership = self.membership(included_by_analysis_id=analysis.pk)
        membership.full_clean()  # SQL does not require matching analysis release or feature assembly.
        membership.save()
        return membership, {'release': self.release, 'epigenetic_feature': self.feature, 'included_by_analysis': analysis}

    def physical_columns(self):
        with connection.cursor() as cursor:
            cursor.execute('SELECT column_name, data_type, character_maximum_length, is_nullable, column_default '
                           'FROM information_schema.columns WHERE table_schema = current_schema() '
                           "AND table_name = 'release_epigenetic_feature' ORDER BY ordinal_position")
            return cursor.fetchall()

    def fk_actions(self):
        with connection.cursor() as cursor:
            cursor.execute('SELECT conname, confdeltype, confupdtype, condeferrable, condeferred FROM pg_constraint '
                           "WHERE conrelid = 'release_epigenetic_feature'::regclass AND contype = 'f'")
            return {row[0]: row[1:] for row in cursor.fetchall()}

    def fk_operation(self):
        migration = normalized_migration_slice('ReleaseEpigeneticFeature')
        return migration.operations[2], MigrationLoader(connection, replace_migrations=False).project_state([NORMALIZED_LEAF])

    def test_minimal_membership_uses_ordered_native_key(self):
        self.assertTrue(hasattr(domain, 'ReleaseEpigeneticFeature'), 'ReleaseEpigeneticFeature is missing.')
        before = timezone.now()
        membership = self.membership()
        created = membership.created_at
        membership.full_clean()
        membership.save()
        membership.refresh_from_db()
        self.assertEqual(membership.pk, (self.release.pk, self.feature.pk))
        self.assertEqual(domain.ReleaseEpigeneticFeature.objects.get(pk=membership.pk), membership)
        self.assertFalse(domain.ReleaseEpigeneticFeature.objects.filter(pk=tuple(reversed(membership.pk))).exists())
        self.assertIsNone(membership.included_by_analysis_id)
        self.assertEqual(membership.created_at, created)
        self.assertTrue(timezone.is_aware(created))
        self.assertLessEqual(before, created)
        self.assertLessEqual(created, timezone.now())

    def test_exact_four_columns_native_pk_three_fks_and_only_feature_index(self):
        columns = {
            'release_id': ('uuid', None, 'NO', None),
            'epigenetic_feature_id': ('uuid', None, 'NO', None),
            'included_by_analysis_id': ('uuid', None, 'YES', None),
            'created_at': ('timestamp with time zone', None, 'NO', 'CURRENT_TIMESTAMP'),
        }
        model = domain.ReleaseEpigeneticFeature
        self.assertEqual((model._meta.db_table, model._meta.pk.name), ('release_epigenetic_feature', 'pk'))
        self.assertIsInstance(model._meta.pk, models.CompositePrimaryKey)
        self.assertEqual(model._meta.pk.field_names, ('release_id', 'epigenetic_feature_id'))
        self.assertEqual(tuple(field.attname for field in model._meta.pk.fields), model._meta.pk.field_names)
        self.assertIsNone(model._meta.pk.column)
        self.assertFalse(model._meta.pk.editable or model._meta.pk.has_default() or model._meta.pk.has_db_default())
        self.assertEqual([field.column for field in model._meta.local_fields if field.column], list(columns))
        self.assertEqual({field.name for field in model._meta.local_fields},
                         {'pk', 'release', 'epigenetic_feature', 'included_by_analysis', 'created_at'})
        for field in model._meta.local_fields:
            if field.column:
                nullable = columns[field.column][2] == 'YES'
                self.assertEqual((field.null, field.blank), (nullable, nullable))
                self.assertFalse(field.choices or field.db_index or field.unique or field.primary_key)
                self.assertEqual((field.has_default(), field.has_db_default()), (field.name == 'created_at',) * 2)
        created = model._meta.get_field('created_at')
        self.assertIs(created.default, timezone.now)
        self.assertIsInstance(created.db_default, TransactionNow)
        self.assertFalse(created.auto_now or created.auto_now_add)
        self.assertEqual(model._meta.constraints, [])
        self.assertEqual({index.name: index.fields for index in model._meta.indexes}, {'idx_release_epi_feature': ['epigenetic_feature']})
        for field, target, key, _, action, _ in self.fk_specs:
            relation = model._meta.get_field(field)
            self.assertIs(relation.remote_field.model, target)
            self.assertIs(relation.remote_field.on_delete, action)
            self.assertEqual((relation.column, relation.db_column, relation.target_field.name), (field + '_id', field + '_id', key))
            self.assertTrue(relation.db_constraint)
        self.assertEqual(self.physical_columns(), [(name, *spec) for name, spec in columns.items()])
        with connection.cursor() as cursor:
            constraints = connection.introspection.get_constraints(cursor, 'release_epigenetic_feature')
            cursor.execute("SELECT indexname FROM pg_indexes WHERE schemaname = current_schema() AND tablename = 'release_epigenetic_feature'")
            self.assertEqual({row[0] for row in cursor.fetchall()}, {'release_epigenetic_feature_pkey', 'idx_release_epi_feature'})
            cursor.execute("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid = 'release_epigenetic_feature'::regclass AND contype = 'p'")
            self.assertEqual(cursor.fetchone()[0], 'PRIMARY KEY (release_id, epigenetic_feature_id)')
        self.assertEqual(set(constraints), {'release_epigenetic_feature_pkey', 'idx_release_epi_feature', *[spec[3] for spec in self.fk_specs]})
        self.assertEqual([info['columns'] for info in constraints.values() if info['primary_key']], [['release_id', 'epigenetic_feature_id']])
        self.assertFalse(any(info['check'] or info['unique'] and not info['primary_key'] for info in constraints.values()))
        self.assertEqual({name: info['columns'] for name, info in constraints.items() if info['index']},
                         {'idx_release_epi_feature': ['epigenetic_feature_id']})
        self.assertEqual({name: (info['columns'], info['foreign_key']) for name, info in constraints.items() if info['foreign_key']},
                         {name: ([field + '_id'], (target._meta.db_table, key)) for field, target, key, name, _, _ in self.fk_specs})
        self.assertEqual(self.fk_actions(), {name: (deletion, 'c', False, False) for _, _, _, name, _, deletion in self.fk_specs})

    def test_raw_minimal_insert_uses_nullable_analysis_and_transaction_timestamp_without_side_effects(self):
        others = (domain.DataRelease, domain.EpigeneticFeature, domain.Analysis, domain.ReleaseVariant,
                  domain.Variant, domain.VariantPlacement, domain.VariantAnnotation, domain.AlleleFrequency,
                  domain.ExternalIdentifier, domain.Population)
        before = {model: model.objects.count() for model in others}
        with connection.cursor() as cursor:
            cursor.execute('INSERT INTO release_epigenetic_feature (release_id, epigenetic_feature_id) VALUES (%s, %s) '
                           'RETURNING included_by_analysis_id, created_at, transaction_timestamp()', [self.release.pk, self.feature.pk])
            analysis, created, database_now = cursor.fetchone()
        self.assertIsNone(analysis)
        self.assertTrue(timezone.is_aware(created))
        self.assertEqual(created, database_now)
        self.assertEqual({model: model.objects.count() for model in others}, before)

    def test_pair_uniqueness_distinct_components_and_native_lookup_update_delete(self):
        first = self.membership()
        first.save()
        with self.assertRaises(ValidationError):
            self.membership().full_clean()
        for insert in (lambda: domain.ReleaseEpigeneticFeature.objects.create(release=self.release, epigenetic_feature=self.feature),
                       lambda: domain.ReleaseEpigeneticFeature.objects.bulk_create([self.membership()])):
            with self.assertRaises(IntegrityError) as error, transaction.atomic():
                insert()
            self.assertEqual(error.exception.__cause__.diag.constraint_name, 'release_epigenetic_feature_pkey')
        with self.assertRaises(IntegrityError) as error, transaction.atomic(), connection.cursor() as cursor:
            cursor.execute('INSERT INTO release_epigenetic_feature (release_id, epigenetic_feature_id) VALUES (%s, %s)', list(first.pk))
        self.assertEqual(error.exception.__cause__.diag.constraint_name, 'release_epigenetic_feature_pkey')
        second, third = self.membership(epigenetic_feature_id=self.new_feature().pk), self.membership(release_id=self.new_release().pk)
        for membership in (second, third):
            membership.full_clean()
            membership.save()
        self.assertEqual(set(domain.ReleaseEpigeneticFeature.objects.values_list('pk', flat=True)), {first.pk, second.pk, third.pk})
        created = timezone.now() - timedelta(days=90)
        self.assertEqual(domain.ReleaseEpigeneticFeature.objects.filter(pk=first.pk).update(created_at=created), 1)
        first.refresh_from_db()
        self.assertEqual(first.created_at, created)
        first.delete()
        self.assertEqual(domain.ReleaseEpigeneticFeature.objects.filter(pk=second.pk).delete()[0], 1)
        self.assertEqual(list(domain.ReleaseEpigeneticFeature.objects.values_list('pk', flat=True)), [third.pk])

    def test_required_columns_reject_explicit_nulls_and_unrelated_provenance_is_allowed(self):
        values = dict(release_id=self.release.pk, epigenetic_feature_id=self.feature.pk, created_at=timezone.now())
        sql = f"INSERT INTO release_epigenetic_feature ({', '.join(values)}) VALUES (%s, %s, %s)"
        for column in values:
            with self.subTest(column=column):
                with self.assertRaises(ValidationError):
                    self.membership(**{column: None}).full_clean()
                with self.assertRaises(IntegrityError) as error, transaction.atomic(), connection.cursor() as cursor:
                    cursor.execute(sql, [None if name == column else value for name, value in values.items()])
                self.assertEqual(error.exception.__cause__.diag.column_name, column)
        membership, parents = self.linked_membership()
        self.assertNotEqual(parents['included_by_analysis'].release_id, membership.release_id)
        self.assertNotEqual(self.feature.reference_assembly, self.release.reference_assembly)
        created = membership.created_at = timezone.now() - timedelta(days=90)
        membership.full_clean()
        membership.save(update_fields=['created_at'])
        membership.refresh_from_db()
        self.assertEqual(membership.created_at, created)
        self.assertEqual(membership.included_by_analysis_id, parents['included_by_analysis'].pk)

    def test_raw_updates_of_all_three_parent_keys_cascade_including_both_pk_components(self):
        membership, parents = self.linked_membership()
        untouched = self.membership(release_id=self.new_release().pk, epigenetic_feature_id=self.new_feature().pk)
        untouched.save()
        before = domain.ReleaseEpigeneticFeature.objects.filter(pk=untouched.pk).values().get()
        with connection.cursor() as cursor:
            for field, target, key, _, _, _ in self.fk_specs:
                parent, new_id, old_pair = parents[field], uuid.uuid4(), membership.pk
                cursor.execute(f'UPDATE {target._meta.db_table} SET {key} = %s WHERE {key} = %s', [new_id, parent.pk])
                parent.pk = new_id
                setattr(membership, field + '_id', new_id)
                membership.refresh_from_db()
                self.assertEqual(getattr(membership, field + '_id'), new_id)
                self.assertEqual(membership.pk, (self.release.pk, self.feature.pk))
                if field != 'included_by_analysis':
                    self.assertFalse(domain.ReleaseEpigeneticFeature.objects.filter(pk=old_pair).exists())
        self.assertEqual(domain.ReleaseEpigeneticFeature.objects.filter(pk=untouched.pk).values().get(), before)

    def test_raw_deletes_set_analysis_null_restrict_feature_immediately_and_cascade_only_release(self):
        membership, parents = self.linked_membership()
        untouched = self.membership(release_id=self.new_release().pk)
        untouched.save()
        before = domain.ReleaseEpigeneticFeature.objects.filter(pk=untouched.pk).values().get()
        with connection.cursor() as cursor:
            cursor.execute('DELETE FROM analysis WHERE analysis_id = %s', [parents['included_by_analysis'].pk])
            membership.refresh_from_db()
            self.assertIsNone(membership.included_by_analysis_id)
            with self.assertRaises(IntegrityError) as error, transaction.atomic():
                cursor.execute('SET CONSTRAINTS ALL DEFERRED')
                cursor.execute('DELETE FROM epigenetic_feature WHERE epigenetic_feature_id = %s', [self.feature.pk])
                self.fail('RESTRICT must reject the delete at the statement.')
            self.assertEqual(error.exception.__cause__.diag.constraint_name, 'fk_release_epi_feature_feature')
            cursor.execute('DELETE FROM data_release WHERE release_id = %s', [self.release.pk])
        self.assertFalse(domain.ReleaseEpigeneticFeature.objects.filter(pk=membership.pk).exists())
        self.assertTrue(domain.EpigeneticFeature.objects.filter(pk=self.feature.pk).exists())
        self.assertEqual(domain.ReleaseEpigeneticFeature.objects.filter(pk=untouched.pk).values().get(), before)

    def test_orm_reverse_relations_and_deletions_match_physical_actions(self):
        membership, parents = self.linked_membership()
        for parent, related in ((self.release, 'epigenetic_feature_memberships'), (self.feature, 'release_memberships'),
                                (parents['included_by_analysis'], 'included_epigenetic_feature_memberships')):
            self.assertEqual(list(getattr(parent, related).all()), [membership])
        for delete in (self.feature.delete, lambda: domain.EpigeneticFeature.objects.filter(pk=self.feature.pk).delete()):
            with self.assertRaises(RestrictedError):
                delete()
        parents['included_by_analysis'].delete()
        membership.refresh_from_db()
        self.assertIsNone(membership.included_by_analysis_id)
        pair = membership.pk
        self.release.delete()
        self.assertFalse(domain.ReleaseEpigeneticFeature.objects.filter(pk=pair).exists())
        self.assertTrue(domain.EpigeneticFeature.objects.filter(pk=self.feature.pk).exists())

    def test_all_three_orphan_inserts_and_updates_fail_at_the_statement_even_when_deferred(self):
        membership = self.membership()
        membership.save()
        insert_release = self.new_release()
        for field, _, _, name, _, _ in self.fk_specs:
            column, orphan = field + '_id', uuid.uuid4()
            with self.subTest(field=field):
                with self.assertRaises(ValidationError):
                    self.membership(**{column: orphan}).full_clean()
                values = dict(release_id=insert_release.pk, epigenetic_feature_id=self.feature.pk) | {column: orphan}
                insert = f"INSERT INTO release_epigenetic_feature ({', '.join(values)}) VALUES ({', '.join(['%s'] * len(values))})"
                for sql, args in ((insert, list(values.values())),
                                  (f'UPDATE release_epigenetic_feature SET {column} = %s WHERE release_id = %s AND epigenetic_feature_id = %s', [orphan, *membership.pk])):
                    with self.assertRaises(IntegrityError) as error, transaction.atomic(), connection.cursor() as cursor:
                        cursor.execute('SET CONSTRAINTS ALL DEFERRED')
                        cursor.execute(sql, args)
                        self.fail('FK must reject an orphan before transaction end.')
                    self.assertEqual(error.exception.__cause__.diag.constraint_name, name)
                for insert in (lambda: domain.ReleaseEpigeneticFeature.objects.create(**values),
                               lambda: domain.ReleaseEpigeneticFeature.objects.bulk_create([domain.ReleaseEpigeneticFeature(**values)])):
                    with self.assertRaises(IntegrityError) as error, transaction.atomic():
                        insert()
                        self.fail('ORM writes must also fail before transaction end.')
                    self.assertEqual(error.exception.__cause__.diag.constraint_name, name)

    def test_fk_reverse_restores_deferred_no_action_then_forward_restores_all_actions(self):
        operation, state = self.fk_operation()
        membership, parents = self.linked_membership()
        connection.check_constraints()
        expected = self.fk_actions()
        with connection.schema_editor() as editor, connection.cursor() as cursor:
            operation.database_backwards('genoma', editor, state, state)
            self.assertEqual(self.fk_actions(), {name: ('a', 'a', True, True) for name in expected})
            for field, target, key, name, _, _ in self.fk_specs:
                with self.subTest(field=field), self.assertRaises(IntegrityError) as error, transaction.atomic():
                    new_id = uuid.uuid4()
                    cursor.execute(f'UPDATE {target._meta.db_table} SET {key} = %s WHERE {key} = %s', [new_id, parents[field].pk])
                    membership.refresh_from_db()
                    self.assertEqual(getattr(membership, field + '_id'), parents[field].pk)
                    cursor.execute(f'DELETE FROM {target._meta.db_table} WHERE {key} = %s', [new_id])
                    self.assertTrue(domain.ReleaseEpigeneticFeature.objects.filter(pk=membership.pk).exists())
                    connection.check_constraints()  # Restored NO ACTION fails only at the deferred check.
                self.assertEqual(error.exception.__cause__.diag.constraint_name, name)
            operation.database_forwards('genoma', editor, state, state)
            self.assertEqual(self.fk_actions(), expected)

    def test_each_missing_or_ambiguous_lookup_fails_before_any_ddl_in_both_directions(self):
        operation, state = self.fk_operation()
        with connection.schema_editor() as editor, connection.cursor() as cursor:
            expected = self.fk_actions()
            for apply in (operation.database_forwards, operation.database_backwards):
                for field, target, key, name, _, _ in self.fk_specs:
                    for case, sql in (
                        ('missing', f'ALTER TABLE release_epigenetic_feature DROP CONSTRAINT {name}'),
                        ('ambiguous', f'ALTER TABLE release_epigenetic_feature ADD CONSTRAINT duplicate_fk FOREIGN KEY ({field}_id) '
                         f'REFERENCES {target._meta.db_table} ({key}) DEFERRABLE INITIALLY DEFERRED'),
                    ):
                        with self.subTest(direction=apply.__name__, field=field, case=case), transaction.atomic():
                            cursor.execute(sql)
                            before = self.fk_actions()
                            editor.deferred_sql.append('SELECT 1')
                            try:
                                with patch.object(editor, 'execute', wraps=editor.execute) as execute:
                                    with self.assertRaisesMessage(RuntimeError, 'Expected exactly one FK'):
                                        apply('genoma', editor, state, state)
                                    execute.assert_not_called()
                                self.assertEqual(editor.deferred_sql, ['SELECT 1'])
                            finally:
                                editor.deferred_sql.clear()
                            self.assertEqual(self.fk_actions(), before)
                            transaction.set_rollback(True)
                operation.database_backwards('genoma', editor, state, state)
            operation.database_forwards('genoma', editor, state, state)
            self.assertEqual(self.fk_actions(), expected)

    def test_exact_relation_and_single_column_lookup_ignores_decoys_and_quotes_discovered_names(self):
        operation, state = self.fk_operation()
        with transaction.atomic(), connection.schema_editor() as editor, connection.cursor() as cursor:
            expected, decoys = self.fk_actions(), {}
            for field, target, key, name, _, _ in self.fk_specs:
                quoted = '"' + f'generated "{field}" FK'.replace('"', '""') + '"'
                cursor.execute(f'ALTER TABLE release_epigenetic_feature RENAME CONSTRAINT {name} TO {quoted}')
                cursor.execute(f'ALTER TABLE {target._meta.db_table} ADD COLUMN decoy_key uuid UNIQUE')
                cursor.execute(f'ALTER TABLE {target._meta.db_table} ADD CONSTRAINT decoy_pair_{field} UNIQUE ({key}, decoy_key)')
                other_table, other_key = ('data_release', 'release_id') if field == 'epigenetic_feature' else ('epigenetic_feature', 'epigenetic_feature_id')
                other_source = 'epigenetic_feature_id' if field == 'release' else 'release_id'
                for kind, source, table, column in (
                    ('source', other_source, target._meta.db_table, key),
                    ('target', field + '_id', target._meta.db_table, 'decoy_key'),
                    ('relation', field + '_id', other_table, other_key),
                    ('composite', f'{field}_id, {other_source}', target._meta.db_table, f'{key}, decoy_key'),
                ):
                    decoy = f'decoy_epi_membership_{kind}_{field}'
                    cursor.execute(f'ALTER TABLE release_epigenetic_feature ADD CONSTRAINT {decoy} FOREIGN KEY ({source}) '
                                   f'REFERENCES {table} ({column}) DEFERRABLE INITIALLY DEFERRED')
                    decoys[decoy] = ('a', 'a', True, True)
            operation.database_forwards('genoma', editor, state, state)
            self.assertEqual(self.fk_actions(), expected | decoys)
            for field, _, _, name, _, _ in self.fk_specs:
                quoted = '"' + f'reverse "{field}" FK'.replace('"', '""') + '"'
                cursor.execute(f'ALTER TABLE release_epigenetic_feature RENAME CONSTRAINT {name} TO {quoted}')
            operation.database_backwards('genoma', editor, state, state)
            self.assertEqual(self.fk_actions(), {name: ('a', 'a', True, True) for name in expected} | decoys)
            transaction.set_rollback(True)

    def test_full_migration_reversal_and_reapplication_preserve_parents_and_exact_catalog(self):
        migration = normalized_migration_slice('ReleaseEpigeneticFeature')
        prior = normalized_state_before('ReleaseEpigeneticFeature')
        membership, parents = self.linked_membership()
        connection.check_constraints()
        actions, columns = self.fk_actions(), self.physical_columns()
        with connection.cursor() as cursor:
            constraints = connection.introspection.get_constraints(cursor, 'release_epigenetic_feature')
        with connection.schema_editor() as editor:
            migration.unapply(prior, editor)
        with connection.cursor() as cursor:
            self.assertNotIn('release_epigenetic_feature', connection.introspection.table_names(cursor))
        for parent in parents.values():
            self.assertTrue(type(parent).objects.filter(pk=parent.pk).exists())
        with connection.schema_editor() as editor:
            migration.apply(prior.clone(), editor)
        self.assertEqual(domain.ReleaseEpigeneticFeature.objects.count(), 0)
        self.assertEqual((self.fk_actions(), self.physical_columns()), (actions, columns))
        with connection.cursor() as cursor:
            self.assertEqual(connection.introspection.get_constraints(cursor, 'release_epigenetic_feature'), constraints)
        membership.save(force_insert=True)
        self.assertEqual(domain.ReleaseEpigeneticFeature.objects.get(pk=membership.pk), membership)

    def test_schema_only_migration_dependency_and_exact_native_composite_state(self):
        with self.assertNumQueries(0):
            reload(import_module('genoma.migrations.0012_release_epigenetic_feature'))
            migration = normalized_migration_slice('ReleaseEpigeneticFeature')
        self.assertEqual(migration.dependencies, normalized_dependencies('ReleaseEpigeneticFeature'))
        self.assertEqual([type(operation).__name__ for operation in migration.operations], ['CreateModel', 'RunPython', 'RunPython'])
        self.assertEqual(migration.operations[0].name, 'ReleaseEpigeneticFeature')
        self.assertTrue(all(operation.reversible for operation in migration.operations))
        historical = MigrationLoader(connection, replace_migrations=False).project_state([NORMALIZED_LEAF]).apps.get_model('genoma', 'ReleaseEpigeneticFeature')
        current = domain.ReleaseEpigeneticFeature
        self.assertEqual(historical._meta.db_table, current._meta.db_table)
        self.assertEqual({field.name: field.deconstruct()[1:] for field in historical._meta.local_fields},
                         {field.name: field.deconstruct()[1:] for field in current._meta.local_fields})
        self.assertEqual(historical._meta.pk.field_names, ('release_id', 'epigenetic_feature_id'))
        self.assertEqual(historical._meta.indexes, current._meta.indexes)
        self.assertEqual(historical._meta.constraints, current._meta.constraints)
        call_command('check')
        call_command('makemigrations', check=True, dry_run=True)


class ReleaseVariantTests(TestCase):
    fk_specs = (
        ('release', domain.DataRelease, 'release_id', 'fk_release_variant_release', CASCADE, 'c'),
        ('variant', domain.Variant, 'variant_id', 'fk_release_variant_variant', RESTRICT, 'r'),
        ('placement', domain.VariantPlacement, 'placement_id', 'fk_release_variant_placement', RESTRICT, 'r'),
        ('included_by_analysis', domain.Analysis, 'analysis_id', 'fk_release_variant_analysis', SET_NULL, 'n'),
    )

    def setUp(self):
        self.assertTrue(connection.settings_dict['NAME'].startswith('gdb_test_'))
        self.release = self.new_release()
        self.variant = domain.Variant.objects.create(variant_type='synthetic-membership')

    def new_release(self):
        return domain.DataRelease.objects.create(
            name=uuid.uuid4().hex, version='v1', status='unlisted', reference_assembly='synthetic',
        )

    def membership(self, **changes):
        return domain.ReleaseVariant(**(dict(release_id=self.release.pk, variant_id=self.variant.pk) | changes))

    def linked_membership(self):
        placement = domain.VariantPlacement.objects.create(
            variant=domain.Variant.objects.create(variant_type='other-variant'),
            reference_assembly='other-assembly', contig='synthetic', start_pos=1, end_pos=1,
        )
        analysis = domain.Analysis.objects.create(
            release=self.new_release(), module='synthetic', pipeline_name='synthetic', pipeline_version='v1', status='unlisted',
        )
        membership = self.membership(placement_id=placement.pk, included_by_analysis_id=analysis.pk)
        membership.full_clean()  # SQL does not require placement variant/assembly or analysis release consistency.
        membership.save()
        return membership, {'release': self.release, 'variant': self.variant,
                            'placement': placement, 'included_by_analysis': analysis}

    def fk_actions(self):
        with connection.cursor() as cursor:
            cursor.execute('SELECT conname, confdeltype, confupdtype, condeferrable, condeferred FROM pg_constraint '
                           "WHERE conrelid = 'release_variant'::regclass AND contype = 'f'")
            return {row[0]: row[1:] for row in cursor.fetchall()}

    def fk_operation(self):
        migration = normalized_migration_slice('ReleaseVariant')
        return migration.operations[1], MigrationLoader(connection, replace_migrations=False).project_state([NORMALIZED_LEAF])

    def test_minimal_membership_uses_ordered_native_key_and_nullable_defaults(self):
        self.assertTrue(hasattr(domain, 'ReleaseVariant'), 'ReleaseVariant is missing.')
        before = timezone.now()
        membership = self.membership()
        created = membership.created_at
        membership.full_clean()
        membership.save()
        membership.refresh_from_db()
        self.assertEqual(membership.pk, (self.release.pk, self.variant.pk))
        self.assertEqual(domain.ReleaseVariant.objects.get(pk=membership.pk), membership)
        self.assertFalse(domain.ReleaseVariant.objects.filter(pk=tuple(reversed(membership.pk))).exists())
        self.assertEqual(membership.inclusion_status, 'included')
        self.assertEqual((membership.placement_id, membership.included_by_analysis_id), (None, None))
        self.assertEqual(membership.created_at, created)
        self.assertTrue(timezone.is_aware(created))
        self.assertLessEqual(before, created)
        self.assertLessEqual(created, timezone.now())

    def test_exact_six_columns_ordered_native_pk_four_fks_defaults_and_only_variant_index(self):
        columns = {
            'release_id': ('uuid', None, 'NO', None),
            'variant_id': ('uuid', None, 'NO', None),
            'placement_id': ('uuid', None, 'YES', None),
            'included_by_analysis_id': ('uuid', None, 'YES', None),
            'inclusion_status': ('character varying', 32, 'NO', "'included'::character varying"),
            'created_at': ('timestamp with time zone', None, 'NO', 'CURRENT_TIMESTAMP'),
        }
        model = domain.ReleaseVariant
        self.assertEqual((model._meta.db_table, model._meta.pk.name), ('release_variant', 'pk'))
        self.assertIsInstance(model._meta.pk, models.CompositePrimaryKey)
        self.assertEqual(model._meta.pk.field_names, ('release_id', 'variant_id'))
        self.assertEqual(tuple(field.attname for field in model._meta.pk.fields), ('release_id', 'variant_id'))
        self.assertIsNone(model._meta.pk.column)
        self.assertFalse(model._meta.pk.editable or model._meta.pk.has_default() or model._meta.pk.has_db_default())
        self.assertEqual([field.column for field in model._meta.local_fields if field.column], list(columns))
        self.assertEqual({field.name for field in model._meta.local_fields},
                         {'pk', 'release', 'variant', 'placement', 'included_by_analysis', 'inclusion_status', 'created_at'})
        for field in model._meta.local_fields:
            if field.column:
                _, length, nullable, _ = columns[field.column]
                self.assertEqual((field.null, field.blank), (nullable == 'YES', nullable == 'YES'))
                if length:
                    self.assertEqual(field.max_length, length)
                self.assertFalse(field.choices or field.db_index or field.unique or field.primary_key)
                self.assertEqual(field.has_default(), field.name in ('inclusion_status', 'created_at'))
                self.assertEqual(field.has_db_default(), field.name in ('inclusion_status', 'created_at'))
        status, created = model._meta.get_field('inclusion_status'), model._meta.get_field('created_at')
        self.assertEqual((status.default, status.db_default), ('included', 'included'))
        self.assertIs(created.default, timezone.now)
        self.assertIsInstance(created.db_default, TransactionNow)
        self.assertFalse(created.auto_now or created.auto_now_add)
        self.assertEqual(model._meta.constraints, [])
        self.assertEqual({index.name: index.fields for index in model._meta.indexes}, {'idx_release_variant_variant': ['variant']})
        for field, target, key, _, action, _ in self.fk_specs:
            relation = model._meta.get_field(field)
            self.assertIs(relation.remote_field.model, target)
            self.assertIs(relation.remote_field.on_delete, action)
            self.assertEqual((relation.column, relation.db_column, relation.target_field.name), (field + '_id', field + '_id', key))
            self.assertTrue(relation.db_constraint)
        with connection.cursor() as cursor:
            cursor.execute('SELECT column_name, data_type, character_maximum_length, is_nullable, column_default '
                           'FROM information_schema.columns WHERE table_schema = current_schema() '
                           "AND table_name = 'release_variant' ORDER BY ordinal_position")
            self.assertEqual(cursor.fetchall(), [(name, *spec) for name, spec in columns.items()])
            constraints = connection.introspection.get_constraints(cursor, 'release_variant')
            cursor.execute("SELECT indexname FROM pg_indexes WHERE schemaname = current_schema() AND tablename = 'release_variant'")
            self.assertEqual({row[0] for row in cursor.fetchall()}, {'release_variant_pkey', 'idx_release_variant_variant'})
            cursor.execute("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid = 'release_variant'::regclass AND contype = 'p'")
            self.assertEqual(cursor.fetchone()[0], 'PRIMARY KEY (release_id, variant_id)')
        self.assertEqual(set(constraints), {'release_variant_pkey', 'idx_release_variant_variant', *[spec[3] for spec in self.fk_specs]})
        self.assertEqual([info['columns'] for info in constraints.values() if info['primary_key']], [['release_id', 'variant_id']])
        self.assertFalse(any(info['check'] or info['unique'] and not info['primary_key'] for info in constraints.values()))
        self.assertEqual({name: info['columns'] for name, info in constraints.items() if info['index']},
                         {'idx_release_variant_variant': ['variant_id']})
        self.assertEqual({name: (info['columns'], info['foreign_key']) for name, info in constraints.items() if info['foreign_key']},
                         {name: ([field + '_id'], (target._meta.db_table, key)) for field, target, key, name, _, _ in self.fk_specs})
        self.assertEqual(self.fk_actions(), {name: (deletion, 'c', False, False) for _, _, _, name, _, deletion in self.fk_specs})

    def test_raw_minimal_insert_uses_unquoted_included_nullable_links_and_transaction_time_only(self):
        self.assertEqual(domain.ReleaseVariant.objects.count(), 0)
        others = (domain.DataRelease, domain.Variant, domain.VariantPlacement, domain.Analysis,
                  domain.VariantAnnotation, domain.AlleleFrequency, domain.ExternalIdentifier, domain.Population, domain.EpigeneticFeature)
        before = {model: model.objects.count() for model in others}
        with connection.cursor() as cursor:
            cursor.execute('INSERT INTO release_variant (release_id, variant_id) VALUES (%s, %s) '
                           'RETURNING placement_id, included_by_analysis_id, inclusion_status, created_at, transaction_timestamp()',
                           [self.release.pk, self.variant.pk])
            placement, analysis, status, created, database_now = cursor.fetchone()
        self.assertEqual((placement, analysis, status), (None, None, 'included'))
        self.assertTrue(timezone.is_aware(created))
        self.assertEqual(created, database_now)
        self.assertEqual({model: model.objects.count() for model in others}, before)

    def test_pair_uniqueness_allows_both_distinct_components_and_native_lookup_update_delete(self):
        first = self.membership()
        first.save()
        with self.assertRaises(ValidationError):
            self.membership(inclusion_status='custom').full_clean()
        for insert in (lambda: domain.ReleaseVariant.objects.create(release=self.release, variant=self.variant),
                       lambda: domain.ReleaseVariant.objects.bulk_create([self.membership(inclusion_status='custom')])):
            with self.assertRaises(IntegrityError) as error, transaction.atomic():
                insert()
            self.assertEqual(error.exception.__cause__.diag.constraint_name, 'release_variant_pkey')
        with self.assertRaises(IntegrityError) as error, transaction.atomic(), connection.cursor() as cursor:
            cursor.execute('INSERT INTO release_variant (release_id, variant_id) VALUES (%s, %s)', list(first.pk))
        self.assertEqual(error.exception.__cause__.diag.constraint_name, 'release_variant_pkey')
        second = self.membership(variant_id=domain.Variant.objects.create(variant_type='other').pk)
        third = self.membership(release_id=self.new_release().pk)
        for membership in (second, third):
            membership.full_clean()
            membership.save()
        self.assertEqual(set(domain.ReleaseVariant.objects.values_list('pk', flat=True)), {first.pk, second.pk, third.pk})
        self.assertEqual(domain.ReleaseVariant.objects.filter(pk=first.pk).update(inclusion_status='custom'), 1)
        first.refresh_from_db()
        self.assertEqual(first.inclusion_status, 'custom')
        first.delete()
        self.assertEqual(set(domain.ReleaseVariant.objects.values_list('pk', flat=True)), {second.pk, third.pk})

    def test_required_columns_reject_explicit_nulls_in_orm_and_sql(self):
        values = dict(release_id=self.release.pk, variant_id=self.variant.pk, inclusion_status='included', created_at=timezone.now())
        sql = f"INSERT INTO release_variant ({', '.join(values)}) VALUES ({', '.join(['%s'] * len(values))})"
        for field in values:
            with self.subTest(field=field):
                with self.assertRaises(ValidationError):
                    self.membership(**{field: None}).full_clean()
                with self.assertRaises(IntegrityError) as error, transaction.atomic(), connection.cursor() as cursor:
                    cursor.execute(sql, [None if name == field else value for name, value in values.items()])
                self.assertEqual(error.exception.__cause__.diag.column_name, field)

    def test_free_text_boundary_explicit_timestamp_and_unrelated_placement_analysis_have_no_inferred_rules(self):
        membership, _ = self.linked_membership()
        created = timezone.now() - timedelta(days=90)
        membership.inclusion_status, membership.created_at = 'custom-unlisted-status', created
        membership.full_clean()
        membership.save(update_fields=['inclusion_status', 'created_at'])
        membership.refresh_from_db()
        self.assertEqual((membership.inclusion_status, membership.created_at), ('custom-unlisted-status', created))
        membership.inclusion_status = 'x' * 32
        membership.full_clean()
        membership.save()
        membership.refresh_from_db()
        self.assertEqual(membership.inclusion_status, 'x' * 32)
        membership.inclusion_status = 'x' * 33
        with self.assertRaises(ValidationError):
            membership.full_clean()
        with self.assertRaises(DataError), transaction.atomic():
            membership.save()
        with self.assertRaises(DataError), transaction.atomic(), connection.cursor() as cursor:
            cursor.execute('UPDATE release_variant SET inclusion_status = %s WHERE release_id = %s AND variant_id = %s',
                           ['x' * 33, *membership.pk])
        with connection.cursor() as cursor:
            cursor.execute('UPDATE release_variant SET inclusion_status = %s WHERE release_id = %s AND variant_id = %s', ['', *membership.pk])
        membership.refresh_from_db()
        self.assertEqual(membership.inclusion_status, '')  # SQL has no status enum or nonempty CHECK.

    def test_raw_updates_of_all_four_parent_keys_cascade_including_both_pk_components(self):
        membership, parents = self.linked_membership()
        untouched = self.membership(release_id=self.new_release().pk, variant_id=domain.Variant.objects.create(variant_type='unrelated').pk)
        untouched.save()
        before = domain.ReleaseVariant.objects.filter(pk=untouched.pk).values().get()
        with connection.cursor() as cursor:
            for field, target, key, _, _, _ in self.fk_specs:
                parent, new_id, old_pair = parents[field], uuid.uuid4(), membership.pk
                cursor.execute(f'UPDATE {target._meta.db_table} SET {key} = %s WHERE {key} = %s', [new_id, parent.pk])
                parent.pk = new_id
                setattr(membership, field + '_id', new_id)
                membership.refresh_from_db()
                self.assertEqual(getattr(membership, field + '_id'), new_id)
                self.assertEqual(membership.pk, (self.release.pk, self.variant.pk))
                if field in ('release', 'variant'):
                    self.assertFalse(domain.ReleaseVariant.objects.filter(pk=old_pair).exists())
        self.assertEqual(domain.ReleaseVariant.objects.filter(pk=untouched.pk).values().get(), before)

    def test_raw_deletes_set_analysis_null_restrict_variant_placement_and_cascade_only_release_memberships(self):
        membership, parents = self.linked_membership()
        untouched = self.membership(release_id=self.new_release().pk)
        untouched.save()
        before = domain.ReleaseVariant.objects.filter(pk=untouched.pk).values().get()
        with connection.cursor() as cursor:
            analysis = parents['included_by_analysis']
            cursor.execute('DELETE FROM analysis WHERE analysis_id = %s', [analysis.pk])
            membership.refresh_from_db()
            self.assertIsNone(membership.included_by_analysis_id)
            for field in ('variant', 'placement'):
                parent = parents[field]
                with self.assertRaises(IntegrityError) as error, transaction.atomic():
                    cursor.execute('SET CONSTRAINTS ALL DEFERRED')
                    cursor.execute(f'DELETE FROM {parent._meta.db_table} WHERE {parent._meta.pk.column} = %s', [parent.pk])
                    self.fail('RESTRICT must reject the delete at the statement.')
                self.assertEqual(error.exception.__cause__.diag.constraint_name, f'fk_release_variant_{field}')
                self.assertTrue(type(parent).objects.filter(pk=parent.pk).exists())
            cursor.execute('DELETE FROM data_release WHERE release_id = %s', [self.release.pk])
        self.assertFalse(domain.ReleaseVariant.objects.filter(pk=membership.pk).exists())
        self.assertTrue(domain.Variant.objects.filter(pk=self.variant.pk).exists())
        self.assertTrue(domain.VariantPlacement.objects.filter(pk=parents['placement'].pk).exists())
        self.assertEqual(domain.ReleaseVariant.objects.filter(pk=untouched.pk).values().get(), before)

    def test_orm_reverse_relations_and_deletions_match_cascade_restrict_and_set_null(self):
        membership, parents = self.linked_membership()
        for parent, related in ((self.release, 'variant_memberships'), (self.variant, 'release_memberships'),
                                (parents['placement'], 'release_memberships'), (parents['included_by_analysis'], 'included_variant_memberships')):
            self.assertEqual(list(getattr(parent, related).all()), [membership])
        for field in ('variant', 'placement'):
            parent = parents[field]
            for delete in (parent.delete, lambda: type(parent).objects.filter(pk=parent.pk).delete()):
                with self.assertRaises(RestrictedError):
                    delete()
        parents['included_by_analysis'].delete()
        membership.refresh_from_db()
        self.assertIsNone(membership.included_by_analysis_id)
        pair = membership.pk
        self.release.delete()
        self.assertFalse(domain.ReleaseVariant.objects.filter(pk=pair).exists())
        self.assertTrue(domain.Variant.objects.filter(pk=self.variant.pk).exists())
        self.assertTrue(domain.VariantPlacement.objects.filter(pk=parents['placement'].pk).exists())

    def test_all_four_orphan_inserts_and_updates_fail_immediately_even_when_constraints_are_deferred(self):
        membership = self.membership()
        membership.save()
        insert_release = self.new_release()
        for field, _, _, name, _, _ in self.fk_specs:
            column, orphan = field + '_id', uuid.uuid4()
            with self.subTest(field=field):
                with self.assertRaises(ValidationError):
                    self.membership(**{column: orphan}).full_clean()
                values = dict(release_id=insert_release.pk, variant_id=self.variant.pk) | {column: orphan}
                insert = f"INSERT INTO release_variant ({', '.join(values)}) VALUES ({', '.join(['%s'] * len(values))})"
                for sql, args in ((insert, list(values.values())),
                                  (f'UPDATE release_variant SET {column} = %s WHERE release_id = %s AND variant_id = %s', [orphan, *membership.pk])):
                    with self.assertRaises(IntegrityError) as error, transaction.atomic(), connection.cursor() as cursor:
                        cursor.execute('SET CONSTRAINTS ALL DEFERRED')
                        cursor.execute(sql, args)
                        self.fail('Membership FK must reject an orphan at the statement, not transaction end.')
                    self.assertEqual(error.exception.__cause__.diag.constraint_name, name)

    def test_fk_reverse_restores_deferred_no_action_for_each_parent_then_forward_restores_actions(self):
        operation, state = self.fk_operation()
        membership, parents = self.linked_membership()
        connection.check_constraints()  # Flush Analysis.release's deferred trigger before DDL.
        expected = self.fk_actions()
        with connection.schema_editor() as editor, connection.cursor() as cursor:
            operation.database_backwards('genoma', editor, state, state)
            self.assertEqual(self.fk_actions(), {name: ('a', 'a', True, True) for name in expected})
            for field, target, key, name, _, _ in self.fk_specs:
                with self.subTest(field=field), self.assertRaises(IntegrityError) as error, transaction.atomic():
                    new_id = uuid.uuid4()
                    cursor.execute(f'UPDATE {target._meta.db_table} SET {key} = %s WHERE {key} = %s', [new_id, parents[field].pk])
                    membership.refresh_from_db()
                    self.assertEqual(getattr(membership, field + '_id'), parents[field].pk)
                    cursor.execute(f'DELETE FROM {target._meta.db_table} WHERE {key} = %s', [new_id])
                    self.assertTrue(domain.ReleaseVariant.objects.filter(pk=membership.pk).exists())
                    connection.check_constraints()  # NO ACTION is deferred, not a cascade, restrict or set-null.
                self.assertEqual(error.exception.__cause__.diag.constraint_name, name)
            operation.database_forwards('genoma', editor, state, state)
            self.assertEqual(self.fk_actions(), expected)

    def test_every_missing_or_ambiguous_lookup_fails_before_any_replacement_in_both_directions(self):
        operation, state = self.fk_operation()
        with connection.schema_editor() as editor, connection.cursor() as cursor:
            expected = self.fk_actions()
            for apply in (operation.database_forwards, operation.database_backwards):
                for field, target, key, name, _, _ in self.fk_specs:
                    for case, sql in (
                        ('missing', f'ALTER TABLE release_variant DROP CONSTRAINT {name}'),
                        ('ambiguous', f'ALTER TABLE release_variant ADD CONSTRAINT duplicate_fk FOREIGN KEY ({field}_id) '
                         f'REFERENCES {target._meta.db_table} ({key}) DEFERRABLE INITIALLY DEFERRED'),
                    ):
                        with self.subTest(direction=apply.__name__, field=field, case=case), transaction.atomic():
                            cursor.execute(sql)
                            before = self.fk_actions()
                            with patch.object(editor, 'execute', wraps=editor.execute) as execute:
                                with self.assertRaisesMessage(RuntimeError, 'Expected exactly one FK'):
                                    apply('genoma', editor, state, state)
                                execute.assert_not_called()
                            self.assertEqual(self.fk_actions(), before)
                            transaction.set_rollback(True)
                operation.database_backwards('genoma', editor, state, state)
            operation.database_forwards('genoma', editor, state, state)
            self.assertEqual(self.fk_actions(), expected)

    def test_lookup_matches_exact_relations_and_attnums_and_quotes_discovered_names(self):
        operation, state = self.fk_operation()
        with transaction.atomic(), connection.schema_editor() as editor, connection.cursor() as cursor:
            expected, decoys = self.fk_actions(), {}
            for field, target, key, name, _, _ in self.fk_specs:
                quoted = connection.ops.quote_name(f'generated "{field}" FK'.replace('"', '""'))
                cursor.execute(f'ALTER TABLE release_variant RENAME CONSTRAINT {name} TO {quoted}')
                cursor.execute(f'ALTER TABLE {target._meta.db_table} ADD COLUMN decoy_key uuid UNIQUE')
                other_table, other_key = ('data_release', 'release_id') if field == 'variant' else ('variant', 'variant_id')
                other_source = 'variant_id' if field == 'release' else 'release_id'
                for kind, source, table, column in (
                    ('source', other_source, target._meta.db_table, key),
                    ('target', field + '_id', target._meta.db_table, 'decoy_key'),
                    ('relation', field + '_id', other_table, other_key),
                ):
                    decoy = f'decoy_membership_{kind}_{field}'
                    cursor.execute(f'ALTER TABLE release_variant ADD CONSTRAINT {decoy} FOREIGN KEY ({source}) '
                                   f'REFERENCES {table} ({column}) DEFERRABLE INITIALLY DEFERRED')
                    decoys[decoy] = ('a', 'a', True, True)
            operation.database_forwards('genoma', editor, state, state)
            self.assertEqual(self.fk_actions(), expected | decoys)
            operation.database_backwards('genoma', editor, state, state)
            self.assertEqual(self.fk_actions(), {name: ('a', 'a', True, True) for name in expected} | decoys)
            transaction.set_rollback(True)

    def test_entire_migration_reverses_table_then_recreates_exact_schema_and_accepts_native_keys(self):
        migration = normalized_migration_slice('ReleaseVariant')
        prior = normalized_state_before('ReleaseVariant')
        membership = self.membership()
        membership.save()
        connection.check_constraints()
        expected = self.fk_actions()
        with connection.cursor() as cursor:
            constraints = connection.introspection.get_constraints(cursor, 'release_variant')
        with connection.schema_editor() as editor:
            migration.unapply(prior, editor)
        with connection.cursor() as cursor:
            self.assertNotIn('release_variant', connection.introspection.table_names(cursor))
        self.assertTrue(domain.DataRelease.objects.filter(pk=self.release.pk).exists())
        self.assertTrue(domain.Variant.objects.filter(pk=self.variant.pk).exists())
        with connection.schema_editor() as editor:
            migration.apply(prior.clone(), editor)
        self.assertEqual(domain.ReleaseVariant.objects.count(), 0)
        self.assertEqual(self.fk_actions(), expected)
        with connection.cursor() as cursor:
            self.assertEqual(connection.introspection.get_constraints(cursor, 'release_variant'), constraints)
        membership.save(force_insert=True)
        self.assertEqual(domain.ReleaseVariant.objects.get(pk=membership.pk), membership)

    def test_schema_only_migration_dependency_and_exact_state_match_native_composite_model(self):
        with self.assertNumQueries(0):
            reload(import_module('genoma.migrations.0011_release_variant'))
            migration = normalized_migration_slice('ReleaseVariant')
        self.assertEqual(migration.dependencies, normalized_dependencies('ReleaseVariant'))
        self.assertEqual([type(operation).__name__ for operation in migration.operations], ['CreateModel', 'RunPython'])
        self.assertEqual(migration.operations[0].name, 'ReleaseVariant')
        self.assertTrue(migration.operations[1].reversible)
        historical = MigrationLoader(connection, replace_migrations=False).project_state([NORMALIZED_LEAF]).apps.get_model('genoma', 'ReleaseVariant')
        current = domain.ReleaseVariant
        self.assertEqual(historical._meta.db_table, current._meta.db_table)
        self.assertEqual({field.name: field.deconstruct()[1:] for field in historical._meta.local_fields},
                         {field.name: field.deconstruct()[1:] for field in current._meta.local_fields})
        self.assertEqual(historical._meta.pk.field_names, ('release_id', 'variant_id'))
        self.assertEqual(historical._meta.indexes, current._meta.indexes)
        self.assertEqual(historical._meta.constraints, current._meta.constraints)
        call_command('check')
        call_command('makemigrations', check=True, dry_run=True)


class AlleleFrequencyTests(TestCase):
    count_fields = ('allele_count', 'allele_number', 'homozygote_count', 'heterozygote_count', 'sample_count')
    fk_specs = (
        ('release', domain.DataRelease, 'release_id', 'fk_allele_frequency_release', SET_NULL, 'n'),
        ('variant', domain.Variant, 'variant_id', 'fk_allele_frequency_variant', PROTECT, 'r'),
        ('population', domain.Population, 'population_id', 'fk_allele_frequency_population', PROTECT, 'r'),
        ('analysis', domain.Analysis, 'analysis_id', 'fk_allele_frequency_analysis', SET_NULL, 'n'),
    )

    def setUp(self):
        self.assertTrue(connection.settings_dict['NAME'].startswith('gdb_test_'))
        self.variant = domain.Variant.objects.create(variant_type='synthetic-frequency')
        self.population = domain.Population.objects.create(code='synthetic-frequency', name='Synthetic cohort')

    def frequency(self, **changes):
        return domain.AlleleFrequency(**(dict(
            variant=self.variant, population=self.population, source_name='custom-source', source_version='v1', allele='synthetic',
        ) | changes))

    def test_minimal_frequency_has_orm_defaults_and_nullable_fields(self):
        self.assertTrue(hasattr(domain, 'AlleleFrequency'), 'AlleleFrequency is missing.')
        before = timezone.now()
        frequency = self.frequency()
        created = frequency.created_at
        frequency.full_clean()
        frequency.save()
        frequency.refresh_from_db()
        self.assertIsInstance(frequency.pk, uuid.UUID)
        self.assertEqual(frequency.pk.version, 4)
        self.assertEqual(frequency.created_at, created)
        self.assertTrue(timezone.is_aware(created))
        self.assertLessEqual(before, created)
        self.assertLessEqual(created, timezone.now())
        for field in ('release_id', 'analysis_id', 'allele_count', 'allele_number', 'allele_frequency',
                      'homozygote_count', 'heterozygote_count', 'sample_count', 'quality_flags'):
            self.assertIsNone(getattr(frequency, field))

    def release(self):
        return domain.DataRelease.objects.create(
            name=uuid.uuid4().hex, version='v1', status='unlisted', reference_assembly='synthetic',
        )

    def linked_frequency(self):
        release = self.release()
        analysis = domain.Analysis.objects.create(
            release=self.release(), module='synthetic', pipeline_name='synthetic', pipeline_version='v1', status='unlisted',
        )  # Frequency and analysis releases need not match.
        frequency = self.frequency(release=release, analysis=analysis)
        frequency.full_clean()
        frequency.save()
        return frequency, release, analysis

    def fk_actions(self):
        with connection.cursor() as cursor:
            cursor.execute('SELECT conname, confdeltype, confupdtype, condeferrable, condeferred FROM pg_constraint '
                           "WHERE conrelid = 'allele_frequency'::regclass AND contype = 'f'")
            return {row[0]: row[1:] for row in cursor.fetchall()}

    def test_exact_sixteen_columns_types_sizes_nullability_defaults_and_constraints(self):
        columns = {
            'frequency_id': ('uuid', None, None, None, 'NO', None),
            'release_id': ('uuid', None, None, None, 'YES', None),
            'variant_id': ('uuid', None, None, None, 'NO', None),
            'population_id': ('uuid', None, None, None, 'NO', None),
            'analysis_id': ('uuid', None, None, None, 'YES', None),
            'source_name': ('character varying', 128, None, None, 'NO', None),
            'source_version': ('character varying', 64, None, None, 'NO', None),
            'allele': ('text', None, None, None, 'NO', None),
            **{field: ('bigint', None, 64, 0, 'YES', None) for field in self.count_fields},
            'allele_frequency': ('numeric', None, 12, 10, 'YES', None),
            'quality_flags': ('jsonb', None, None, None, 'YES', None),
            'created_at': ('timestamp with time zone', None, None, None, 'NO', 'CURRENT_TIMESTAMP'),
        }
        model = domain.AlleleFrequency
        self.assertEqual((model._meta.db_table, model._meta.pk.name), ('allele_frequency', 'frequency_id'))
        self.assertEqual({field.column for field in model._meta.local_fields}, set(columns))
        self.assertIs(model._meta.pk.default, uuid.uuid4)
        self.assertFalse(model._meta.pk.editable)
        for field in model._meta.local_fields:
            _, length, _, _, nullable, _ = columns[field.column]
            self.assertEqual((field.null, field.blank), (nullable == 'YES', nullable == 'YES'))
            if length is not None:
                self.assertEqual(field.max_length, length)
            self.assertFalse(field.choices or field.db_index or field.unique and not field.primary_key)
            self.assertEqual(field.has_default(), field.name in ('frequency_id', 'created_at'))
            self.assertEqual(field.has_db_default(), field.name == 'created_at')
        for name in self.count_fields:
            self.assertEqual(model._meta.get_field(name).get_internal_type(), 'BigIntegerField')
        value = model._meta.get_field('allele_frequency')
        self.assertEqual((value.max_digits, value.decimal_places), (12, 10))
        created = model._meta.get_field('created_at')
        self.assertIs(created.default, timezone.now)
        self.assertIsInstance(created.db_default, TransactionNow)
        self.assertFalse(created.auto_now or created.auto_now_add)
        indexes = {'idx_frequency_variant_population': ['variant', 'population'],
                   'idx_frequency_source': ['source_name', 'source_version']}
        self.assertEqual({index.name: index.fields for index in model._meta.indexes}, indexes)
        unique, *checks = model._meta.constraints
        unique_columns = ['release_id', 'variant_id', 'population_id', 'source_name', 'source_version', 'allele']
        self.assertEqual((unique.name, list(unique.fields)),
                         ('uq_allele_frequency_record', [name.removesuffix('_id') for name in unique_columns]))
        self.assertIsNone(unique.nulls_distinct)
        self.assertIsNone(unique.deferrable)
        self.assertIsNone(unique.condition)
        self.assertFalse(unique.expressions or unique.include or unique.opclasses)
        check_columns = {f'allele_frequency_{field}_gte_0': {field} for field in self.count_fields}
        check_columns['allele_frequency_value_range'] = {'allele_frequency'}
        self.assertEqual({check.name for check in checks}, set(check_columns))
        for field, target, key, _, action, _ in self.fk_specs:
            relation = model._meta.get_field(field)
            self.assertIs(relation.remote_field.model, target)
            self.assertIs(relation.remote_field.on_delete, action)
            self.assertEqual(relation.target_field.name, key)
        with connection.cursor() as cursor:
            cursor.execute('SELECT column_name, data_type, character_maximum_length, numeric_precision, numeric_scale, '
                           'is_nullable, column_default FROM information_schema.columns '
                           "WHERE table_schema = current_schema() AND table_name = 'allele_frequency'")
            self.assertEqual({row[0]: row[1:] for row in cursor.fetchall()}, columns)
            constraints = connection.introspection.get_constraints(cursor, 'allele_frequency')
            cursor.execute('SELECT indexname FROM pg_indexes WHERE schemaname = current_schema() '
                           "AND tablename = 'allele_frequency'")
            self.assertEqual({row[0] for row in cursor.fetchall()},
                             {'allele_frequency_pkey', 'uq_allele_frequency_record', *indexes})
            cursor.execute("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid = 'allele_frequency'::regclass "
                           "AND conname = 'uq_allele_frequency_record'")
            self.assertEqual(cursor.fetchone()[0], f"UNIQUE ({', '.join(unique_columns)})")
        self.assertEqual(set(constraints), {'allele_frequency_pkey', 'uq_allele_frequency_record', *indexes,
                                           *check_columns, *[spec[3] for spec in self.fk_specs]})
        self.assertEqual([info['columns'] for info in constraints.values() if info['primary_key']], [['frequency_id']])
        self.assertEqual({name: info['columns'] for name, info in constraints.items() if info['unique'] and not info['primary_key']},
                         {'uq_allele_frequency_record': unique_columns})
        self.assertEqual({name: info['columns'] for name, info in constraints.items() if info['index']},
                         indexes | {'idx_frequency_variant_population': ['variant_id', 'population_id']})
        self.assertEqual({name: set(info['columns']) for name, info in constraints.items() if info['check']}, check_columns)
        self.assertEqual({name: (info['columns'], info['foreign_key']) for name, info in constraints.items() if info['foreign_key']},
                         {name: ([field + '_id'], (target._meta.db_table, key)) for field, target, key, name, _, _ in self.fk_specs})
        self.assertEqual(self.fk_actions(), {name: (deletion, 'c', False, False) for _, _, _, name, _, deletion in self.fk_specs})

    def test_raw_defaults_are_nullable_and_transaction_time_without_seeds_or_other_writes(self):
        self.assertEqual(domain.AlleleFrequency.objects.count(), 0)
        others = (domain.DataRelease, domain.Variant, domain.Population, domain.Analysis,
                  domain.VariantPlacement, domain.VariantAnnotation, domain.ExternalIdentifier, domain.EpigeneticFeature)
        before = {model: model.objects.count() for model in others}
        with connection.cursor() as cursor:
            cursor.execute('INSERT INTO allele_frequency (frequency_id, variant_id, population_id, source_name, source_version, allele) '
                           'VALUES (%s, %s, %s, %s, %s, %s) RETURNING release_id, analysis_id, allele_count, allele_number, '
                           'allele_frequency, homozygote_count, heterozygote_count, sample_count, quality_flags, '
                           'created_at, transaction_timestamp()',
                           [uuid.uuid4(), self.variant.pk, self.population.pk, 'custom-source', 'v1', 'synthetic'])
            *optional, created, database_now = cursor.fetchone()
        self.assertEqual(optional, [None] * 9)
        self.assertTrue(timezone.is_aware(created))
        self.assertEqual(created, database_now)
        self.assertEqual({model: model.objects.count() for model in others}, before)

    def test_required_columns_and_primary_key_reject_nulls_and_duplicates(self):
        values = dict(frequency_id=uuid.uuid4(), variant_id=self.variant.pk, population_id=self.population.pk,
                      source_name='synthetic', source_version='v1', allele='synthetic', created_at=timezone.now())
        sql = f"INSERT INTO allele_frequency ({', '.join(values)}) VALUES ({', '.join(['%s'] * len(values))})"
        for field in values:
            with self.subTest(null_column=field):
                if field != 'frequency_id':
                    with self.assertRaises(ValidationError):
                        self.frequency(**{field: None}).full_clean()
                with self.assertRaises(IntegrityError) as error, transaction.atomic():
                    with connection.cursor() as cursor:
                        cursor.execute(sql, [None if name == field else value for name, value in values.items()])
                self.assertEqual(error.exception.__cause__.diag.column_name, field)
        first = self.frequency()
        first.save()
        with self.assertRaises(ValidationError):
            self.frequency(frequency_id=first.pk).full_clean()
        with self.assertRaises(IntegrityError) as error, transaction.atomic():
            domain.AlleleFrequency.objects.bulk_create([self.frequency(frequency_id=first.pk)])
        self.assertEqual(error.exception.__cause__.diag.constraint_name, 'allele_frequency_pkey')
        with self.assertRaises(IntegrityError) as error, transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(sql, list((values | {'frequency_id': first.pk}).values()))
        self.assertEqual(error.exception.__cause__.diag.constraint_name, 'allele_frequency_pkey')

    def test_varchar_boundaries_and_unbounded_allele_text(self):
        for field, length in (('source_name', 128), ('source_version', 64)):
            with self.subTest(field=field):
                boundary = self.frequency(**{field: 'x' * length})
                boundary.full_clean()
                boundary.save()
                boundary.refresh_from_db()
                self.assertEqual(getattr(boundary, field), 'x' * length)
                too_long = self.frequency(**{field: 'x' * (length + 1)})
                with self.assertRaises(ValidationError):
                    too_long.full_clean()
                with self.assertRaises(DataError), transaction.atomic():
                    too_long.save()
                with self.assertRaises(DataError), transaction.atomic():
                    with connection.cursor() as cursor:
                        cursor.execute(f'UPDATE allele_frequency SET {field} = %s WHERE frequency_id = %s',
                                       ['x' * (length + 1), boundary.pk])
        frequency = self.frequency(allele='unlisted symbolic allele ' * 1000)
        frequency.full_clean()
        frequency.save()
        frequency.refresh_from_db()
        self.assertEqual(frequency.allele, 'unlisted symbolic allele ' * 1000)

    def test_five_nullable_nonnegative_bigint_counts_enforce_bounds_on_inserts_and_updates(self):
        for field in self.count_fields:
            with self.subTest(field=field):
                for value in (None, 0, 2**63 - 1):
                    frequency = self.frequency(**{field: value})
                    frequency.full_clean()
                    frequency.save()
                    frequency.refresh_from_db()
                    self.assertEqual(getattr(frequency, field), value)
                constraint = f'allele_frequency_{field}_gte_0'
                with self.assertRaises(ValidationError) as error:
                    self.frequency(**{field: -1}).full_clean()
                self.assertIn(constraint, str(error.exception))
                with self.assertRaises(IntegrityError) as error, transaction.atomic():
                    self.frequency(**{field: -1}).save()
                self.assertEqual(error.exception.__cause__.diag.constraint_name, constraint)
                with self.assertRaises(IntegrityError) as error, transaction.atomic():
                    with connection.cursor() as cursor:
                        cursor.execute(f'UPDATE allele_frequency SET {field} = -1 WHERE frequency_id = %s', [frequency.pk])
                self.assertEqual(error.exception.__cause__.diag.constraint_name, constraint)
                for overflow in (2**63, -2**63 - 1):
                    with self.assertRaises(ValidationError):
                        self.frequency(**{field: overflow}).full_clean()
                    with self.assertRaises(DataError), transaction.atomic():
                        self.frequency(**{field: overflow}).save()

    def test_nullable_numeric_precision_inclusive_range_rounding_and_overflow(self):
        for value in (None, Decimal('0'), Decimal('1'), Decimal('0.0000000001'), Decimal('0.9999999999')):
            with self.subTest(value=value):
                frequency = self.frequency(allele_frequency=value)
                frequency.full_clean()
                frequency.save()
                frequency.refresh_from_db()
                self.assertEqual(frequency.allele_frequency, value)
        for value in ('-0.0000000001', '1.0000000001', '99.9999999999'):
            with self.subTest(out_of_range=value):
                with self.assertRaises(ValidationError):
                    self.frequency(allele_frequency=Decimal(value)).full_clean()
                with self.assertRaises(IntegrityError) as error, transaction.atomic():
                    self.frequency(allele_frequency=Decimal(value)).save()
                self.assertEqual(error.exception.__cause__.diag.constraint_name, 'allele_frequency_value_range')
                with self.assertRaises(IntegrityError) as error, transaction.atomic():
                    with connection.cursor() as cursor:
                        cursor.execute('UPDATE allele_frequency SET allele_frequency = %s WHERE frequency_id = %s',
                                       [Decimal(value), frequency.pk])
                self.assertEqual(error.exception.__cause__.diag.constraint_name, 'allele_frequency_value_range')
        for value in ('100', '-100'):
            with self.subTest(overflow=value):
                with self.assertRaises(ValidationError):
                    self.frequency(allele_frequency=Decimal(value)).full_clean()
                with self.assertRaises(DataError), transaction.atomic():
                    self.frequency(allele_frequency=Decimal(value)).save()
        for value, rounded in (('0.00000000001', '0'), ('0.00000000005', '0.0000000001'),
                               ('-0.00000000004', '0'), ('1.00000000004', '1')):
            with self.subTest(rounding=value):
                with self.assertRaises(ValidationError):
                    self.frequency(allele_frequency=Decimal(value)).full_clean()
                with connection.cursor() as cursor:
                    cursor.execute('UPDATE allele_frequency SET allele_frequency = %s WHERE frequency_id = %s RETURNING allele_frequency',
                                   [Decimal(value), frequency.pk])
                    self.assertEqual(cursor.fetchone()[0], Decimal(rounded))

    def test_jsonb_explicit_timestamp_and_inconsistent_counts_have_no_inferred_semantics(self):
        _, _, analysis = self.linked_frequency()
        before = {model: model.objects.count() for model in (domain.Variant, domain.Population, domain.Analysis, domain.DataRelease)}
        values = dict(analysis=analysis, allele='unlisted allele', allele_count=10, allele_number=0,
                      allele_frequency=Decimal('1'), homozygote_count=500, heterozygote_count=600, sample_count=0,
                      created_at=timezone.now() - timedelta(days=1))
        for flags in ({'nested': {'flag': True, 'missing': None}}, ['unlisted', 3, False], 'custom', 42, True):
            with self.subTest(flags=flags):
                frequency = self.frequency(**(values | {'quality_flags': flags}))
                frequency.full_clean()
                frequency.save()
                frequency.refresh_from_db()
                self.assertEqual(frequency.quality_flags, flags)
                self.assertEqual({field: getattr(frequency, field) for field in values}, values)
        self.assertEqual({model: model.objects.count() for model in before}, before)
        with self.assertRaises(ValidationError):
            self.frequency(quality_flags={'unserializable': {1}}).full_clean()

    def test_unique_record_uses_nulls_distinct_but_rejects_nonnull_duplicates(self):
        for _ in range(2):
            frequency = self.frequency()
            frequency.full_clean()
            frequency.save()
        with connection.cursor() as cursor:
            cursor.execute('INSERT INTO allele_frequency (frequency_id, variant_id, population_id, source_name, source_version, allele) '
                           'VALUES (%s, %s, %s, %s, %s, %s)',
                           [uuid.uuid4(), self.variant.pk, self.population.pk, 'custom-source', 'v1', 'synthetic'])
        self.assertEqual(domain.AlleleFrequency.objects.count(), 3)
        release = self.release()
        first = self.frequency(release=release)
        first.full_clean()
        first.save()
        analysis = domain.Analysis.objects.create(module='synthetic', pipeline_name='synthetic', pipeline_version='v1', status='unlisted')
        for changes in ({}, {'analysis': analysis, 'allele_count': 99, 'quality_flags': ['different']}):
            with self.subTest(changes=changes):
                duplicate = self.frequency(**({'release': release} | changes))
                with self.assertRaises(ValidationError):
                    duplicate.full_clean()
                with self.assertRaises(IntegrityError) as error, transaction.atomic():
                    duplicate.save()
                self.assertEqual(error.exception.__cause__.diag.constraint_name, 'uq_allele_frequency_record')
        with self.assertRaises(IntegrityError) as error, transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute('INSERT INTO allele_frequency (frequency_id, release_id, variant_id, population_id, source_name, source_version, allele) '
                               'VALUES (%s, %s, %s, %s, %s, %s, %s)',
                               [uuid.uuid4(), release.pk, self.variant.pk, self.population.pk, 'custom-source', 'v1', 'synthetic'])
        self.assertEqual(error.exception.__cause__.diag.constraint_name, 'uq_allele_frequency_record')
        with self.assertRaises(IntegrityError) as error, transaction.atomic():
            domain.AlleleFrequency.objects.filter(pk=frequency.pk).update(release=release)
        self.assertEqual(error.exception.__cause__.diag.constraint_name, 'uq_allele_frequency_record')
        other_variant = domain.Variant.objects.create(variant_type='synthetic-other')
        other_population = domain.Population.objects.create(code='synthetic-other', name='Other synthetic cohort')
        for changes in ({'release': self.release()}, {'variant': other_variant}, {'population': other_population},
                        {'source_name': 'other'}, {'source_version': 'v2'}, {'allele': 'other'}):
            with self.subTest(distinct=changes):
                distinct = self.frequency(**({'release': release} | changes))
                distinct.full_clean()
                distinct.save()

    def test_raw_key_updates_cascade_and_deletes_only_null_optional_links_or_restrict(self):
        frequency, release, analysis = self.linked_frequency()
        untouched = self.frequency(
            variant=domain.Variant.objects.create(variant_type='unrelated'),
            population=domain.Population.objects.create(code='unrelated', name='Unrelated cohort'),
        )
        untouched.save()
        before = domain.AlleleFrequency.objects.filter(pk=untouched.pk).values().get()
        parents = {'release': release, 'variant': self.variant, 'population': self.population, 'analysis': analysis}
        with connection.cursor() as cursor:
            for field, target, key, _, _, _ in self.fk_specs:
                parent, new_id = parents[field], uuid.uuid4()
                cursor.execute(f'UPDATE {target._meta.db_table} SET {key} = %s WHERE {key} = %s', [new_id, parent.pk])
                frequency.refresh_from_db()
                self.assertEqual(getattr(frequency, field + '_id'), new_id)
                parent.pk = new_id
            for field in ('release', 'analysis'):
                parent = parents[field]
                cursor.execute(f'DELETE FROM {parent._meta.db_table} WHERE {parent._meta.pk.column} = %s', [parent.pk])
                frequency.refresh_from_db()
                self.assertIsNone(getattr(frequency, field + '_id'))
                self.assertEqual((frequency.variant_id, frequency.population_id), (self.variant.pk, self.population.pk))
            for field in ('variant', 'population'):
                parent = parents[field]
                with self.assertRaises(IntegrityError) as error, transaction.atomic():
                    cursor.execute('SET CONSTRAINTS ALL DEFERRED')
                    cursor.execute(f'DELETE FROM {parent._meta.db_table} WHERE {parent._meta.pk.column} = %s', [parent.pk])
                    self.fail('RESTRICT must reject the delete at the statement.')
                self.assertEqual(error.exception.__cause__.diag.constraint_name, f'fk_allele_frequency_{field}')
                self.assertTrue(type(parent).objects.filter(pk=parent.pk).exists())
        self.assertEqual(domain.AlleleFrequency.objects.filter(pk=untouched.pk).values().get(), before)
        self.assertTrue(domain.AlleleFrequency.objects.filter(pk=frequency.pk).exists())

    def test_orm_deletes_set_null_or_protect_without_cascading_frequency_rows(self):
        frequency, release, analysis = self.linked_frequency()
        release.delete()
        analysis.delete()
        frequency.refresh_from_db()
        self.assertEqual((frequency.release_id, frequency.analysis_id), (None, None))
        for parent in (self.variant, self.population):
            with self.assertRaises(ProtectedError):
                parent.delete()
        self.assertTrue(domain.AlleleFrequency.objects.filter(pk=frequency.pk).exists())

    def test_all_four_orphan_inserts_and_updates_fail_immediately_even_when_deferred(self):
        frequency = self.frequency()
        frequency.save()
        for field, _, _, name, _, _ in self.fk_specs:
            column, orphan = field + '_id', uuid.uuid4()
            with self.subTest(field=field):
                with self.assertRaises(ValidationError):
                    self.frequency(**{column: orphan}).full_clean()
                values = dict(frequency_id=uuid.uuid4(), variant_id=self.variant.pk, population_id=self.population.pk,
                              source_name='custom-source', source_version='v1', allele='synthetic') | {column: orphan}
                insert = f"INSERT INTO allele_frequency ({', '.join(values)}) VALUES ({', '.join(['%s'] * len(values))})"
                for sql, args in ((insert, list(values.values())),
                                  (f'UPDATE allele_frequency SET {column} = %s WHERE frequency_id = %s', [orphan, frequency.pk])):
                    with self.assertRaises(IntegrityError) as error, transaction.atomic():
                        with connection.cursor() as cursor:
                            cursor.execute('SET CONSTRAINTS ALL DEFERRED')
                            cursor.execute(sql, args)
                            self.fail('Frequency FK must reject an orphan at the statement, not transaction end.')
                    self.assertEqual(error.exception.__cause__.diag.constraint_name, name)

    def test_fk_reverse_restores_deferred_no_action_then_forward_restores_physical_actions(self):
        operation = normalized_migration_slice('AlleleFrequency').operations[1]
        state = MigrationLoader(connection, replace_migrations=False).project_state([NORMALIZED_LEAF])
        frequency, release, analysis = self.linked_frequency()
        parents = {'release': release, 'variant': self.variant, 'population': self.population, 'analysis': analysis}
        # Flush the fixture's unrelated, deferred Analysis.release FK before schema DDL.
        connection.check_constraints()
        expected = self.fk_actions()
        with connection.schema_editor() as editor, connection.cursor() as cursor:
            operation.database_backwards('genoma', editor, state, state)
            self.assertEqual(self.fk_actions(), {name: ('a', 'a', True, True) for name in expected})
            for field, target, key, _, _, _ in self.fk_specs:
                with self.subTest(field=field), transaction.atomic():
                    # Both updates may temporarily violate a deferred FK; no cascade occurs on reversal.
                    cursor.execute(f'UPDATE {target._meta.db_table} SET {key} = %s WHERE {key} = %s',
                                   [uuid.uuid4(), parents[field].pk])
                    frequency.refresh_from_db()
                    self.assertEqual(getattr(frequency, field + '_id'), parents[field].pk)
                    cursor.execute(f'UPDATE allele_frequency SET {field}_id = %s WHERE frequency_id = %s',
                                   [uuid.uuid4(), frequency.pk])
                    transaction.set_rollback(True)
            operation.database_forwards('genoma', editor, state, state)
            self.assertEqual(self.fk_actions(), expected)

    def test_every_missing_or_ambiguous_lookup_fails_before_any_fk_replacement_in_both_directions(self):
        operation = normalized_migration_slice('AlleleFrequency').operations[1]
        state = MigrationLoader(connection, replace_migrations=False).project_state([NORMALIZED_LEAF])
        with connection.schema_editor() as editor, connection.cursor() as cursor:
            expected = self.fk_actions()
            for apply in (operation.database_forwards, operation.database_backwards):
                for field, target, key, name, _, _ in self.fk_specs:
                    for case, sql in (
                        ('missing', f'ALTER TABLE allele_frequency DROP CONSTRAINT {name}'),
                        ('ambiguous', f'ALTER TABLE allele_frequency ADD CONSTRAINT duplicate_fk FOREIGN KEY ({field}_id) '
                         f'REFERENCES {target._meta.db_table} ({key}) DEFERRABLE INITIALLY DEFERRED'),
                    ):
                        with self.subTest(direction=apply.__name__, field=field, case=case), transaction.atomic():
                            cursor.execute(sql)
                            before = self.fk_actions()
                            with patch.object(editor, 'execute', wraps=editor.execute) as execute:
                                with self.assertRaisesMessage(RuntimeError, 'Expected exactly one FK'):
                                    apply('genoma', editor, state, state)
                                execute.assert_not_called()
                            self.assertEqual(self.fk_actions(), before)
                            transaction.set_rollback(True)
                operation.database_backwards('genoma', editor, state, state)
            operation.database_forwards('genoma', editor, state, state)
            self.assertEqual(self.fk_actions(), expected)

    def test_fk_lookup_matches_exact_relations_attnums_and_quotes_discovered_names(self):
        operation = normalized_migration_slice('AlleleFrequency').operations[1]
        state = MigrationLoader(connection, replace_migrations=False).project_state([NORMALIZED_LEAF])
        with transaction.atomic(), connection.schema_editor() as editor, connection.cursor() as cursor:
            expected, decoys = self.fk_actions(), {}
            for field, target, key, name, _, _ in self.fk_specs:
                quoted = connection.ops.quote_name(f'generated "{field}" FK'.replace('"', '""'))
                cursor.execute(f'ALTER TABLE allele_frequency RENAME CONSTRAINT {name} TO {quoted}')
                cursor.execute(f'ALTER TABLE {target._meta.db_table} ADD COLUMN decoy_key uuid UNIQUE')
                other_table, other_key = ('population', 'population_id') if field == 'variant' else ('variant', 'variant_id')
                for kind, source, table, column in (
                    ('source', 'frequency_id', target._meta.db_table, key),
                    ('target', field + '_id', target._meta.db_table, 'decoy_key'),
                    ('relation', field + '_id', other_table, other_key),
                ):
                    decoy = f'decoy_frequency_{kind}_{field}'
                    cursor.execute(f'ALTER TABLE allele_frequency ADD CONSTRAINT {decoy} FOREIGN KEY ({source}) '
                                   f'REFERENCES {table} ({column}) DEFERRABLE INITIALLY DEFERRED')
                    decoys[decoy] = ('a', 'a', True, True)
            operation.database_forwards('genoma', editor, state, state)
            self.assertEqual(self.fk_actions(), expected | decoys)
            operation.database_backwards('genoma', editor, state, state)
            self.assertEqual(self.fk_actions(), {name: ('a', 'a', True, True) for name in expected} | decoys)
            transaction.set_rollback(True)

    def test_schema_only_migration_dependency_state_and_postgresql_index_deconstruction(self):
        with self.assertNumQueries(0):
            reload(import_module('genoma.migrations.0010_allele_frequency'))
            migration = normalized_migration_slice('AlleleFrequency')
        self.assertEqual(migration.dependencies, normalized_dependencies('AlleleFrequency'))
        self.assertEqual([type(operation).__name__ for operation in migration.operations], ['CreateModel', 'RunPython'])
        self.assertEqual(migration.operations[0].name, 'AlleleFrequency')
        self.assertTrue(migration.operations[1].reversible)
        historical = MigrationLoader(connection, replace_migrations=False).project_state([NORMALIZED_LEAF]).apps.get_model('genoma', 'AlleleFrequency')
        self.assertEqual(historical._meta.db_table, domain.AlleleFrequency._meta.db_table)
        self.assertEqual({field.name: field.deconstruct()[1:] for field in historical._meta.local_fields},
                         {field.name: field.deconstruct()[1:] for field in domain.AlleleFrequency._meta.local_fields})
        self.assertEqual(historical._meta.indexes, domain.AlleleFrequency._meta.indexes)
        self.assertEqual(historical._meta.constraints, domain.AlleleFrequency._meta.constraints)
        index = domain.AlleleFrequency._meta.indexes[0]
        self.assertIsInstance(index, domain.PostgreSQLIndex)
        self.assertEqual(index.max_name_length, 63)
        path, args, kwargs = index.deconstruct()
        self.assertEqual(path, 'genoma.models.PostgreSQLIndex')
        self.assertEqual(domain.PostgreSQLIndex(*args, **kwargs).deconstruct(), index.deconstruct())
        call_command('check')
        call_command('makemigrations', check=True, dry_run=True)


class VariantAnnotationTests(TestCase):
    fk_specs = (
        ('variant', domain.Variant, 'variant_id', 'fk_variant_annotation_variant', CASCADE, 'c'),
        ('placement', domain.VariantPlacement, 'placement_id', 'fk_variant_annotation_placement', SET_NULL, 'n'),
        ('analysis', domain.Analysis, 'analysis_id', 'fk_variant_annotation_analysis', SET_NULL, 'n'),
    )

    def setUp(self):
        self.assertTrue(connection.settings_dict['NAME'].startswith('gdb_test_'))
        self.variant = domain.Variant.objects.create(variant_type='synthetic-annotation')

    def annotation(self, **changes):
        return domain.VariantAnnotation(**(dict(
            variant=self.variant, source_name='custom-source', source_version='v1', annotation_type='unlisted-type',
        ) | changes))

    def test_minimal_annotation_has_orm_defaults_and_nullable_fields(self):
        self.assertTrue(hasattr(domain, 'VariantAnnotation'), 'VariantAnnotation is missing.')
        before = timezone.now()
        annotation = self.annotation()
        created = annotation.created_at
        self.assertLessEqual(before, created)
        self.assertLessEqual(created, timezone.now())
        annotation.full_clean()
        annotation.save()
        annotation.refresh_from_db()
        self.assertIsInstance(annotation.pk, uuid.UUID)
        self.assertEqual(annotation.pk.version, 4)
        self.assertEqual(annotation.variant, self.variant)
        self.assertEqual(annotation.created_at, created)
        self.assertTrue(timezone.is_aware(created))
        for field in ('placement_id', 'analysis_id', 'gene_symbol', 'transcript_id', 'consequence',
                      'clinical_significance', 'evidence_level', 'score', 'citation_id', 'payload'):
            self.assertIsNone(getattr(annotation, field))

    def fk_actions(self):
        with connection.cursor() as cursor:
            cursor.execute('SELECT conname, confdeltype, confupdtype, condeferrable, condeferred FROM pg_constraint '
                           "WHERE conrelid = 'variant_annotation'::regclass AND contype = 'f'")
            return {row[0]: row[1:] for row in cursor.fetchall()}

    def linked_annotation(self):
        other = domain.Variant.objects.create(variant_type='synthetic-other')
        placement = domain.VariantPlacement.objects.create(
            variant=other, reference_assembly='synthetic', contig='1', start_pos=1, end_pos=1,
        )  # SQL does not require the annotation and placement to reference the same variant.
        analysis = domain.Analysis.objects.create(
            module='synthetic', pipeline_name='synthetic', pipeline_version='v1', status='unlisted-status',
        )
        annotation = self.annotation(placement=placement, analysis=analysis)
        annotation.full_clean()
        annotation.save()
        return annotation, placement, analysis

    def test_exact_sixteen_columns_precision_defaults_pk_fks_and_only_three_indexes(self):
        columns = {
            'annotation_id': ('uuid', None, None, None, 'NO', None),
            'variant_id': ('uuid', None, None, None, 'NO', None),
            'placement_id': ('uuid', None, None, None, 'YES', None),
            'analysis_id': ('uuid', None, None, None, 'YES', None),
            'source_name': ('character varying', 128, None, None, 'NO', None),
            'source_version': ('character varying', 64, None, None, 'NO', None),
            'annotation_type': ('character varying', 96, None, None, 'NO', None),
            'gene_symbol': ('character varying', 64, None, None, 'YES', None),
            'transcript_id': ('character varying', 128, None, None, 'YES', None),
            'consequence': ('character varying', 128, None, None, 'YES', None),
            'clinical_significance': ('character varying', 128, None, None, 'YES', None),
            'evidence_level': ('character varying', 64, None, None, 'YES', None),
            'score': ('numeric', None, 20, 10, 'YES', None),
            'citation_id': ('character varying', 128, None, None, 'YES', None),
            'payload': ('jsonb', None, None, None, 'YES', None),
            'created_at': ('timestamp with time zone', None, None, None, 'NO', 'CURRENT_TIMESTAMP'),
        }
        model = domain.VariantAnnotation
        self.assertEqual((model._meta.db_table, model._meta.pk.name), ('variant_annotation', 'annotation_id'))
        self.assertEqual({field.column for field in model._meta.local_fields}, set(columns))
        self.assertIs(model._meta.pk.default, uuid.uuid4)
        self.assertFalse(model._meta.pk.editable)
        for field in model._meta.local_fields:
            _, length, _, _, nullable, _ = columns[field.column]
            self.assertEqual((field.null, field.blank), (nullable == 'YES', nullable == 'YES'))
            if length is not None:
                self.assertEqual(field.max_length, length)
            self.assertFalse(field.choices or field.db_index or field.unique and not field.primary_key)
            self.assertEqual(field.has_default(), field.name in ('annotation_id', 'created_at'))
            self.assertEqual(field.has_db_default(), field.name == 'created_at')
        score, created = (model._meta.get_field(name) for name in ('score', 'created_at'))
        self.assertEqual((score.max_digits, score.decimal_places), (20, 10))
        self.assertIs(created.default, timezone.now)
        self.assertIsInstance(created.db_default, TransactionNow)
        self.assertFalse(created.auto_now or created.auto_now_add)
        indexes = {'idx_variant_annotation_variant': ['variant'],
                   'idx_variant_annotation_source': ['source_name', 'source_version'],
                   'idx_variant_annotation_gene': ['gene_symbol']}
        self.assertEqual({index.name: index.fields for index in model._meta.indexes}, indexes)
        self.assertEqual(model._meta.constraints, [])
        for field, target, key, _, action, _ in self.fk_specs:
            relation = model._meta.get_field(field)
            self.assertIs(relation.remote_field.model, target)
            self.assertIs(relation.remote_field.on_delete, action)
            self.assertEqual(relation.target_field.name, key)
        with connection.cursor() as cursor:
            cursor.execute('SELECT column_name, data_type, character_maximum_length, numeric_precision, numeric_scale, '
                           'is_nullable, column_default FROM information_schema.columns '
                           "WHERE table_schema = current_schema() AND table_name = 'variant_annotation'")
            self.assertEqual({row[0]: row[1:] for row in cursor.fetchall()}, columns)
            constraints = connection.introspection.get_constraints(cursor, 'variant_annotation')
            cursor.execute('SELECT indexname FROM pg_indexes WHERE schemaname = current_schema() '
                           "AND tablename = 'variant_annotation'")
            self.assertEqual({row[0] for row in cursor.fetchall()}, {'variant_annotation_pkey', *indexes})
        self.assertEqual(set(constraints), {'variant_annotation_pkey', *indexes, *[spec[3] for spec in self.fk_specs]})
        self.assertEqual([info['columns'] for info in constraints.values() if info['primary_key']], [['annotation_id']])
        self.assertEqual({name: (info['columns'], info['foreign_key']) for name, info in constraints.items() if info['foreign_key']},
                         {name: ([field + '_id'], (target._meta.db_table, key)) for field, target, key, name, _, _ in self.fk_specs})
        self.assertEqual({name: info['columns'] for name, info in constraints.items() if info['index']},
                         indexes | {'idx_variant_annotation_variant': ['variant_id']})
        self.assertFalse(any(info['check'] or info['unique'] and not info['primary_key'] for info in constraints.values()))
        self.assertEqual(self.fk_actions(), {name: (deletion, 'c', False, False) for _, _, _, name, _, deletion in self.fk_specs})

    def test_raw_defaults_are_nullable_and_transaction_time_without_seeds_or_other_writes(self):
        self.assertEqual(domain.VariantAnnotation.objects.count(), 0)
        others = (domain.Variant, domain.VariantPlacement, domain.Analysis,
                  domain.DataRelease, domain.ExternalIdentifier, domain.Population, domain.EpigeneticFeature)
        before = {model: model.objects.count() for model in others}
        with connection.cursor() as cursor:
            cursor.execute('INSERT INTO variant_annotation (annotation_id, variant_id, source_name, source_version, annotation_type) '
                           'VALUES (%s, %s, %s, %s, %s) RETURNING placement_id, analysis_id, gene_symbol, transcript_id, consequence, '
                           'clinical_significance, evidence_level, score, citation_id, payload, created_at, transaction_timestamp()',
                           [uuid.uuid4(), self.variant.pk, 'custom-source', 'v1', 'unlisted-type'])
            *optional, created, database_now = cursor.fetchone()
        self.assertEqual(optional, [None] * 10)
        self.assertTrue(timezone.is_aware(created))
        self.assertEqual(created, database_now)
        self.annotation().save()  # Identical provenance is allowed; no inferred uniqueness or enums.
        self.assertEqual(domain.VariantAnnotation.objects.count(), 2)
        self.assertEqual({model: model.objects.count() for model in others}, before)

    def test_required_columns_and_primary_key_reject_nulls_and_duplicates(self):
        values = dict(annotation_id=uuid.uuid4(), variant_id=self.variant.pk, source_name='synthetic',
                      source_version='v1', annotation_type='synthetic', created_at=timezone.now())
        columns = ', '.join(connection.ops.quote_name(field) for field in values)
        sql = f"INSERT INTO variant_annotation ({columns}) VALUES ({', '.join(['%s'] * len(values))})"
        for field in values:
            with self.subTest(null_column=field):
                if field != 'annotation_id':
                    with self.assertRaises(ValidationError):
                        self.annotation(**{field: None}).full_clean()
                with self.assertRaises(IntegrityError) as error, transaction.atomic():
                    with connection.cursor() as cursor:
                        cursor.execute(sql, [None if name == field else value for name, value in values.items()])
                self.assertEqual(error.exception.__cause__.diag.column_name, field)
        first = self.annotation()
        first.save()
        with self.assertRaises(ValidationError):
            self.annotation(annotation_id=first.pk).full_clean()
        with self.assertRaises(IntegrityError), transaction.atomic():
            domain.VariantAnnotation.objects.bulk_create([self.annotation(annotation_id=first.pk)])
        with self.assertRaises(IntegrityError) as error, transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(sql, list((values | {'annotation_id': first.pk}).values()))
        self.assertEqual(error.exception.__cause__.diag.constraint_name, 'variant_annotation_pkey')

    def test_all_varchar_boundaries_and_overflows(self):
        for field, length in (('source_name', 128), ('source_version', 64), ('annotation_type', 96), ('gene_symbol', 64),
                              ('transcript_id', 128), ('consequence', 128), ('clinical_significance', 128),
                              ('evidence_level', 64), ('citation_id', 128)):
            with self.subTest(field=field):
                boundary = self.annotation(**{field: 'x' * length})
                boundary.full_clean()
                boundary.save()
                boundary.refresh_from_db()
                self.assertEqual(getattr(boundary, field), 'x' * length)
                too_long = self.annotation(**{field: 'x' * (length + 1)})
                with self.assertRaises(ValidationError):
                    too_long.full_clean()
                with self.assertRaises(DataError), transaction.atomic():
                    too_long.save()

    def test_numeric_precision_extremes_rounding_and_overflow_without_score_limits(self):
        for value in ('9999999999.9999999999', '-9999999999.9999999999', '0.0000000001', '-0.0000000001', '0'):
            with self.subTest(value=value):
                annotation = self.annotation(score=Decimal(value))
                annotation.full_clean()
                annotation.save()
                annotation.refresh_from_db()
                self.assertEqual(annotation.score, Decimal(value))
        annotation = self.annotation()
        annotation.save()
        for value in ('10000000000', '-10000000000', '9999999999.99999999995', '-9999999999.99999999995'):
            with self.subTest(overflow=value):
                with self.assertRaises(ValidationError):
                    self.annotation(score=Decimal(value)).full_clean()
                with self.assertRaises(DataError), transaction.atomic():
                    self.annotation(score=Decimal(value)).save()
        for value, rounded in (('0.00000000001', '0'), ('0.00000000005', '0.0000000001'), ('-0.00000000005', '-0.0000000001')):
            with self.subTest(rounding=value):
                with self.assertRaises(ValidationError):
                    self.annotation(score=Decimal(value)).full_clean()
                with connection.cursor() as cursor:
                    cursor.execute('UPDATE variant_annotation SET score = %s WHERE annotation_id = %s RETURNING score',
                                   [Decimal(value), annotation.pk])
                    self.assertEqual(cursor.fetchone()[0], Decimal(rounded))

    def test_json_and_explicit_timestamp_round_trip_without_payload_schema_rules(self):
        created = timezone.now() - timedelta(days=1)
        for payload in ({'tags': ['synthetic'], 'nested': {'flag': True, 'missing': None}}, ['synthetic', 3, False], 'custom', 42, True):
            with self.subTest(payload=payload):
                annotation = self.annotation(payload=payload, created_at=created)
                annotation.full_clean()
                annotation.save()
                annotation.refresh_from_db()
                self.assertEqual((annotation.payload, annotation.created_at), (payload, created))
        with self.assertRaises(ValidationError):
            self.annotation(payload={'unserializable': {1}}).full_clean()

    def test_raw_pk_updates_cascade_and_deletes_cascade_or_set_null_only_linked_rows(self):
        annotation, placement, analysis = self.linked_annotation()
        other = domain.Variant.objects.create(variant_type='synthetic-unrelated')
        untouched = self.annotation(variant=other)
        untouched.save()
        with connection.cursor() as cursor:
            for field, target, key, _, _, _ in self.fk_specs:
                obj = {'variant': self.variant, 'placement': placement, 'analysis': analysis}[field]
                new_id = uuid.uuid4()
                cursor.execute(f'UPDATE {connection.ops.quote_name(target._meta.db_table)} SET {key} = %s WHERE {key} = %s', [new_id, obj.pk])
                annotation.refresh_from_db()
                self.assertEqual(getattr(annotation, field + '_id'), new_id)
                obj.pk = new_id
            for obj, field in ((placement, 'placement'), (analysis, 'analysis')):
                cursor.execute(f'DELETE FROM {connection.ops.quote_name(obj._meta.db_table)} WHERE {obj._meta.pk.column} = %s', [obj.pk])
                annotation.refresh_from_db()
                self.assertIsNone(getattr(annotation, field + '_id'))
                self.assertEqual(annotation.variant_id, self.variant.pk)
            cursor.execute('DELETE FROM variant WHERE variant_id = %s', [self.variant.pk])
        self.assertEqual(list(domain.VariantAnnotation.objects.values_list('pk', flat=True)), [untouched.pk])
        self.assertTrue(domain.Variant.objects.filter(pk=other.pk).exists())

    def test_orm_deletion_matches_physical_actions(self):
        annotation, placement, analysis = self.linked_annotation()
        placement.delete()
        analysis.delete()
        annotation.refresh_from_db()
        self.assertEqual((annotation.placement_id, annotation.analysis_id), (None, None))
        self.variant.delete()
        self.assertFalse(domain.VariantAnnotation.objects.filter(pk=annotation.pk).exists())

    def test_all_orphan_inserts_and_updates_fail_at_statement_even_when_deferred(self):
        annotation = self.annotation()
        annotation.save()
        for field, _, _, name, _, _ in self.fk_specs:
            column, orphan = field + '_id', uuid.uuid4()
            with self.subTest(field=field):
                with self.assertRaises(ValidationError):
                    self.annotation(**{column: orphan}).full_clean()
                values = dict(annotation_id=uuid.uuid4(), variant_id=self.variant.pk, source_name='custom-source',
                              source_version='v1', annotation_type='unlisted-type') | {column: orphan}
                columns = ', '.join(connection.ops.quote_name(name) for name in values)
                insert = f"INSERT INTO variant_annotation ({columns}) VALUES ({', '.join(['%s'] * len(values))})"
                for sql, args in (
                    (insert, list(values.values())),
                    (f'UPDATE variant_annotation SET {column} = %s WHERE annotation_id = %s', [orphan, annotation.pk]),
                ):
                    with self.assertRaises(IntegrityError) as error, transaction.atomic():
                        with connection.cursor() as cursor:
                            cursor.execute('SET CONSTRAINTS ALL DEFERRED')
                            cursor.execute(sql, args)
                            self.fail('Annotation FK must reject an orphan at the statement, not transaction end.')
                    self.assertEqual(error.exception.__cause__.diag.constraint_name, name)

    def test_fk_reverse_and_every_missing_or_ambiguous_lookup_fail_before_any_replacement(self):
        operation = normalized_migration_slice('VariantAnnotation').operations[1]
        state = MigrationLoader(connection, replace_migrations=False).project_state([NORMALIZED_LEAF])
        with connection.schema_editor() as editor, connection.cursor() as cursor:
            expected = self.fk_actions()
            operation.database_backwards('genoma', editor, state, state)
            self.assertEqual(self.fk_actions(), {name: ('a', 'a', True, True) for name in expected})
            for apply in (operation.database_forwards, operation.database_backwards):
                for field, target, key, name, _, _ in self.fk_specs:
                    for case, sql in (
                        ('missing', f'ALTER TABLE variant_annotation DROP CONSTRAINT {name}'),
                        ('ambiguous', f'ALTER TABLE variant_annotation ADD CONSTRAINT duplicate_fk FOREIGN KEY ({field}_id) '
                         f'REFERENCES {target._meta.db_table} ({key}) DEFERRABLE INITIALLY DEFERRED'),
                    ):
                        with self.subTest(direction=apply.__name__, field=field, case=case), transaction.atomic():
                            cursor.execute(sql)
                            before = self.fk_actions()
                            with self.assertRaisesMessage(RuntimeError, 'Expected exactly one FK'):
                                apply('genoma', editor, state, state)
                            self.assertEqual(self.fk_actions(), before)
                            transaction.set_rollback(True)
                operation.database_forwards('genoma', editor, state, state)
            self.assertEqual(self.fk_actions(), expected)

    def test_fk_lookup_uses_exact_relations_attnums_and_quotes_discovered_names(self):
        operation = normalized_migration_slice('VariantAnnotation').operations[1]
        state = MigrationLoader(connection, replace_migrations=False).project_state([NORMALIZED_LEAF])
        with transaction.atomic(), connection.schema_editor() as editor, connection.cursor() as cursor:
            expected, decoys = self.fk_actions(), {}
            for field, target, key, name, _, _ in self.fk_specs:
                quoted = connection.ops.quote_name(f'generated "{field}" FK'.replace('"', '""'))
                cursor.execute(f'ALTER TABLE variant_annotation RENAME CONSTRAINT {name} TO {quoted}')
                cursor.execute(f'ALTER TABLE {target._meta.db_table} ADD COLUMN decoy_key uuid UNIQUE')
                for kind, source, table, column in (
                    ('source', 'annotation_id', target._meta.db_table, key),
                    ('target', field + '_id', target._meta.db_table, 'decoy_key'),
                    ('relation', field + '_id', 'population', 'population_id'),
                ):
                    decoy = f'decoy_{kind}_{field}'
                    cursor.execute(f'ALTER TABLE variant_annotation ADD CONSTRAINT {decoy} FOREIGN KEY ({source}) '
                                   f'REFERENCES {table} ({column}) DEFERRABLE INITIALLY DEFERRED')
                    decoys[decoy] = ('a', 'a', True, True)
            operation.database_forwards('genoma', editor, state, state)
            self.assertEqual(self.fk_actions(), expected | decoys)
            operation.database_backwards('genoma', editor, state, state)
            self.assertEqual(self.fk_actions(), {name: ('a', 'a', True, True) for name in expected} | decoys)
            transaction.set_rollback(True)

    def test_schema_only_migration_dependency_and_state_match_model(self):
        with self.assertNumQueries(0):
            reload(import_module('genoma.migrations.0009_variant_annotation'))
            migration = normalized_migration_slice('VariantAnnotation')
        self.assertEqual(migration.dependencies, normalized_dependencies('VariantAnnotation'))
        self.assertEqual([type(operation).__name__ for operation in migration.operations], ['CreateModel', 'RunPython'])
        self.assertEqual(migration.operations[0].name, 'VariantAnnotation')
        self.assertTrue(migration.operations[1].reversible)
        historical = MigrationLoader(connection, replace_migrations=False).project_state([NORMALIZED_LEAF]).apps.get_model('genoma', 'VariantAnnotation')
        self.assertEqual(historical._meta.db_table, domain.VariantAnnotation._meta.db_table)
        self.assertEqual({field.name: field.deconstruct()[1:] for field in historical._meta.local_fields},
                         {field.name: field.deconstruct()[1:] for field in domain.VariantAnnotation._meta.local_fields})
        self.assertEqual(historical._meta.indexes, domain.VariantAnnotation._meta.indexes)
        self.assertEqual(historical._meta.constraints, domain.VariantAnnotation._meta.constraints)
        call_command('check')
        call_command('makemigrations', check=True, dry_run=True)


class EpigeneticFeatureTests(TestCase):
    def setUp(self):
        self.assertTrue(connection.settings_dict['NAME'].startswith('gdb_test_'))

    def feature(self, **changes):
        return domain.EpigeneticFeature(**(dict(
            feature_type='synthetic-feature', reference_assembly='GRCh38', contig='1', start_pos=1, end_pos=1,
        ) | changes))

    def test_minimal_feature_has_orm_defaults_and_nullable_fields(self):
        self.assertTrue(hasattr(domain, 'EpigeneticFeature'), 'EpigeneticFeature is missing.')
        before = timezone.now()
        feature = self.feature()
        created = feature.created_at
        self.assertLessEqual(before, created)
        self.assertLessEqual(created, timezone.now())
        feature.full_clean()
        feature.save()
        feature.refresh_from_db()
        self.assertIsInstance(feature.pk, uuid.UUID)
        self.assertEqual(feature.pk.version, 4)
        self.assertEqual(feature.coordinate_system, '1-based-inclusive')
        self.assertEqual(feature.created_at, created)
        self.assertTrue(timezone.is_aware(created))
        for field in ('strand', 'modification_code', 'name', 'metadata'):
            self.assertIsNone(getattr(feature, field))

    def test_exact_twelve_columns_defaults_keys_checks_and_only_region_index(self):
        columns = {
            'epigenetic_feature_id': ('uuid', None, 'NO', None),
            'feature_type': ('character varying', 64, 'NO', None),
            'reference_assembly': ('character varying', 32, 'NO', None),
            'contig': ('character varying', 64, 'NO', None),
            'start_pos': ('bigint', None, 'NO', None),
            'end_pos': ('bigint', None, 'NO', None),
            'coordinate_system': ('character varying', 32, 'NO', "'1-based-inclusive'::character varying"),
            'strand': ('character', 1, 'YES', None),
            'modification_code': ('character varying', 32, 'YES', None),
            'name': ('character varying', 255, 'YES', None),
            'metadata': ('jsonb', None, 'YES', None),
            'created_at': ('timestamp with time zone', None, 'NO', 'CURRENT_TIMESTAMP'),
        }
        model = domain.EpigeneticFeature
        self.assertEqual((model._meta.db_table, model._meta.pk.name), ('epigenetic_feature', 'epigenetic_feature_id'))
        self.assertEqual({field.column for field in model._meta.local_fields}, set(columns))
        self.assertIs(model._meta.pk.default, uuid.uuid4)
        self.assertFalse(model._meta.pk.editable)
        for field in model._meta.local_fields:
            _, length, nullable, _ = columns[field.column]
            self.assertEqual((field.null, field.blank), (nullable == 'YES', nullable == 'YES'))
            if length is not None:
                self.assertEqual(field.max_length, length)
            self.assertFalse(field.is_relation or field.db_index or field.choices)
            self.assertEqual(field.has_default(), field.name in ('epigenetic_feature_id', 'coordinate_system', 'created_at'))
            self.assertEqual(field.has_db_default(), field.name in ('coordinate_system', 'created_at'))
        coordinate = model._meta.get_field('coordinate_system')
        # Correct SQL v01.5's triple-quoted literal to the semantic, unquoted value.
        self.assertEqual((coordinate.default, coordinate.db_default), ('1-based-inclusive', '1-based-inclusive'))
        created = model._meta.get_field('created_at')
        self.assertIs(created.default, timezone.now)
        self.assertIsInstance(created.db_default, TransactionNow)
        self.assertFalse(created.auto_now or created.auto_now_add)
        self.assertIsInstance(model._meta.get_field('strand'), domain.FixedCharField)
        region = {'idx_epigenetic_feature_region': ['reference_assembly', 'contig', 'start_pos', 'end_pos']}
        self.assertEqual({index.name: index.fields for index in model._meta.indexes}, region)
        with connection.cursor() as cursor:
            cursor.execute('SELECT column_name, data_type, character_maximum_length, is_nullable, column_default '
                           'FROM information_schema.columns WHERE table_schema = current_schema() '
                           "AND table_name = 'epigenetic_feature'")
            self.assertEqual({row[0]: row[1:] for row in cursor.fetchall()}, columns)
            constraints = connection.introspection.get_constraints(cursor, 'epigenetic_feature')
            cursor.execute('SELECT indexname FROM pg_indexes WHERE schemaname = current_schema() '
                           "AND tablename = 'epigenetic_feature'")
            self.assertEqual({row[0] for row in cursor.fetchall()}, {'epigenetic_feature_pkey', *region})
        self.assertEqual([info['columns'] for info in constraints.values() if info['primary_key']], [['epigenetic_feature_id']])
        self.assertFalse(any(info['foreign_key'] or info['unique'] and not info['primary_key'] for info in constraints.values()))
        self.assertEqual({name: info['columns'] for name, info in constraints.items() if info['index']}, region)
        checks = {'epigenetic_feature_start_gte_1': {'start_pos'},
                  'epigenetic_feature_end_gte_start': {'end_pos', 'start_pos'}}
        self.assertEqual({constraint.name for constraint in model._meta.constraints}, set(checks))
        self.assertEqual({name: set(info['columns']) for name, info in constraints.items() if info['check']}, checks)

    def test_raw_sql_defaults_are_unquoted_nullable_and_transaction_time(self):
        with connection.cursor() as cursor:
            cursor.execute('INSERT INTO epigenetic_feature '
                           '(epigenetic_feature_id, feature_type, reference_assembly, contig, start_pos, end_pos) '
                           'VALUES (%s, %s, %s, %s, %s, %s) RETURNING coordinate_system, strand, modification_code, '
                           'name, metadata, created_at, transaction_timestamp()',
                           [uuid.uuid4(), 'synthetic-feature', 'GRCh38', '1', 1, 1])
            coordinate, *optional, created, database_now = cursor.fetchone()
        self.assertEqual(coordinate, '1-based-inclusive')
        self.assertEqual(optional, [None] * 4)
        self.assertTrue(timezone.is_aware(created))
        self.assertEqual(created, database_now)

    def test_explicit_values_and_duplicate_regions_preserve_unrelated_normalized_rows(self):
        variant = domain.Variant.objects.create(variant_type='synthetic', canonical_name='Preserved normalized row')
        other_models = (domain.Analysis, domain.DataRelease, domain.Variant,
                        domain.VariantPlacement, domain.ExternalIdentifier, domain.Population)
        before = {model: model.objects.count() for model in other_models}
        self.assertEqual(domain.EpigeneticFeature.objects.count(), 0)  # No seeds.
        values = dict(feature_type='unlisted-feature-type', reference_assembly='synthetic-assembly',
                      contig='synthetic-contig', start_pos=2**40, end_pos=2**40 + 2,
                      coordinate_system='synthetic-coordinates', strand='?', modification_code='unlisted-modification',
                      name='Synthetic definition', metadata={'tags': ['synthetic'], 'details': {'count': 2}},
                      created_at=timezone.now() - timedelta(days=1))
        for _ in range(2):
            feature = self.feature(**values)
            feature.full_clean()
            feature.save()
            feature.refresh_from_db()
            self.assertEqual({field: getattr(feature, field) for field in values}, values)
        self.assertEqual(domain.EpigeneticFeature.objects.count(), 2)  # No interval uniqueness or ontology inference.
        self.assertEqual({model: model.objects.count() for model in other_models}, before)
        variant.refresh_from_db()
        self.assertEqual(variant.canonical_name, 'Preserved normalized row')

    def test_coordinate_checks_apply_to_orm_inserts_and_sql_updates(self):
        valid = self.feature()
        valid.full_clean()
        valid.save()  # Inclusive single-base features at position one are valid.
        upper = self.feature(start_pos=2**63 - 1, end_pos=2**63 - 1)
        upper.full_clean()
        upper.save()
        for changes, constraint in (
            ({'start_pos': 0}, 'epigenetic_feature_start_gte_1'),
            ({'start_pos': -1}, 'epigenetic_feature_start_gte_1'),
            ({'start_pos': 2, 'end_pos': 1}, 'epigenetic_feature_end_gte_start'),
        ):
            with self.subTest(changes=changes):
                feature = self.feature(**changes)
                with self.assertRaises(ValidationError) as error:
                    feature.full_clean()
                self.assertIn(constraint, str(error.exception))
                with self.assertRaises(IntegrityError) as error, transaction.atomic():
                    feature.save()
                self.assertEqual(error.exception.__cause__.diag.constraint_name, constraint)
                with self.assertRaises(IntegrityError) as error, transaction.atomic():
                    with connection.cursor() as cursor:
                        cursor.execute('UPDATE epigenetic_feature SET start_pos = %s, end_pos = %s '
                                       'WHERE epigenetic_feature_id = %s', [feature.start_pos, feature.end_pos, valid.pk])
                self.assertEqual(error.exception.__cause__.diag.constraint_name, constraint)
        valid.refresh_from_db()
        self.assertEqual((valid.start_pos, valid.end_pos), (1, 1))
        self.assertEqual(domain.EpigeneticFeature.objects.count(), 2)

    def test_required_columns_and_primary_key_are_enforced_in_orm_and_sql(self):
        values = dict(epigenetic_feature_id=uuid.uuid4(), feature_type='synthetic-feature', reference_assembly='GRCh38',
                      contig='1', start_pos=1, end_pos=1, coordinate_system='1-based-inclusive', created_at=timezone.now())
        columns = ', '.join(connection.ops.quote_name(field) for field in values)
        placeholders = ', '.join(['%s'] * len(values))
        sql = f'INSERT INTO epigenetic_feature ({columns}) VALUES ({placeholders})'
        for field in values:
            with self.subTest(null_column=field):
                if field != 'epigenetic_feature_id':
                    with self.assertRaises(ValidationError) as error:
                        self.feature(**{field: None}).full_clean()
                    self.assertIn(field, error.exception.message_dict)
                with self.assertRaises(IntegrityError) as error, transaction.atomic():
                    with connection.cursor() as cursor:
                        cursor.execute(sql, [None if name == field else value for name, value in values.items()])
                self.assertEqual(error.exception.__cause__.diag.column_name, field)
        for field in ('feature_type', 'reference_assembly', 'contig', 'coordinate_system'):
            with self.subTest(blank_field=field):
                with self.assertRaises(ValidationError) as error:
                    self.feature(**{field: ''}).full_clean()
                self.assertIn(field, error.exception.message_dict)
        first = self.feature()
        first.save()
        duplicate = self.feature(epigenetic_feature_id=first.pk)
        with self.assertRaises(ValidationError):
            duplicate.full_clean()
        with self.assertRaises(IntegrityError) as error, transaction.atomic():
            domain.EpigeneticFeature.objects.bulk_create([duplicate])
        self.assertEqual(error.exception.__cause__.diag.constraint_name, 'epigenetic_feature_pkey')
        with self.assertRaises(IntegrityError) as error, transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(sql, list((values | {'epigenetic_feature_id': first.pk}).values()))
        self.assertEqual(error.exception.__cause__.diag.constraint_name, 'epigenetic_feature_pkey')
        self.assertEqual(domain.EpigeneticFeature.objects.count(), 1)

    def test_varchar_and_fixed_char_boundaries_and_overflows_in_orm_and_sql(self):
        for field, length in (('feature_type', 64), ('reference_assembly', 32), ('contig', 64),
                              ('coordinate_system', 32), ('strand', 1), ('modification_code', 32), ('name', 255)):
            with self.subTest(field=field):
                boundary = self.feature(**{field: 'x' * length})
                boundary.full_clean()
                boundary.save()
                boundary.refresh_from_db()
                self.assertEqual(getattr(boundary, field), 'x' * length)
                too_long = self.feature(**{field: 'x' * (length + 1)})
                with self.assertRaises(ValidationError) as error:
                    too_long.full_clean()
                self.assertIn(field, error.exception.message_dict)
                with self.assertRaises(DataError), transaction.atomic():
                    too_long.save()
                with self.assertRaises(DataError), transaction.atomic():
                    with connection.cursor() as cursor:
                        cursor.execute(f'UPDATE epigenetic_feature SET {connection.ops.quote_name(field)} = %s '
                                       'WHERE epigenetic_feature_id = %s', ['x' * (length + 1), boundary.pk])
                boundary.refresh_from_db()
                self.assertEqual(getattr(boundary, field), 'x' * length)

    def test_schema_only_migration_dependency_state_and_fixed_char_deconstruction(self):
        with self.assertNumQueries(0):
            reload(import_module('genoma.migrations.0008_epigenetic_feature'))
            migration = normalized_migration_slice('EpigeneticFeature')
        self.assertEqual(migration.dependencies, normalized_dependencies('EpigeneticFeature'))
        self.assertEqual([type(operation).__name__ for operation in migration.operations], ['CreateModel'])
        self.assertEqual(migration.operations[0].name, 'EpigeneticFeature')
        historical = MigrationLoader(connection, replace_migrations=False).project_state([NORMALIZED_LEAF]).apps.get_model(
            'genoma', 'EpigeneticFeature',
        )
        self.assertEqual(historical._meta.db_table, domain.EpigeneticFeature._meta.db_table)
        self.assertEqual({field.name: field.deconstruct()[1:] for field in historical._meta.local_fields},
                         {field.name: field.deconstruct()[1:] for field in domain.EpigeneticFeature._meta.local_fields})
        self.assertEqual(historical._meta.indexes, domain.EpigeneticFeature._meta.indexes)
        self.assertEqual(historical._meta.constraints, domain.EpigeneticFeature._meta.constraints)
        field = domain.EpigeneticFeature._meta.get_field('strand')
        _, path, args, kwargs = field.deconstruct()
        self.assertEqual(path, 'genoma.models.FixedCharField')
        rebuilt = domain.FixedCharField(*args, **kwargs)
        self.assertEqual(rebuilt.deconstruct()[1:], field.deconstruct()[1:])
        self.assertEqual(rebuilt.db_type(connection), 'char(1)')
        call_command('check')
        call_command('makemigrations', check=True, dry_run=True)


class PopulationTests(TestCase):
    def setUp(self):
        self.assertTrue(connection.settings_dict['NAME'].startswith('gdb_test_'))

    def population(self, **changes):
        return domain.Population(**(dict(code=uuid.uuid4().hex, name='Synthetic cohort') | changes))

    def fk_actions(self):
        with connection.cursor() as cursor:
            cursor.execute('SELECT conname, confdeltype, confupdtype, condeferrable, condeferred FROM pg_constraint '
                           "WHERE conrelid = 'population'::regclass AND contype = 'f'")
            return {row[0]: row[1:] for row in cursor.fetchall()}

    def test_minimal_population_has_orm_defaults_and_nullable_fields(self):
        self.assertTrue(hasattr(domain, 'Population'), 'Population is missing.')
        population = domain.Population(code='unlisted-population', name='Synthetic cohort')
        population.full_clean()
        population.save()
        population.refresh_from_db()
        self.assertIsInstance(population.pk, uuid.UUID)
        self.assertEqual(population.pk.version, 4)
        self.assertEqual((population.code, population.name), ('unlisted-population', 'Synthetic cohort'))
        self.assertIs(population.is_internal, False)
        self.assertIs(population.is_masked, False)
        self.assertTrue(timezone.is_aware(population.created_at))
        for field in ('parent_population_id', 'description', 'geographic_region', 'metadata'):
            self.assertIsNone(getattr(population, field))

    def test_exact_ten_columns_defaults_keys_self_fk_and_no_extra_indexes_or_checks(self):
        columns = {
            'population_id': ('uuid', None, 'NO', None),
            'parent_population_id': ('uuid', None, 'YES', None),
            'code': ('character varying', 64, 'NO', None),
            'name': ('character varying', 128, 'NO', None),
            'description': ('text', None, 'YES', None),
            'geographic_region': ('character varying', 128, 'YES', None),
            'is_internal': ('boolean', None, 'NO', 'false'),
            'is_masked': ('boolean', None, 'NO', 'false'),
            'metadata': ('jsonb', None, 'YES', None),
            'created_at': ('timestamp with time zone', None, 'NO', 'CURRENT_TIMESTAMP'),
        }
        model = domain.Population
        self.assertEqual((model._meta.db_table, model._meta.pk.name), ('population', 'population_id'))
        self.assertEqual({field.column for field in model._meta.local_fields}, set(columns))
        self.assertIs(model._meta.pk.default, uuid.uuid4)
        self.assertFalse(model._meta.pk.editable)
        for field in model._meta.local_fields:
            _, length, nullable, _ = columns[field.column]
            self.assertEqual((field.null, field.blank), (nullable == 'YES', nullable == 'YES'))
            if length is not None:
                self.assertEqual(field.max_length, length)
            self.assertFalse(field.choices)
            self.assertEqual(field.has_default(), field.name in ('population_id', 'is_internal', 'is_masked', 'created_at'))
            self.assertEqual(field.has_db_default(), field.name in ('is_internal', 'is_masked', 'created_at'))
        for name in ('is_internal', 'is_masked'):
            field = model._meta.get_field(name)
            self.assertIs(field.default, False)
            self.assertIs(field.db_default, False)
        created = model._meta.get_field('created_at')
        self.assertIs(created.default, timezone.now)
        self.assertIsInstance(created.db_default, TransactionNow)
        parent = model._meta.get_field('parent_population')
        self.assertIs(parent.remote_field.model, model)
        self.assertIs(parent.remote_field.on_delete, SET_NULL)
        self.assertEqual(parent.target_field.name, 'population_id')
        self.assertFalse(parent.db_index)
        self.assertEqual(model._meta.indexes, [])
        unique, = model._meta.constraints
        self.assertEqual((unique.name, unique.fields), ('uq_population_code', ('code',)))
        with connection.cursor() as cursor:
            cursor.execute('SELECT column_name, data_type, character_maximum_length, is_nullable, column_default '
                           "FROM information_schema.columns WHERE table_schema = current_schema() AND table_name = 'population'")
            self.assertEqual({row[0]: row[1:] for row in cursor.fetchall()}, columns)
            constraints = connection.introspection.get_constraints(cursor, 'population')
            cursor.execute("SELECT indexname FROM pg_indexes WHERE schemaname = current_schema() AND tablename = 'population'")
            self.assertEqual({row[0] for row in cursor.fetchall()}, {'population_pkey', 'uq_population_code'})
        self.assertEqual([info['columns'] for info in constraints.values() if info['primary_key']], [['population_id']])
        self.assertEqual({name: info['columns'] for name, info in constraints.items() if info['unique'] and not info['primary_key']},
                         {'uq_population_code': ['code']})
        self.assertEqual([info['foreign_key'] for info in constraints.values() if info['foreign_key']], [('population', 'population_id')])
        self.assertEqual(constraints['fk_population_parent']['columns'], ['parent_population_id'])
        self.assertFalse(any(info['check'] or info['index'] for info in constraints.values()))
        self.assertEqual(self.fk_actions(), {'fk_population_parent': ('n', 'c', False, False)})

    def test_raw_sql_defaults_are_false_nullable_and_transaction_time(self):
        with connection.cursor() as cursor:
            cursor.execute('INSERT INTO population (population_id, code, name) VALUES (%s, %s, %s) '
                           'RETURNING parent_population_id, description, geographic_region, metadata, '
                           'is_internal, is_masked, created_at, transaction_timestamp()',
                           [uuid.uuid4(), 'synthetic-sql', 'Synthetic cohort'])
            *optional, internal, masked, created, database_now = cursor.fetchone()
        self.assertEqual(optional, [None] * 4)
        self.assertIs(internal, False)
        self.assertIs(masked, False)
        self.assertTrue(timezone.is_aware(created))
        self.assertEqual(created, database_now)

    def test_explicit_values_round_trip_without_inference_or_other_table_writes(self):
        other_models = (domain.Analysis, domain.DataRelease, domain.Variant,
                        domain.VariantPlacement, domain.ExternalIdentifier)
        before = {model: model.objects.count() for model in other_models}
        self.assertEqual(domain.Population.objects.count(), 0)  # No catalog seeds.
        parent = self.population()
        parent.save()
        values = dict(parent_population=parent, code='unlisted.code-42', name='Synthetic cohort',
                      description='Synthetic description', geographic_region='Unlisted synthetic region',
                      is_internal=True, is_masked=True, metadata={'tags': ['synthetic'], 'details': {'count': 2}},
                      created_at=timezone.now() - timedelta(days=1))
        population = self.population(**values)
        population.full_clean()
        population.save()
        population.refresh_from_db()
        self.assertEqual({field: getattr(population, field) for field in values}, values)
        self.assertEqual({model: model.objects.count() for model in other_models}, before)

    def test_required_columns_primary_key_and_unique_code_are_enforced(self):
        values = dict(population_id=uuid.uuid4(), code='synthetic', name='Synthetic cohort',
                      is_internal=False, is_masked=False, created_at=timezone.now())
        columns = ', '.join(connection.ops.quote_name(field) for field in values)
        placeholders = ', '.join(['%s'] * len(values))
        for field in values:
            with self.subTest(null_column=field):
                with self.assertRaises(IntegrityError) as error, transaction.atomic():
                    with connection.cursor() as cursor:
                        cursor.execute(f'INSERT INTO population ({columns}) VALUES ({placeholders})',
                                       [None if name == field else value for name, value in values.items()])
                self.assertEqual(error.exception.__cause__.diag.column_name, field)
        for field in ('code', 'name'):
            with self.subTest(blank_field=field):
                with self.assertRaises(ValidationError) as error:
                    self.population(**{field: ''}).full_clean()
                self.assertIn(field, error.exception.message_dict)
        first = self.population()
        first.save()
        with self.assertRaises(ValidationError):
            self.population(code=first.code).full_clean()
        for changes, constraint in (({'population_id': first.pk}, 'population_pkey'),
                                    ({'code': first.code}, 'uq_population_code')):
            with self.subTest(constraint=constraint):
                with self.assertRaises(IntegrityError) as error, transaction.atomic():
                    domain.Population.objects.bulk_create([self.population(**changes)])
                self.assertEqual(error.exception.__cause__.diag.constraint_name, constraint)

    def test_varchar_boundaries_and_overflows_in_orm_and_database(self):
        for field, length in (('code', 64), ('name', 128), ('geographic_region', 128)):
            with self.subTest(field=field):
                boundary = self.population(**{field: 'x' * length})
                boundary.full_clean()
                boundary.save()
                boundary.refresh_from_db()
                self.assertEqual(getattr(boundary, field), 'x' * length)
                too_long = self.population(**{field: 'x' * (length + 1)})
                with self.assertRaises(ValidationError) as error:
                    too_long.full_clean()
                self.assertIn(field, error.exception.message_dict)
                with self.assertRaises(DataError), transaction.atomic():
                    too_long.save()

    def test_raw_parent_pk_update_cascades_and_delete_sets_only_direct_children_null(self):
        parent = self.population()
        parent.parent_population_id = parent.pk  # SQL allows self-reference; no acyclicity check.
        parent.save()
        children = [self.population(parent_population=parent) for _ in range(2)]
        domain.Population.objects.bulk_create(children)
        grandchild = self.population(parent_population=children[0])
        grandchild.save()
        unrelated = self.population()
        unrelated.save()
        new_id = uuid.uuid4()
        with connection.cursor() as cursor:
            cursor.execute('UPDATE population SET population_id = %s WHERE population_id = %s', [new_id, parent.pk])
            self.assertEqual(list(domain.Population.objects.filter(code__in=[parent.code] + [child.code for child in children])
                                  .values_list('parent_population_id', flat=True)), [new_id] * 3)
            cursor.execute('DELETE FROM population WHERE population_id = %s', [new_id])
        self.assertEqual(list(domain.Population.objects.filter(pk__in=[child.pk for child in children])
                              .values_list('parent_population_id', flat=True)), [None] * 2)
        grandchild.refresh_from_db()
        self.assertEqual(grandchild.parent_population_id, children[0].pk)
        self.assertTrue(domain.Population.objects.filter(pk=unrelated.pk).exists())
        self.assertEqual(domain.Population.objects.count(), 4)

    def test_orm_parent_delete_preserves_children_with_null_parent(self):
        parent = self.population()
        parent.save()
        child = self.population(parent_population=parent)
        child.save()
        parent.delete()
        child.refresh_from_db()
        self.assertIsNone(child.parent_population_id)
        self.assertEqual(domain.Population.objects.count(), 1)

    def test_orphan_fk_rejects_insert_and_update_immediately_even_when_all_are_deferred(self):
        orphan = self.population(parent_population_id=uuid.uuid4())
        with self.assertRaises(ValidationError) as error:
            orphan.full_clean()
        self.assertIn('parent_population', error.exception.message_dict)
        population = self.population()
        population.save()
        for sql, args in (
            ('INSERT INTO population (population_id, parent_population_id, code, name) VALUES (%s, %s, %s, %s)',
             [orphan.pk, orphan.parent_population_id, orphan.code, orphan.name]),
            ('UPDATE population SET parent_population_id = %s WHERE population_id = %s', [orphan.parent_population_id, population.pk]),
        ):
            with self.subTest(sql=sql):
                with self.assertRaises(IntegrityError) as error, transaction.atomic():
                    with connection.cursor() as cursor:
                        cursor.execute('SET CONSTRAINTS ALL DEFERRED')
                        cursor.execute(sql, args)
                        self.fail('Population FK must reject an orphan at the statement, not transaction end.')
                self.assertEqual(error.exception.__cause__.diag.constraint_name, 'fk_population_parent')

    def test_fk_reverse_restores_django_defaults_and_lookup_fails_closed(self):
        operation = normalized_migration_slice('Population').operations[1]
        state = MigrationLoader(connection, replace_migrations=False).project_state([NORMALIZED_LEAF])
        with connection.schema_editor() as editor, connection.cursor() as cursor:
            expected = self.fk_actions()
            operation.database_backwards('genoma', editor, state, state)
            self.assertEqual(self.fk_actions(), {'fk_population_parent': ('a', 'a', True, True)})
            for case, sql in (
                ('missing', 'ALTER TABLE population DROP CONSTRAINT fk_population_parent'),
                ('ambiguous', 'ALTER TABLE population ADD CONSTRAINT duplicate_fk FOREIGN KEY (parent_population_id) '
                 'REFERENCES population (population_id) DEFERRABLE INITIALLY DEFERRED'),
            ):
                with self.subTest(case=case), transaction.atomic():
                    cursor.execute(sql)
                    before = self.fk_actions()
                    with self.assertRaisesMessage(RuntimeError, 'Expected exactly one FK'):
                        operation.database_forwards('genoma', editor, state, state)
                    self.assertEqual(self.fk_actions(), before)
                    transaction.set_rollback(True)
            operation.database_forwards('genoma', editor, state, state)
            self.assertEqual(self.fk_actions(), expected)

    def test_fk_lookup_matches_exact_source_and_target_attnums(self):
        operation = normalized_migration_slice('Population').operations[1]
        state = MigrationLoader(connection, replace_migrations=False).project_state([NORMALIZED_LEAF])
        with transaction.atomic(), connection.schema_editor() as editor, connection.cursor() as cursor:
            expected = self.fk_actions()
            cursor.execute('ALTER TABLE population ADD CONSTRAINT decoy_unique UNIQUE (parent_population_id)')
            for name, source, target in (('decoy_source', 'population_id', 'population_id'),
                                         ('decoy_target', 'parent_population_id', 'parent_population_id')):
                cursor.execute(f'ALTER TABLE population ADD CONSTRAINT {name} FOREIGN KEY ({source}) '
                               f'REFERENCES population ({target}) DEFERRABLE INITIALLY DEFERRED')
            operation.database_backwards('genoma', editor, state, state)
            operation.database_forwards('genoma', editor, state, state)
            self.assertEqual(self.fk_actions(), expected | {name: ('a', 'a', True, True) for name in ('decoy_source', 'decoy_target')})
            transaction.set_rollback(True)

    def test_schema_only_migration_dependency_and_state_match_model(self):
        with self.assertNumQueries(0):
            reload(import_module('genoma.migrations.0007_population'))
            migration = normalized_migration_slice('Population')
        self.assertEqual(migration.dependencies, normalized_dependencies('Population'))
        self.assertEqual([type(operation).__name__ for operation in migration.operations], ['CreateModel', 'RunPython'])
        self.assertEqual(migration.operations[0].name, 'Population')
        self.assertTrue(migration.operations[1].reversible)
        historical = MigrationLoader(connection, replace_migrations=False).project_state([NORMALIZED_LEAF]).apps.get_model('genoma', 'Population')
        self.assertEqual(historical._meta.db_table, domain.Population._meta.db_table)
        self.assertEqual({field.name: field.deconstruct()[1:] for field in historical._meta.local_fields},
                         {field.name: field.deconstruct()[1:] for field in domain.Population._meta.local_fields})
        self.assertEqual(historical._meta.indexes, domain.Population._meta.indexes)
        self.assertEqual(historical._meta.constraints, domain.Population._meta.constraints)
        call_command('check')
        call_command('makemigrations', check=True, dry_run=True)


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
        legacy = (domain.Analysis, domain.DataRelease, domain.Variant, domain.VariantPlacement)
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
        operation = normalized_migration_slice('ExternalIdentifier').operations[1]
        state = MigrationLoader(connection, replace_migrations=False).project_state([NORMALIZED_LEAF])
        with connection.schema_editor() as editor, connection.cursor() as cursor:
            expected = self.fk_actions()
            operation.database_backwards('genoma', editor, state, state)
            restored = {name: ('a', 'a', True, True) for name in expected}
            self.assertEqual(self.fk_actions(), restored)
            operation.database_forwards('genoma', editor, state, state)
            self.assertEqual(self.fk_actions(), expected)
            operation.database_backwards('genoma', editor, state, state)
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
                            operation.database_forwards('genoma', editor, state, state)
                        self.assertEqual(self.fk_actions(), before)  # Neither FK changes if either lookup fails.
                        transaction.set_rollback(True)
            operation.database_forwards('genoma', editor, state, state)

    def test_fk_lookup_matches_source_and_target_attnums_not_other_self_references(self):
        operation = normalized_migration_slice('ExternalIdentifier').operations[1]
        state = MigrationLoader(connection, replace_migrations=False).project_state([NORMALIZED_LEAF])
        with transaction.atomic(), connection.schema_editor() as editor, connection.cursor() as cursor:
            expected = self.fk_actions()
            cursor.execute('ALTER TABLE external_identifier ADD CONSTRAINT decoy_unique UNIQUE (variant_id)')
            for name, source, target in (('decoy_source', 'variant_id', 'external_identifier_id'),
                                         ('decoy_target', 'replaced_by_identifier_id', 'variant_id')):
                cursor.execute(f'ALTER TABLE external_identifier ADD CONSTRAINT {name} FOREIGN KEY ({source}) '
                               f'REFERENCES external_identifier ({target}) DEFERRABLE INITIALLY DEFERRED')
            operation.database_backwards('genoma', editor, state, state)
            operation.database_forwards('genoma', editor, state, state)
            self.assertEqual(self.fk_actions(), expected | {name: ('a', 'a', True, True) for name in ('decoy_source', 'decoy_target')})
            transaction.set_rollback(True)

    def test_schema_only_migration_dependency_and_state_match_model(self):
        with self.assertNumQueries(0):
            reload(import_module('genoma.migrations.0006_external_identifier'))
            migration = normalized_migration_slice('ExternalIdentifier')
        self.assertEqual(migration.dependencies, normalized_dependencies('ExternalIdentifier'))
        self.assertEqual([type(operation).__name__ for operation in migration.operations], ['CreateModel', 'RunPython'])
        self.assertEqual(migration.operations[0].name, 'ExternalIdentifier')
        historical = MigrationLoader(connection, replace_migrations=False).project_state([NORMALIZED_LEAF]).apps.get_model('genoma', 'ExternalIdentifier')
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
        legacy = (domain.Analysis, domain.DataRelease, domain.Variant)
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
        operation = normalized_migration_slice('VariantPlacement').operations[1]
        state = MigrationLoader(connection, replace_migrations=False).project_state([NORMALIZED_LEAF])
        actions_sql = ('SELECT confdeltype, confupdtype, condeferrable, condeferred FROM pg_constraint '
                       "WHERE conrelid = 'variant_placement'::regclass AND conname = 'fk_variant_placement_variant'")
        with connection.schema_editor() as editor, connection.cursor() as cursor:
            operation.database_backwards('genoma', editor, state, state)
            cursor.execute(actions_sql)
            self.assertEqual(cursor.fetchall(), [('a', 'a', True, True)])
            operation.database_forwards('genoma', editor, state, state)
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
                        operation.database_forwards('genoma', editor, state, state)
                    transaction.set_rollback(True)  # Restore the isolated FK after each intentional lookup failure.

    def test_schema_only_migration_dependency_state_and_fixed_char_deconstruction(self):
        with self.assertNumQueries(0):
            reload(import_module('genoma.migrations.0005_variant_placement'))
            migration = normalized_migration_slice('VariantPlacement')
        self.assertEqual(migration.dependencies, normalized_dependencies('VariantPlacement'))
        self.assertEqual([type(operation).__name__ for operation in migration.operations], ['CreateModel', 'RunPython'])
        self.assertEqual(migration.operations[0].name, 'VariantPlacement')
        historical = MigrationLoader(connection, replace_migrations=False).project_state([NORMALIZED_LEAF]).apps.get_model(
            'genoma', 'VariantPlacement',
        )
        self.assertEqual(historical._meta.db_table, domain.VariantPlacement._meta.db_table)
        self.assertEqual({field.name: field.deconstruct()[1:] for field in historical._meta.local_fields},
                         {field.name: field.deconstruct()[1:] for field in domain.VariantPlacement._meta.local_fields})
        self.assertEqual(historical._meta.indexes, domain.VariantPlacement._meta.indexes)
        self.assertEqual(historical._meta.constraints, domain.VariantPlacement._meta.constraints)
        field = domain.VariantPlacement._meta.get_field('strand')
        self.assertIsInstance(field, domain.FixedCharField)
        _, path, args, kwargs = field.deconstruct()
        self.assertEqual(path, 'genoma.models.FixedCharField')
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
        legacy = (domain.Analysis, domain.DataRelease)
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
            reload(import_module('genoma.migrations.0004_variant'))
            migration = normalized_migration_slice('Variant')
        self.assertEqual(migration.dependencies, normalized_dependencies('Variant'))
        self.assertEqual([type(operation).__name__ for operation in migration.operations], ['CreateModel'])
        self.assertEqual(migration.operations[0].name, 'Variant')
        historical = MigrationLoader(connection, replace_migrations=False).project_state([NORMALIZED_LEAF]).apps.get_model('genoma', 'Variant')
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
            reload(import_module('genoma.migrations.0002_data_release'))
            migration = normalized_migration_slice('DataRelease')
        self.assertEqual(migration.dependencies, normalized_dependencies('DataRelease'))
        self.assertEqual([type(op).__name__ for op in migration.operations], ['CreateModel'])
        loader = MigrationLoader(connection, replace_migrations=False)
        followup = loader.disk_migrations[('genoma', '0003_analysis_release')]
        self.assertEqual(followup.dependencies, [NORMALIZED_TABLE_MIGRATIONS['DataRelease']])
        self.assertEqual([type(op).__name__ for op in followup.operations], ['AddField', 'AddIndex'])
        self.assertEqual((followup.operations[0].model_name, followup.operations[0].name), ('analysis', 'release'))
        self.assertEqual(followup.operations[1].index.name, 'idx_analysis_release_module')
        state = loader.project_state([NORMALIZED_LEAF])
        for name in ('DataRelease', 'Analysis'):
            historical, current = state.apps.get_model('genoma', name), getattr(domain, name)
            self.assertEqual(historical._meta.db_table, current._meta.db_table)
            self.assertEqual({f.name: f.deconstruct()[1:] for f in historical._meta.local_fields},
                             {f.name: f.deconstruct()[1:] for f in current._meta.local_fields})
            self.assertEqual(historical._meta.indexes, current._meta.indexes)
            self.assertEqual(historical._meta.constraints, current._meta.constraints)
        field = domain.DataRelease._meta.get_field('manifest_checksum')
        _, path, args, kwargs = field.deconstruct()
        self.assertEqual(path, 'genoma.models.FixedCharField')
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
        self.assertFalse(domain.Genotype.objects.exists())

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
            reload(import_module('genoma.migrations.0001_initial'))
            migration = normalized_migration_slice('Analysis')
        self.assertEqual(migration.dependencies, NORMALIZED_DEPENDENCIES)
        self.assertEqual([type(op).__name__ for op in migration.operations], ['CreateModel'])
        historical = MigrationLoader(connection, replace_migrations=False).project_state([NORMALIZED_LEAF]).apps.get_model('genoma', 'Analysis')
        self.assertEqual({f.name: f.deconstruct()[1:] for f in historical._meta.local_fields},
                         {f.name: f.deconstruct()[1:] for f in domain.Analysis._meta.local_fields})
        self.assertEqual(historical._meta.indexes, domain.Analysis._meta.indexes)
        self.assertTrue(connection.settings_dict['NAME'].startswith('gdb_test_'))
        call_command('check')
        call_command('makemigrations', check=True, dry_run=True)


class SyntheticVariantCatalogLoadTests(TestCase):
    fixture_path = Path(__file__).resolve().parent / 'fixtures' / 'synthetic_variant_catalog_v1.json'
    catalog_models = (domain.DataRelease, domain.Variant, domain.VariantPlacement, domain.ReleaseVariant)
    expected_counts = (1, 8, 8, 8)

    def setUp(self):
        self.assertEqual(connection.vendor, 'postgresql')
        self.assertTrue(connection.settings_dict['NAME'].startswith('gdb_test_'))
        self.assertTrue(connection.in_atomic_block)
        with connection.cursor() as cursor:
            cursor.execute('SELECT current_database()')
            self.assertEqual(cursor.fetchone()[0], connection.settings_dict['NAME'])
        applied_migrations = MigrationRecorder(connection).applied_migrations()
        self.assertIn(NORMALIZED_INITIAL, applied_migrations)
        self.assertIn(NORMALIZED_LEAF, applied_migrations)
        self.assertEqual(MigrationExecutor(connection).migration_plan([NORMALIZED_LEAF]), [])

    def load_catalog(self):
        output = StringIO()
        call_command('loaddata', str(self.fixture_path), database='default', verbosity=1, stdout=output)
        self.assertIn('Installed 25 object(s) from 1 fixture(s)', output.getvalue())
        connection.check_constraints()

    def catalog_rows(self):
        return [list(model.objects.order_by('pk').values()) for model in self.catalog_models]

    def test_real_loaddata_preserves_uuid_links_and_reloading_does_not_duplicate(self):
        self.assertEqual(tuple(model.objects.count() for model in self.catalog_models), (0, 0, 0, 0))
        self.load_catalog()
        self.assertEqual(tuple(model.objects.count() for model in self.catalog_models), self.expected_counts)
        release = domain.DataRelease.objects.get()
        self.assertEqual((release.reference_assembly, release.status), ('GENOMIA-DEMO-v1', 'synthetic'))
        self.assertIsNone(release.manifest_checksum)
        self.assertIsNone(release.frozen_at)
        self.assertIsInstance(release.pk, uuid.UUID)
        rows = json.loads(self.fixture_path.read_text(encoding='utf-8'))
        memberships = [row for row in rows if row['model'] == 'genoma.releasevariant']
        for serialized in memberships:
            with self.subTest(pk=serialized['pk']):
                fields = serialized['fields']
                self.assertEqual(serialized['pk'], [fields['release'], fields['variant']])
                key = tuple(uuid.UUID(value) for value in serialized['pk'])
                membership = domain.ReleaseVariant.objects.select_related('variant', 'placement').get(pk=key)
                self.assertEqual(membership.pk, (release.pk, membership.variant.pk))
                self.assertEqual(str(membership.placement_id), fields['placement'])
                self.assertEqual(membership.placement.variant_id, membership.variant_id)
                self.assertEqual(membership.placement.reference_assembly, release.reference_assembly)
                self.assertIsNone(membership.included_by_analysis_id)
                self.assertIsNone(membership.variant.vrs_id)
                self.assertIs(membership.placement.normalized, False)
                for item in (membership.variant, membership.placement):
                    self.assertIsInstance(item.pk, uuid.UUID)
                    self.assertIs(item.metadata['synthetic'], True)
                    self.assertEqual(item.metadata['purpose'], 'development_catalog_example')
        before = self.catalog_rows()
        self.load_catalog()
        self.assertEqual(tuple(model.objects.count() for model in self.catalog_models), self.expected_counts)
        self.assertEqual(self.catalog_rows(), before)

    def test_reload_overwrites_fields_of_existing_stable_ids(self):
        self.load_catalog()
        expected = self.catalog_rows()
        domain.DataRelease.objects.update(description='Local development edit')
        domain.Variant.objects.update(canonical_name='Local development edit', metadata={'local': True})
        domain.VariantPlacement.objects.update(normalized=True, alternate_allele='T')
        domain.ReleaseVariant.objects.update(inclusion_status='excluded')
        self.assertNotEqual(self.catalog_rows(), expected)
        self.load_catalog()
        self.assertEqual(self.catalog_rows(), expected)
        self.assertEqual(tuple(model.objects.count() for model in self.catalog_models), self.expected_counts)

    def test_both_loads_preserve_nonempty_patient_workflow_results_auth_and_other_catalog_rows(self):
        self.user = User.objects.create_user(username='catalog-preserved-owner')
        Profile.objects.create(user=self.user, phone='CATALOG-PRESERVED')
        group = Group.objects.create(name='catalog-preserved-group')
        self.user.groups.add(group)
        # Reuse the existing isolated-test graph builder, not the custom importer.
        NormalizedInitialMigrationTests.seed_complete_normalized_graph(self)
        request = ServiceRequest.objects.get(participant__user=self.user)
        ServiceStatusLog.objects.create(request=request, status=request.status, actor=self.user.app_user)
        preserved_models = [model for model in apps.get_models(include_auto_created=True)
                            if model not in self.catalog_models]

        def preserved_rows():
            return {model._meta.label: list(model.objects.order_by('pk').values())
                    for model in preserved_models}

        before = preserved_rows()
        for model in (User, AppUser, Role, Group, User.groups.through, Profile, Participant,
                      Purchase, ServiceRequest, ServiceStatusLog, Sample,
                      domain.Analysis, domain.AnalysisResult, domain.Genotype):
            self.assertTrue(before[model._meta.label], model._meta.label)
        prior_catalog = self.catalog_rows()
        self.assertEqual(tuple(map(len, prior_catalog)), (1, 1, 1, 1))
        for attempt in (1, 2):
            with self.subTest(load=attempt):
                self.load_catalog()
                self.assertEqual(preserved_rows(), before)
                after = self.catalog_rows()
                self.assertEqual(tuple(map(len, after)), (2, 9, 9, 9))
                for prior_rows, loaded_rows in zip(prior_catalog, after):
                    for row in prior_rows:
                        self.assertIn(row, loaded_rows)
                if attempt == 1:
                    first_loaded = after
                else:
                    self.assertEqual(after, first_loaded)


class SyntheticVariantCatalogContractTests(SimpleTestCase):
    def setUp(self):
        self.rows = json.loads(SyntheticVariantCatalogLoadTests.fixture_path.read_text(encoding='utf-8'))
        self.expected_labels = (
            'genoma.datarelease', 'genoma.variant',
            'genoma.variantplacement', 'genoma.releasevariant',
        )
        self.by_model = {label: [row for row in self.rows if row['model'] == label]
                         for label in self.expected_labels}

    def test_exact_catalog_scope_unique_uuid_keys_and_consistent_membership_references(self):
        self.assertIs(type(self.rows), list)
        self.assertEqual({row['model'] for row in self.rows}, set(self.expected_labels))
        self.assertEqual(tuple(len(self.by_model[label]) for label in self.expected_labels), (1, 8, 8, 8))
        self.assertEqual([row['model'] for row in self.rows], [
            label for label, count in zip(self.expected_labels, (1, 8, 8, 8)) for _ in range(count)
        ])
        single_keys = [row['pk'] for row in self.rows if row['model'] != 'genoma.releasevariant']
        self.assertEqual(len(set(single_keys)), 17)
        for key in single_keys:
            self.assertEqual(str(uuid.UUID(key)), key)
        release = self.by_model['genoma.datarelease'][0]
        variants = {row['pk']: row['fields'] for row in self.by_model['genoma.variant']}
        placements = {row['pk']: row['fields'] for row in self.by_model['genoma.variantplacement']}
        memberships = self.by_model['genoma.releasevariant']
        self.assertEqual(len({tuple(row['pk']) for row in memberships}), 8)
        self.assertEqual({row['fields']['variant'] for row in memberships}, set(variants))
        self.assertEqual({row['fields']['placement'] for row in memberships}, set(placements))
        for row in memberships:
            fields = row['fields']
            self.assertIs(type(row['pk']), list)
            self.assertEqual(row['pk'], [release['pk'], fields['variant']])
            self.assertEqual(fields['release'], release['pk'])
            self.assertEqual(placements[fields['placement']]['variant'], fields['variant'])
            self.assertEqual(fields['inclusion_status'], 'included')
            self.assertIsNone(fields['included_by_analysis'])

    def test_fictional_unvalidated_markers_and_coherent_substitution_and_anchored_indel_examples(self):
        release = self.by_model['genoma.datarelease'][0]['fields']
        self.assertEqual(release['name'], 'SYNTHETIC DEMO variant catalog')
        self.assertEqual(release['status'], 'synthetic')
        self.assertEqual(release['reference_assembly'], 'GENOMIA-DEMO-v1')
        self.assertIsNone(release['manifest_checksum'])
        self.assertIsNone(release['frozen_at'])
        variants = {row['pk']: row['fields'] for row in self.by_model['genoma.variant']}
        self.assertEqual({fields['variant_type'] for fields in variants.values()},
                         {'SNV', 'MNV', 'deletion', 'insertion'})
        names = [fields['canonical_name'] for fields in variants.values()]
        self.assertEqual(len(set(names)), 8)
        for fields in variants.values():
            self.assertTrue(fields['canonical_name'].startswith('SYNTHETIC-DEMO-'))
            self.assertIsNone(fields['vrs_id'])
            self.assertEqual(fields['status'], 'synthetic')
        for row in self.by_model['genoma.variant'] + self.by_model['genoma.variantplacement']:
            self.assertEqual(row['fields']['metadata'], {
                'synthetic': True, 'purpose': 'development_catalog_example', 'biologically_validated': False,
            })
        for row in self.by_model['genoma.variantplacement']:
            with self.subTest(placement=row['pk']):
                fields = row['fields']
                kind = variants[fields['variant']]['variant_type']
                ref, alt = fields['reference_allele'], fields['alternate_allele']
                self.assertRegex(ref, r'^[ACGT]+$')
                self.assertRegex(alt, r'^[ACGT]+$')
                self.assertNotEqual(ref, alt)
                self.assertEqual(fields['reference_assembly'], release['reference_assembly'])
                self.assertIn(fields['contig'], {'DEMO-CONTIG-A', 'DEMO-CONTIG-B',
                                                'DEMO-CONTIG-C', 'DEMO-CONTIG-D'})
                self.assertEqual(fields['coordinate_system'], '1-based-inclusive')
                self.assertIs(type(fields['start_pos']), int)
                self.assertIs(type(fields['end_pos']), int)
                self.assertGreaterEqual(fields['start_pos'], 1)
                self.assertGreaterEqual(fields['end_pos'], fields['start_pos'])
                self.assertEqual(fields['end_pos'] - fields['start_pos'] + 1, len(ref))
                self.assertIs(fields['normalized'], False)
                self.assertIs(fields['is_canonical'], False)
                self.assertIsNone(fields['sv_length'])
                self.assertIsNone(fields['breakend'])
                if kind == 'SNV':
                    self.assertEqual((len(ref), len(alt)), (1, 1))
                elif kind == 'MNV':
                    self.assertEqual(len(ref), len(alt))
                    self.assertGreater(len(ref), 1)
                elif kind == 'deletion':
                    self.assertEqual(alt, ref[0])
                    self.assertGreater(len(ref), len(alt))
                else:
                    self.assertEqual(ref, alt[0])
                    self.assertGreater(len(alt), len(ref))


# These deliberately artificial VCF records test preparation, not public biological facts.
import gzip as preparation_gzip
import io as preparation_io
import subprocess as preparation_subprocess
import sys as preparation_sys
import tempfile as preparation_tempfile
from contextlib import contextmanager as preparation_contextmanager
from urllib.error import HTTPError as PreparationHTTPError


class PublicVariantPreparationInputs:
    @staticmethod
    def vcf(rows=None, *, date='2026-09-28', reference='GRCh38'):
        if rows is None:
            rows = [PublicVariantPreparationInputs.row()]
        header = (
            '##fileformat=VCFv4.1\n##source=ClinVar\n'
            f'##fileDate={date}\n##reference={reference}\n'
            '##INFO=<ID=ALLELEID,Number=1,Type=Integer,Description="Allele ID">\n'
            '#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n'
        )
        return (header + '\n'.join(rows) + '\n').encode('utf-8')

    @staticmethod
    def row(allele=101, record=201, pos=11, ref='AC', alt='A', info=None, contig='1'):
        if info is None:
            info = ('GENEINFO=TESTGENE:1;CLNSIG=Uncertain_significance;'
                    'CLNREVSTAT=criteria_provided%2C_single_submitter;'
                    'CLNDN=Test%3Bcondition%3Dvalue;RS=7;CLNCIT=TEST-CITATION')
        return f'{contig}\t{pos}\t{record}\t{ref}\t{alt}\t.\t.\tALLELEID={allele};{info}'

    @preparation_contextmanager
    def source_tree(self, content=None, compressed=None, sidecar=None):
        with preparation_tempfile.TemporaryDirectory(prefix='public-preparation-tests-') as directory:
            root = Path(directory)
            source = root / 'input'
            source.mkdir()
            filename = 'clinvar_20260928.vcf.gz'
            data = compressed if compressed is not None else preparation_gzip.compress(
                content if content is not None else self.vcf(), mtime=0,
            )
            (source / filename).write_bytes(data)
            checksum = sidecar if sidecar is not None else (
                hashlib.md5(data).hexdigest() + '  ' + filename + '\n'
            ).encode('ascii')
            (source / (filename + '.md5')).write_bytes(checksum)
            yield root, source, data

    def prepare_local(self, root, source, *, limit=1, **kwargs):
        return self.preparation.prepare(
            cache_dir=root / 'cache', output_dir=root / 'output',
            local_source_dir=source, limit=limit, **kwargs,
        )

    @staticmethod
    def outputs(root):
        return {path.name: path.read_bytes() for path in (root / 'output').iterdir()}


class PublicVariantPreparationContractTests(PublicVariantPreparationInputs, SimpleTestCase):
    def setUp(self):
        self.preparation = import_module('genoma.public_variant_preparation')

    def test_deterministic_six_model_fixture_manifest_and_lossless_assertions(self):
        second = self.row(102, 202, 21, 'A', 'AG', info='RS=7;GENEINFO=OTHER:2')
        with self.source_tree(self.vcf([self.row(), second])) as (root, source, compressed):
            manifest = self.prepare_local(root, source, limit=2)
            first = self.outputs(root)
            objects = json.loads(first['catalog.json'])
            self.assertEqual(manifest, json.loads(first['manifest.json']))
            self.assertEqual(manifest['fixture']['sha256'], hashlib.sha256(first['catalog.json']).hexdigest())
            self.assertEqual(manifest['source']['sha256'], hashlib.sha256(compressed).hexdigest())
            self.assertEqual(manifest['source']['md5']['value'], hashlib.md5(compressed).hexdigest())
            self.assertFalse(manifest['source']['md5']['publisher_authenticated'])
            self.assertEqual(manifest['selection']['selected'], 2)
            self.assertEqual(manifest['selection']['eligible'], 2)
            self.assertIn('not representative', manifest['selection']['method'])
            self.assertIn('maintenance_use', manifest['data_policy']['url'])
            self.assertNotIn('license', manifest['data_policy'])
            self.assertEqual(len(objects), 11)
            expected = {model._meta.label_lower: model for model in (
                domain.DataRelease, domain.Variant, domain.VariantPlacement,
                domain.ReleaseVariant, domain.ExternalIdentifier, domain.VariantAnnotation,
            )}
            self.assertEqual({obj['model'] for obj in objects}, set(expected))
            for obj in objects:
                model = expected[obj['model']]
                field_names = {field.name for field in model._meta.local_fields
                               if not field.primary_key}
                self.assertEqual(set(obj['fields']), field_names)
                self.assertEqual(obj['fields']['created_at'], '2026-09-28T00:00:00Z')
                for field in model._meta.local_fields:
                    value = obj['fields'].get(field.name)
                    if field.max_length and isinstance(value, str):
                        self.assertLessEqual(len(value), field.max_length)
            placement = next(obj for obj in objects if obj['model'] == 'genoma.variantplacement')['fields']
            self.assertEqual((placement['start_pos'], placement['end_pos']), (11, 12))
            self.assertEqual((placement['reference_allele'], placement['alternate_allele']), ('AC', 'A'))
            self.assertFalse(placement['normalized'])
            annotation = next(obj for obj in objects if obj['model'] == 'genoma.variantannotation')['fields']
            self.assertEqual(annotation['gene_symbol'], 'TESTGENE')
            self.assertEqual(annotation['payload']['info']['CLNDN'], 'Test;condition=value')
            self.assertEqual(annotation['payload']['info']['RS'], '7')
            self.assertIn('CLNDN=Test%3Bcondition%3Dvalue', annotation['payload']['raw_info'])
            accessions = [obj['fields'] for obj in objects if obj['model'] == 'genoma.externalidentifier']
            self.assertEqual({value['accession'] for value in accessions}, {'101', '102'})
            self.assertEqual({value['namespace'] for value in accessions}, {'clinvar.allele'})
            self.assertEqual({value['version'] for value in accessions}, {'unversioned'})
            self.preparation.validate_catalog(objects)
            self.preparation.prepare(cache_dir=root / 'cache2', output_dir=root / 'output2',
                                     local_source_dir=source, limit=2)
            self.assertEqual(first, {p.name: p.read_bytes() for p in (root / 'output2').iterdir()})

    def test_raw_long_or_multiple_assertions_are_not_truncated_into_typed_fields(self):
        info = 'GENEINFO=A:1|B:2;CLNSIG=' + 'x' * 129 + ';CLNREVSTAT=' + 'y' * 65
        with self.source_tree(self.vcf([self.row(info=info)])) as (root, source, _):
            self.prepare_local(root, source)
            objects = json.loads((root / 'output/catalog.json').read_text())
            annotation = next(o['fields'] for o in objects if o['model'] == 'genoma.variantannotation')
            for field in ('gene_symbol', 'clinical_significance', 'evidence_level'):
                self.assertIsNone(annotation[field])
                self.assertIn(field, annotation['payload']['typed_fields_omitted'])
            self.assertEqual(annotation['payload']['info']['CLNSIG'], 'x' * 129)

    def test_skips_are_counted_cap_is_exact_and_trailer_is_still_validated(self):
        rows = [self.row(), self.row(102, 202, 21, alt='<DEL>'),
                self.row(103, 203, 31, alt='A,G'), self.row(104, 204, 41, alt='N'),
                self.row(105, 205, 51, contig='GL0001'), self.row(106, 206, 61)]
        with self.source_tree(self.vcf(rows)) as (root, source, _):
            manifest = self.prepare_local(root, source)
            self.assertEqual(manifest['selection']['selected'], 1)
            self.assertEqual(manifest['selection']['eligible'], 2)
            self.assertEqual(manifest['selection']['records_scanned'], 6)
            self.assertEqual(manifest['selection']['skipped'], {
                'symbolic_or_breakend': 1, 'multiallelic': 1,
                'non_acgt_allele': 1, 'unsupported_contig': 1,
            })
        with self.source_tree(self.vcf(rows)) as (root, source, _):
            with self.assertRaisesRegex(self.preparation.PreparationError, 'requested'):
                self.prepare_local(root, source, limit=3)
            self.assertFalse((root / 'cache').exists())
            self.assertFalse((root / 'output').exists())

    def test_invalid_header_identity_coordinates_and_info_fail_closed(self):
        good = self.vcf()
        cases = [good.replace(b'GRCh38', b'GRCh37'), good.replace(b'2026-09-28', b'2026-09-27'),
                 good.replace(b'##reference=GRCh38\n', b''),
                 good.replace(b'#CHROM\tPOS', b'#BAD\tPOS'),
                 good.replace(b'Number=1', b'Number=.'),
                 good.replace(b'\t11\t', b'\t0\t'),
                 good.replace(b'ALLELEID=101', b'ALLELEID=101,102'),
                 good.replace(b'ALLELEID=101', b'ALLELEID=101;ALLELEID=101'),
                 good.replace(b'ALLELEID=101', b'ALLELEID=00101'),
                 good.replace(b'Test%3B', b'Test%ZZ'),
                 good.replace(b'\t11\t', b'\t9223372036854775807\t'),
                 good + b'broken\trow\n']
        for content in cases:
            with self.subTest(content=content[-100:]), self.source_tree(content) as (root, source, _):
                with self.assertRaises(self.preparation.PreparationError):
                    self.prepare_local(root, source)
                self.assertFalse((root / 'output').exists())
                self.assertFalse((root / 'cache').exists())

    def test_duplicate_allele_record_and_coordinate_keys_even_after_selected_cap_reject(self):
        cases = [self.row(), self.row(record=202, pos=21),
                 self.row(allele=102, pos=21), self.row(allele=102, record=202)]
        for duplicate in cases:
            with self.subTest(duplicate=duplicate), self.source_tree(
                self.vcf([self.row(), duplicate]),
            ) as (root, source, _):
                with self.assertRaisesRegex(self.preparation.PreparationError, 'duplicate'):
                    self.prepare_local(root, source)
                self.assertFalse((root / 'output').exists())

    def test_catalog_validator_rejects_composite_order_ownership_and_external_collisions(self):
        with self.source_tree(self.vcf([self.row(), self.row(102, 202, 21)])) as (root, source, _):
            self.prepare_local(root, source, limit=2)
            objects = json.loads((root / 'output/catalog.json').read_text())
        membership = next(i for i, o in enumerate(objects) if o['model'] == 'genoma.releasevariant')
        placement = next(i for i, o in enumerate(objects) if o['model'] == 'genoma.variantplacement')
        externals = [i for i, o in enumerate(objects) if o['model'] == 'genoma.externalidentifier']
        for mutate in ('order', 'owner', 'assembly', 'external', 'duplicate', 'span'):
            changed = deepcopy(objects)
            if mutate == 'order':
                changed[membership]['pk'].reverse()
            elif mutate == 'owner':
                changed[placement]['fields']['variant'] = str(uuid.uuid4())
            elif mutate == 'assembly':
                changed[placement]['fields']['reference_assembly'] = 'GRCh37'
            elif mutate == 'external':
                changed[externals[1]]['fields']['accession'] = changed[externals[0]]['fields']['accession']
            elif mutate == 'span':
                changed[placement]['fields']['end_pos'] += 1
            else:
                changed.append(deepcopy(changed[membership]))
            with self.subTest(mutate=mutate), self.assertRaises(self.preparation.PreparationError):
                self.preparation.validate_catalog(changed)

    def test_existing_directories_and_repository_paths_never_clobber(self):
        for target in ('cache', 'output'):
            with self.source_tree() as (root, source, _):
                existing = root / target
                existing.mkdir()
                sentinel = existing / 'keep.txt'
                sentinel.write_text('existing bytes')
                with self.assertRaises(self.preparation.PreparationError):
                    self.prepare_local(root, source)
                self.assertEqual(sentinel.read_text(), 'existing bytes')
                self.assertEqual(set(p.name for p in root.iterdir()), {'input', target})
        with self.source_tree() as (root, source, _):
            with self.assertRaisesRegex(self.preparation.PreparationError, 'outside'):
                self.preparation.prepare(cache_dir=root / 'cache', output_dir=Path(__file__).parent / 'forbidden',
                                         local_source_dir=source, limit=1)
            self.assertFalse((root / 'cache').exists())

    def test_failed_output_write_cleans_only_owned_files(self):
        original = Path.open

        def fail_manifest(path, *args, **kwargs):
            if path.name == 'manifest.json':
                raise OSError('test write failure')
            return original(path, *args, **kwargs)

        with self.source_tree() as (root, source, _), patch.object(Path, 'open', fail_manifest):
            with self.assertRaises(self.preparation.PreparationError):
                self.prepare_local(root, source)
            self.assertEqual(set(p.name for p in root.iterdir()), {'input'})
            self.assertTrue((source / 'clinvar_20260928.vcf.gz').exists())

    def test_checksum_filename_mismatch_corruption_and_gzip_truncation_leave_no_success(self):
        bad_sidecars = [b'0' * 32 + b'  clinvar_20260928.vcf.gz\n',
                        b'0' * 32 + b'  other.gz\n', b'not a checksum',
                        b'0' * 32 + b'  ../clinvar_20260928.vcf.gz\n']
        for sidecar in bad_sidecars:
            with self.subTest(sidecar=sidecar), self.source_tree(sidecar=sidecar) as (root, source, _):
                with self.assertRaises(self.preparation.PreparationError):
                    self.prepare_local(root, source)
                self.assertFalse((root / 'cache').exists())
        for data in (b'not gzip', preparation_gzip.compress(self.vcf(), mtime=0)[:-4]):
            with self.subTest(data=data[:10]), self.source_tree(compressed=data) as (root, source, _):
                with self.assertRaises(self.preparation.PreparationError):
                    self.prepare_local(root, source)
                self.assertFalse((root / 'output').exists())

    def test_explicit_bounds_invalid_limit_and_local_files_are_checked(self):
        for changes in ({'max_compressed': 10}, {'max_uncompressed': 10}, {'max_line': 10},
                        {'max_sidecar': 10}, {'max_records': 1}):
            with self.subTest(changes=changes), self.source_tree(
                self.vcf([self.row(), self.row(102, 202, 21)]),
            ) as (root, source, _):
                with self.assertRaises(self.preparation.PreparationError):
                    self.prepare_local(root, source, bounds=self.preparation.Bounds(**changes))
                self.assertFalse((root / 'cache').exists())
        for limit in (0, -1, True, 1.5):
            with self.source_tree() as (root, source, _):
                with self.assertRaises(self.preparation.PreparationError):
                    self.prepare_local(root, source, limit=limit)
        with self.source_tree() as (root, source, _):
            (source / 'clinvar_20260928.vcf.gz.md5').rename(source / 'missing.md5')
            with self.assertRaises(self.preparation.PreparationError):
                self.prepare_local(root, source)
            self.assertFalse((root / 'cache').exists())

    def test_standalone_module_cli_with_django_and_database_imports_forbidden(self):
        bootstrap = (
            "import sys,runpy,socket; "
            "socket.socket.connect=lambda *a: (_ for _ in ()).throw(RuntimeError('forbidden connection')); "
            "socket.create_connection=socket.socket.connect; "
            "sys.meta_path.insert(0,type('Deny',(),{'find_spec':lambda self,name,*a: "
            "(_ for _ in ()).throw(RuntimeError('forbidden import '+name)) "
            "if name.split('.')[0] in {'django','psycopg','psycopg2','sequoh'} else None})()); "
            "sys.argv=['genoma.public_variant_preparation']+sys.argv[1:]; "
            "runpy.run_module('genoma.public_variant_preparation',run_name='__main__')"
        )
        with self.source_tree() as (root, source, _):
            args = [preparation_sys.executable, '-B', '-c', bootstrap,
                    '--local-source-dir', str(source), '--cache-dir', str(root / 'cache'),
                    '--output-dir', str(root / 'output'), '--limit', '1']
            result = preparation_subprocess.run(args, cwd=Path(__file__).resolve().parents[1],
                                                capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)['selection']['selected'], 1)
            again = preparation_subprocess.run(args, cwd=Path(__file__).resolve().parents[1],
                                               capture_output=True, text=True, timeout=30)
            self.assertEqual(again.returncode, 2)
            self.assertIn('exists', again.stderr)
            module_args = [preparation_sys.executable, '-B', '-m', 'genoma.public_variant_preparation',
                           '--local-source-dir', str(source), '--cache-dir', str(root / 'cli-cache'),
                           '--output-dir', str(root / 'cli-output'), '--limit', '1']
            direct = preparation_subprocess.run(module_args, cwd=Path(__file__).resolve().parents[1],
                                                capture_output=True, text=True, timeout=30)
            self.assertEqual(direct.returncode, 0, direct.stderr)
            self.assertEqual((root / 'cli-output/catalog.json').read_bytes(),
                             (root / 'output/catalog.json').read_bytes())

    def test_default_ten_thousand_cap_on_artificial_inputs_and_all_supported_types(self):
        representations = [('A', 'G'), ('AC', 'GT'), ('A', 'AG'), ('AC', 'A'), ('AC', 'G')]
        rows = [self.row(100000 + i, 200000 + i, 1 + i * 2,
                         *representations[i % 5], info='RS=7') for i in range(10000)]
        with self.source_tree(self.vcf(rows)) as (root, source, _):
            manifest = self.preparation.prepare(cache_dir=root / 'cache', output_dir=root / 'output',
                                                local_source_dir=source)
            self.assertEqual(manifest['selection']['requested'], 10000)
            self.assertEqual(manifest['selection']['selected'], 10000)
            self.assertEqual(manifest['fixture']['objects'], 50001)
            objects = json.loads((root / 'output/catalog.json').read_text())
            self.assertEqual({o['fields']['variant_type'] for o in objects if o['model'] == 'genoma.variant'},
                             {'SNV', 'MNV', 'insertion', 'deletion', 'delins'})
            self.assertFalse(manifest['source']['md5']['publisher_authenticated'])

    def test_observed_publisher_sidecar_uses_basename_not_a_local_producer_path(self):
        # Parent-observed metadata only; this test does NOT verify the actual full source.
        checksum = '707723f0a08d1d711eb1c1de660a9098'
        producer = ('/netmnt/vast01/clinvar_gtr/ftp_test_MGG_REPORT/vcv_xml_product/'
                    'vcf_GRCh38/clinvar_20260928.vcf.gz')
        self.assertEqual(self.preparation.parse_sidecar(
            f'{checksum}  {producer}\n'.encode('ascii'), 'clinvar_20260928.vcf.gz',
        ), (checksum, producer))


class PublicVariantPreparationNetworkTests(PublicVariantPreparationInputs, SimpleTestCase):
    def setUp(self):
        self.preparation = import_module('genoma.public_variant_preparation')

    @staticmethod
    def response(data, url, headers=None):
        response = preparation_io.BytesIO(data)
        response.headers = headers or {'Content-Length': str(len(data))}
        response.geturl = lambda: url
        response.status = 200
        return response

    def network_prepare(self, root, responses, **kwargs):
        opener = self.preparation.official_opener('20260928')
        with patch.object(opener, 'open', side_effect=responses) as opened:
            result = self.preparation.prepare(cache_dir=root / 'cache', output_dir=root / 'output',
                                              limit=1, opener=opener, **kwargs)
        self.assertEqual(opened.call_count, 2)
        self.assertTrue(all(call.kwargs['timeout'] == 30 for call in opened.call_args_list))
        return result

    def test_mocked_official_download_verifies_full_source_and_publisher_sidecar(self):
        with self.source_tree(self.vcf([self.row(), self.row(102, 202, 21)])) as (root, source, data):
            url = self.preparation.source_url('20260928')
            result = self.network_prepare(root, [
                self.response((source / 'clinvar_20260928.vcf.gz.md5').read_bytes(), url + '.md5'),
                self.response(data, url),
            ])
            self.assertTrue(result['source']['md5']['publisher_authenticated'])
            self.assertEqual(result['source']['sha256'], hashlib.sha256(data).hexdigest())
            self.assertEqual(result['selection']['eligible'], 2)

    def test_redirect_policy_blocks_before_following_unapproved_destinations(self):
        url = self.preparation.source_url('20260928')
        policy = self.preparation.OfficialRedirects({url, url + '.md5'})
        from urllib.request import Request
        for destination in ('https://example.org/file', 'http://ftp.ncbi.nlm.nih.gov/file',
                            'https://ftp.ncbi.nlm.nih.gov/private',
                            url + '?token=x', 'https://user@ftp.ncbi.nlm.nih.gov/' + url.split('/', 3)[3]):
            with self.subTest(destination=destination), self.assertRaises(self.preparation.PreparationError):
                policy.redirect_request(Request(url), None, 302, 'redirect', {}, destination)
        self.assertEqual(policy.redirect_request(Request(url), None, 302, '', {}, url).full_url, url)

    def test_http_error_response_metadata_excess_and_truncation_fail_atomically(self):
        url = self.preparation.source_url('20260928')
        for fault in ('http', 'timeout', 'url', 'status', 'range', 'length', 'encoding',
                      'excess', 'streamexcess', 'truncated', 'checksum'):
            with self.subTest(fault=fault), self.source_tree() as (root, source, data):
                sidecar = (source / 'clinvar_20260928.vcf.gz.md5').read_bytes()
                response = self.response(data, url)
                if fault == 'http':
                    response = PreparationHTTPError(url, 503, 'unavailable', {}, None)
                elif fault == 'timeout':
                    response = TimeoutError('test socket timeout')
                elif fault == 'url':
                    response.geturl = lambda: 'https://example.org/file'
                elif fault == 'status':
                    response.status = 206
                elif fault == 'range':
                    response.headers['Content-Range'] = 'bytes 0-10/100'
                elif fault == 'length':
                    response.headers = {'Content-Length': 'garbage'}
                elif fault == 'encoding':
                    response.headers['Content-Encoding'] = 'gzip'
                elif fault == 'excess':
                    response.headers['Content-Length'] = str(2 ** 40)
                elif fault == 'streamexcess':
                    response.headers = {}
                elif fault == 'truncated':
                    response = self.response(data[:-1], url, {'Content-Length': str(len(data))})
                else:
                    response = self.response(data + b'x', url)
                opener = self.preparation.official_opener('20260928')
                with patch.object(opener, 'open', side_effect=[self.response(sidecar, url + '.md5'), response]):
                    with self.assertRaises(self.preparation.PreparationError):
                        self.preparation.prepare(
                            cache_dir=root / 'cache', output_dir=root / 'output', opener=opener, limit=1,
                            bounds=self.preparation.Bounds(max_compressed=len(data) - 1)
                            if fault == 'streamexcess' else self.preparation.Bounds(),
                        )
                self.assertFalse((root / 'cache').exists())
                self.assertFalse((root / 'output').exists())


class PublicVariantPreparationLoadTests(PublicVariantPreparationInputs, TestCase):
    def setUp(self):
        self.assertTrue(connection.settings_dict['NAME'].startswith('gdb_test_'))
        self.preparation = import_module('genoma.public_variant_preparation')

    def test_actual_serialization_loaddata_composites_reload_and_preservation(self):
        self.user = User.objects.create_user(username='public-preparation-preserved-owner')
        Profile.objects.create(user=self.user, phone='PUBLIC-PREP-KEPT')
        group = Group.objects.create(name='public-preparation-preserved-group')
        self.user.groups.add(group)
        NormalizedInitialMigrationTests.seed_complete_normalized_graph(self)
        request = ServiceRequest.objects.get(participant__user=self.user)
        ServiceStatusLog.objects.create(request=request, status=request.status, actor=self.user.app_user)
        tracked = list(apps.get_models(include_auto_created=True))

        def snapshot():
            return {m._meta.label: list(m.objects.order_by('pk').values()) for m in tracked}

        before = snapshot()
        with self.source_tree(self.vcf([self.row(), self.row(102, 202, 21)])) as (root, source, _):
            self.prepare_local(root, source, limit=2)
            fixture = root / 'output/catalog.json'
            objects = json.loads(fixture.read_text())
            from django.core import serializers
            deserialized = list(serializers.deserialize('json', fixture.read_text()))
            self.assertEqual(len(deserialized), 11)
            call_command('loaddata', str(fixture), verbosity=0, stdout=StringIO())
            first = snapshot()
            for label, prior_rows in before.items():
                for row in prior_rows:
                    self.assertIn(row, first[label], label)
            for model in (User, AppUser, Group, Profile, Participant, Purchase, Sample,
                          ServiceRequest, ServiceStatusLog, domain.Analysis, domain.Genotype):
                self.assertEqual(first[model._meta.label], before[model._meta.label])
                self.assertTrue(before[model._meta.label], model._meta.label)
            for serialized, decoded in zip(objects, deserialized):
                persisted = type(decoded.object).objects.get(pk=decoded.object.pk)
                for field in persisted._meta.local_fields:
                    # Composite deserialization retains string UUID components until DB coercion.
                    self.assertEqual(field.value_to_string(persisted), field.value_to_string(decoded.object))
                if serialized['model'] == 'genoma.releasevariant':
                    fields = serialized['fields']
                    self.assertEqual(serialized['pk'], [fields['release'], fields['variant']])
                    self.assertEqual(persisted.placement.variant_id, persisted.variant_id)
                    self.assertEqual(persisted.placement.reference_assembly, persisted.release.reference_assembly)
            call_command('loaddata', str(fixture), verbosity=0, stdout=StringIO())
            self.assertEqual(snapshot(), first)
            variant_pk = next(o['pk'] for o in objects if o['model'] == 'genoma.variant')
            domain.Variant.objects.filter(pk=variant_pk).update(canonical_name='Local catalog edit')
            call_command('loaddata', str(fixture), verbosity=0, stdout=StringIO())
            self.assertEqual(snapshot(), first, 'Reload replaces edits at deterministic IDs')


from contextlib import ExitStack as preparation_bounds_exit_stack


class PublicVariantPreparationHardCeilingTests(PublicVariantPreparationInputs, SimpleTestCase):
    def setUp(self):
        self.preparation = import_module('genoma.public_variant_preparation')
        self.maxima = vars(self.preparation.Bounds())

    def assert_bounds_rejected_before_io(self, bounds, message):
        with preparation_tempfile.TemporaryDirectory(prefix='public-bounds-tests-') as directory:
            root = Path(directory)
            sentinel = root / 'existing.txt'
            sentinel.write_bytes(b'existing unrelated bytes')
            with preparation_bounds_exit_stack() as stack:
                guards = []
                for name in ('outside_repository', 'official_opener', 'download', 'copy_local',
                             'source_integrity', 'parse_vcf'):
                    guards.append(stack.enter_context(patch.object(
                        self.preparation, name, side_effect=AssertionError(f'{name} reached before rejection'),
                    )))
                for name in ('open', 'mkdir', 'exists', 'stat'):
                    guards.append(stack.enter_context(patch.object(
                        Path, name, side_effect=AssertionError(f'Path.{name} reached before rejection'),
                    )))
                with self.assertRaisesRegex(self.preparation.PreparationError, message):
                    self.preparation.prepare(cache_dir=root / 'cache', output_dir=root / 'output',
                                             bounds=bounds, limit=1)
                for guard in guards:
                    guard.assert_not_called()
            self.assertEqual(sentinel.read_bytes(), b'existing unrelated bytes')
            self.assertEqual({path.name for path in root.iterdir()}, {'existing.txt'})
            self.assertFalse((root / 'cache').exists())
            self.assertFalse((root / 'output').exists())

    def test_each_declared_hard_ceiling_and_large_overrides_reject_before_io(self):
        self.assertEqual(self.maxima, {
            'max_compressed': 512 * 1024 * 1024, 'max_uncompressed': 4 * 1024 * 1024 * 1024,
            'max_line': 1024 * 1024, 'max_sidecar': 8192, 'max_header': 16 * 1024 * 1024,
            'max_records': 5000000, 'max_selected': 100000, 'timeout': 30, 'total_seconds': 1800,
        })
        overrides = [(name, maximum + 1) for name, maximum in self.maxima.items()]
        overrides += [('max_compressed', self.maxima['max_compressed'] * 1024),
                      ('max_uncompressed', self.maxima['max_uncompressed'] * 1024),
                      ('total_seconds', self.maxima['total_seconds'] * 100)]
        for name, value in overrides:
            with self.subTest(field=name, value=value):
                self.assert_bounds_rejected_before_io(self.preparation.Bounds(**{name: value}), name)

    def test_every_bound_requires_positive_non_bool_builtin_integer_before_limit_comparison(self):
        class IntegerSubclass(int):
            pass

        for name in self.maxima:
            for value in (True, False, 0, -1, 1.5, '1', None, IntegerSubclass(1)):
                with self.subTest(field=name, value=value, value_type=type(value).__name__):
                    self.assert_bounds_rejected_before_io(self.preparation.Bounds(**{name: value}), name)

    def test_invalid_bounds_type_or_shape_is_a_preparation_error_before_io(self):
        for value in (None, {}, 'bounds', object(), self.preparation.Bounds):
            with self.subTest(value_type=type(value).__name__):
                self.assert_bounds_rejected_before_io(value, 'Bounds')
        extra = self.preparation.Bounds()
        object.__setattr__(extra, 'unexpected', 1)
        missing = self.preparation.Bounds()
        object.__delattr__(missing, 'max_compressed')
        for value in (extra, missing):
            with self.subTest(shape=tuple(vars(value))):
                self.assert_bounds_rejected_before_io(value, 'Bounds')

    def test_all_bounds_can_tighten_together_without_changing_preparation_output(self):
        tightened = self.preparation.Bounds(**{name: maximum - 1 for name, maximum in self.maxima.items()})
        with self.source_tree() as (root, source, _):
            manifest = self.prepare_local(root, source, bounds=tightened)
            self.assertEqual(manifest['bounds'], vars(tightened))
            self.assertEqual(manifest['selection']['selected'], 1)
            self.assertEqual(manifest['fixture']['objects'], 6)
            self.assertFalse(manifest['source']['md5']['publisher_authenticated'])


import tracemalloc as preparation_tracemalloc


class PublicVariantPreparationDiskIdentityTests(PublicVariantPreparationInputs, SimpleTestCase):
    def setUp(self):
        self.preparation = import_module('genoma.public_variant_preparation')

    def small_chunks(self, *, entries=7, size=512, fan_in=2):
        return patch.multiple(self.preparation, create=True, _IDENTITY_BUFFER_ENTRIES=entries,
                              _IDENTITY_BUFFER_BYTES=size, _IDENTITY_MERGE_FAN_IN=fan_in)

    def many_rows(self, count):
        return [self.row(100000 + i, 200000 + i, 1 + i * 2, info='RS=7') for i in range(count)]

    def test_disk_runs_are_owned_and_removed_without_changing_deterministic_output(self):
        rows = self.many_rows(41)
        rows[10] = self.row(100010, 200010, 21, alt='<DEL>', info='RS=7')
        original_create = self.preparation.OwnedDirectory.create
        names = []

        def observe_create(owner, name):
            names.append((owner.path, name))
            return original_create(owner, name)

        with self.source_tree(self.vcf(rows)) as (root, source, _):
            source_before = {p.name: p.read_bytes() for p in source.iterdir()}
            with self.small_chunks(), patch.object(self.preparation.OwnedDirectory, 'create', observe_create):
                manifest = self.prepare_local(root, source, limit=2)
            # Django app labels are serialized in the catalog; pin the genoma output digest.
            self.assertEqual(manifest['fixture']['sha256'],
                             '13131f94bd5cecfdb954c43843c31d199218bd89c5f8f1a0c38dea089b5e2bb0')
            scratch = [(parent, name) for parent, name in names if name.startswith('.identity-')]
            self.assertGreater(len(scratch), 4, 'Full-source identities must use owned disk runs')
            self.assertEqual({parent for parent, _ in scratch}, {root / 'cache'})
            self.assertEqual({p.name for p in (root / 'cache').iterdir()}, set(source_before))
            self.assertEqual({p.name for p in (root / 'output').iterdir()},
                             {'catalog.json', 'preview.json', 'manifest.json'})
            self.assertEqual({p.name: p.read_bytes() for p in source.iterdir()}, source_before)
            self.assertEqual(manifest['selection']['records_scanned'], 41)
            self.assertEqual(manifest['selection']['eligible'], 40)
            self.assertEqual(manifest['selection']['skipped'], {'symbolic_or_breakend': 1})
            objects = json.loads((root / 'output/catalog.json').read_text())
            self.assertEqual([o['fields']['accession'] for o in objects
                              if o['model'] == 'genoma.externalidentifier'], ['100000', '100001'])
            first = self.outputs(root)
            self.preparation.prepare(cache_dir=root / 'cache2', output_dir=root / 'output2',
                                     local_source_dir=source, limit=2)
            self.assertEqual(first, {p.name: p.read_bytes() for p in (root / 'output2').iterdir()})

    def test_each_duplicate_identity_across_chunks_and_merge_passes_in_unsupported_tail(self):
        for kind in ('AlleleID', 'VariationID', 'assembly/coordinate/REF/ALT'):
            rows = self.many_rows(65)
            # Both duplicate participants are unsupported and beyond the selected cap.
            rows[8] = self.row(100008, 200008, 17, alt='<DEL>', info='RS=7')
            allele, record, pos = 100064, 200064, 129
            if kind == 'AlleleID':
                allele = 100008
            elif kind == 'VariationID':
                record = 200008
            else:
                pos = 17
            rows[-1] = self.row(allele, record, pos, alt='<DEL>', info='RS=7')
            with self.subTest(kind=kind), self.source_tree(self.vcf(rows)) as (root, source, _):
                with self.small_chunks(entries=3), self.assertRaisesRegex(
                    self.preparation.PreparationError, 'duplicate ' + kind,
                ):
                    self.prepare_local(root, source)
                self.assertEqual({p.name for p in root.iterdir()}, {'input'})

    def test_many_records_respect_buffer_fan_in_open_handle_and_scratch_byte_bounds(self):
        identity_class = self.preparation._DiskIdentities
        original_init, original_open, original_unlink = identity_class.__init__, Path.open, Path.unlink
        instances, active = [], set()
        peak = [0]

        class TrackedFile:
            def __init__(self, stream, path):
                self.stream, self.path = stream, path
                active.add(path)
                peak[0] = max(peak[0], len(active))

            def __getattr__(self, name):
                return getattr(self.stream, name)

            def __enter__(self):
                return self

            def __exit__(self, *args):
                self.close()

            def close(self):
                self.stream.close()
                active.discard(self.path)

        def observe_init(instance, *args, **kwargs):
            original_init(instance, *args, **kwargs)
            instances.append(instance)

        def observe_open(path, *args, **kwargs):
            stream = original_open(path, *args, **kwargs)
            return TrackedFile(stream, path) if path.name.startswith('.identity-') else stream

        def observe_unlink(path, *args, **kwargs):
            self.assertNotIn(path, active, 'Windows handles must close before unlink')
            return original_unlink(path, *args, **kwargs)

        with self.source_tree(self.vcf(self.many_rows(128))) as (root, source, _):
            with self.small_chunks(size=100), patch.object(identity_class, '__init__', observe_init), \
                    patch.object(Path, 'open', observe_open), patch.object(Path, 'unlink', observe_unlink):
                manifest = self.prepare_local(root, source, bounds=self.preparation.Bounds(max_records=128))
            self.assertEqual(manifest['selection']['records_scanned'], 128)
            self.assertEqual(len(instances), 1)
            index = instances[0]
            self.assertLessEqual(index.peak_buffer_bytes, 100)
            self.assertLessEqual(index.peak_buffer_entries, 7)
            self.assertGreaterEqual(index.merge_passes, 2)
            self.assertLessEqual(peak[0], 3, 'Two inputs plus one output at most')
            self.assertGreater(peak[0], 1)
            self.assertFalse(active)
            self.assertLessEqual(index.peak_scratch_bytes, 2 * 128 * 580)
            print(f'DISK_IDENTITY_RESOURCE_PROBE entries={index.peak_buffer_entries} '
                  f'buffer_bytes={index.peak_buffer_bytes} open_files={peak[0]} '
                  f'passes={index.merge_passes} scratch_bytes={index.peak_scratch_bytes}')

    def test_parser_memory_does_not_retain_all_source_identity_keys_at_fixed_selection(self):
        peaks = []
        for count in (2000, 20000):
            # Construct/compress input BEFORE tracing parser allocations.
            content = self.vcf(self.many_rows(count))
            with self.source_tree(content) as (root, source, _), self.small_chunks(
                entries=128, size=8192, fan_in=4,
            ):
                preparation_tracemalloc.start()
                try:
                    manifest = self.prepare_local(root, source)
                    peaks.append(preparation_tracemalloc.get_traced_memory()[1])
                finally:
                    preparation_tracemalloc.stop()
                self.assertEqual(manifest['selection']['selected'], 1)
                self.assertEqual(manifest['selection']['records_scanned'], count)
                self.assertEqual({p.name for p in (root / 'cache').iterdir()},
                                 {'clinvar_20260928.vcf.gz', 'clinvar_20260928.vcf.gz.md5'})
        print(f'DISK_IDENTITY_TRACEMALLOC_BYTES small={peaks[0]} large={peaks[1]}')
        self.assertLessEqual(peaks[1], peaks[0] + 2 * 1024 * 1024,
                             'Source-wide identity memory must not grow as three all-record sets')

    def test_partial_chunk_merge_write_read_and_transient_unlink_failures_clean_owned_files(self):
        for fault in ('chunk_write', 'merge_write', 'merge_read', 'unlink', 'persistent_unlink'):
            original_open, original_unlink = Path.open, Path.unlink
            fired, denied = [], []

            class FaultFile:
                def __init__(self, stream, mode, path):
                    self.stream, self.mode, self.path = stream, mode, path

                def __getattr__(self, name):
                    return getattr(self.stream, name)

                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    self.stream.close()

                def write(self, data):
                    target = '.identity-chunk-' if fault == 'chunk_write' else '.identity-merge-'
                    if not fired and fault.endswith('_write') and self.path.name.startswith(target):
                        fired.append(fault)
                        self.stream.write(data[:-1])
                        return len(data) - 1
                    return self.stream.write(data)

                def readline(self, *args):
                    if not fired and fault == 'merge_read' and self.mode == 'rb':
                        fired.append(fault)
                        return b'A123'  # Incomplete owned run record, not a valid identity entry.
                    return self.stream.readline(*args)

            def inject_open(path, mode='r', *args, **kwargs):
                stream = original_open(path, mode, *args, **kwargs)
                return FaultFile(stream, mode, path) if path.name.startswith('.identity-') else stream

            def inject_unlink(path, *args, **kwargs):
                if fault == 'persistent_unlink' and path.name.startswith('.identity-'):
                    if not fired:
                        fired.append(fault)
                        denied.append(path)
                    if path == denied[0]:
                        raise PermissionError('test persistent scratch unlink failure')
                if not fired and fault == 'unlink' and path.name.startswith('.identity-'):
                    fired.append(fault)
                    raise OSError('test scratch unlink failure')
                return original_unlink(path, *args, **kwargs)

            with self.subTest(fault=fault), self.source_tree(self.vcf(self.many_rows(41))) as (root, source, _):
                keep = root / 'keep.txt'
                keep.write_bytes(b'preserved')
                before = {p.name: p.read_bytes() for p in source.iterdir()}
                with self.small_chunks(), patch.object(Path, 'open', inject_open), \
                        patch.object(Path, 'unlink', inject_unlink), self.assertRaises(self.preparation.PreparationError):
                    self.prepare_local(root, source)
                self.assertEqual(fired, [fault])
                if fault == 'persistent_unlink':
                    self.assertEqual({p.name for p in root.iterdir()}, {'input', 'keep.txt', 'cache'})
                    self.assertEqual(set((root / 'cache').iterdir()), set(denied))
                    self.assertFalse((root / 'output').exists())
                else:
                    self.assertEqual({p.name for p in root.iterdir()}, {'input', 'keep.txt'})
                self.assertEqual(keep.read_bytes(), b'preserved')
                self.assertEqual({p.name: p.read_bytes() for p in source.iterdir()}, before)

    def test_exclusive_scratch_collision_preserves_foreign_file_and_never_recursively_cleans(self):
        original_open = Path.open
        collided = []

        def collide(path, mode='r', *args, **kwargs):
            if not collided and path.name.startswith('.identity-') and mode == 'xb':
                collided.append(path)
                with original_open(path, 'xb') as stream:
                    stream.write(b'foreign scratch-name occupant')
            return original_open(path, mode, *args, **kwargs)

        with self.source_tree(self.vcf(self.many_rows(41))) as (root, source, _):
            with self.small_chunks(), patch.object(Path, 'open', collide), \
                    self.assertRaises(self.preparation.PreparationError):
                self.prepare_local(root, source)
            self.assertEqual(len(collided), 1)
            self.assertEqual(collided[0].read_bytes(), b'foreign scratch-name occupant')
            self.assertEqual(set((root / 'cache').iterdir()), set(collided))
            self.assertFalse((root / 'output').exists())
            self.assertEqual(len(list(source.iterdir())), 2)

    def test_tail_crc_record_cap_and_run_count_ceiling_still_fail_without_outputs(self):
        content = self.vcf(self.many_rows(41))
        for fault in ('crc', 'records', 'runs'):
            data = bytearray(preparation_gzip.compress(content, mtime=0))
            if fault == 'crc':
                data[-8] ^= 1
            with self.subTest(fault=fault), self.source_tree(compressed=bytes(data)) as (root, source, _):
                with self.small_chunks(), patch.object(self.preparation, '_IDENTITY_MAX_RUNS',
                                                       2 if fault == 'runs' else 4096, create=True), \
                        self.assertRaises(self.preparation.PreparationError):
                    self.prepare_local(root, source,
                                       bounds=self.preparation.Bounds(max_records=10)
                                       if fault == 'records' else self.preparation.Bounds())
                self.assertEqual({p.name for p in root.iterdir()}, {'input'})
