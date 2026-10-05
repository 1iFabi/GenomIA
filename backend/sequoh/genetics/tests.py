import json
import os
import uuid
from io import StringIO
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from importlib import import_module, reload
from threading import Barrier
from unittest.mock import call, patch

from django.conf import settings
from django.contrib.auth.models import Group, User
from django.contrib.postgres.functions import TransactionNow
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import DataError, IntegrityError, connection, connections, models, transaction
from django.db.migrations.loader import MigrationLoader
from django.db.models.deletion import CASCADE, PROTECT, RESTRICT, SET_NULL, ProtectedError, RestrictedError
from django.test import TestCase, TransactionTestCase
from django.test.utils import CaptureQueriesContext
from django.urls import resolve
from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.jwt_utils import encode_jwt
from accounts.models import AppUser, Role
from accounts.roles import grant_admin_role, grant_analyst_role, grant_reception_role
from genetics import models as domain, synthetic_import as bundle
from participants.models import Participant
from genetics.models import SNP, UserSNP
from genetics.upload_views import UploadGeneticFileAPIView
from profiles.models import Profile, ServiceStatus
from services.models import (
    Purchase, PurchaseStatus, Sample, ServiceRequest, ServiceStatus as RequestStatus,
    ServiceStatusLog,
)


class SyntheticServiceResultReadTests(APITestCase):
    list_url = '/api/genomics/v1/services/'

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

    def assert_response(self, response, status, body):
        self.assertEqual(response.status_code, status)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertEqual(response.json(), body)

    def assert_hidden(self):
        self.assert_response(self.client.get(self.detail_url()), 404, {'detail': 'Not found.'})
        self.assert_response(self.client.get(self.list_url), 200, {'services': []})

    def summary(self, receipt=None):
        receipt = receipt or self.receipt
        sample = Sample.objects.get(pk=receipt.sample_id)
        return {
            'service_request_id': str(receipt.service_request_id), 'sample_id': str(receipt.sample_id),
            'sample_code': sample.sample_code, 'release_version': bundle.DEMO_VERSION,
            'synthetic': True, 'non_clinical': True, 'disclaimer': bundle.DISCLAIMER,
        }

    def state(self):
        return [list(model.objects.order_by('pk').values()) for model in (
            User, AppUser, Participant, Profile, SNP, UserSNP, Purchase, ServiceRequest,
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
        with CaptureQueriesContext(connection) as queries:
            self.assert_response(self.client.get(self.list_url), 200, {'services': [expected]})
            self.assert_response(self.client.get(self.detail_url()), 200, expected | {'results': expected_results})
        self.assertFalse(any(query['sql'].lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE'))
                             for query in queries.captured_queries))
        self.assertFalse(any('"genotype"' in query['sql'] or 'COUNT(' in query['sql'].upper()
                             for query in queries.captured_queries))
        self.assertEqual(self.state(), before)

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

    def test_unauthenticated_gets_are_denied_without_domain_queries(self):
        self.client.cookies.clear()
        for path in (self.list_url, self.detail_url()):
            with self.subTest(path=path), self.assertNumQueries(0):
                self.assertIn(self.client.get(path).status_code, (401, 403))

    def test_other_owner_missing_and_malformed_identifiers_are_indistinguishable_even_with_staff_flags(self):
        self.other.is_staff = self.other.is_superuser = True
        self.other.save(update_fields=['is_staff', 'is_superuser'])
        self.other.groups.add(Group.objects.get_or_create(name='ADMIN')[0])
        self.authenticate(self.other)
        for identifier in (self.receipt.service_request_id, uuid.uuid4(), 'not-a-uuid', '-1'):
            self.assert_response(self.client.get(self.detail_url(identifier)), 404, {'detail': 'Not found.'})
        self.assert_response(self.client.get(self.list_url), 200, {'services': [self.summary(self.other_receipt)]})
        for grant in (grant_admin_role, grant_analyst_role, grant_reception_role):
            with self.subTest(role=grant.__name__):
                grant(self.other)
                for identifier in (self.receipt.service_request_id, self.other_receipt.service_request_id, uuid.uuid4()):
                    self.assert_response(self.client.get(self.detail_url(identifier)), 404, {'detail': 'Not found.'})
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
        expected = self.summary()
        self.assert_response(self.client.get(self.list_url + query), 200, {'services': [expected]})
        response = self.client.get(self.detail_url() + query)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['service_request_id'], str(self.receipt.service_request_id))

    def test_existing_nonsynthetic_participant_is_supported_without_disclosing_or_rewriting_it(self):
        user = User.objects.create_user(username='synthetic-read-existing-participant')
        participant = Participant.objects.create(
            user=user, participant_code='existing-read-participant', metadata=['existing'],
            consent_status='withdrawn', enrollment_status='inactive',
        )
        receipt = bundle.import_synthetic_genomics(user_id=user.pk)
        before = self.state()
        self.authenticate(user)
        self.assert_response(self.client.get(self.list_url), 200, {'services': [self.summary(receipt)]})
        response = self.client.get(self.detail_url(receipt.service_request_id))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(str(participant.pk), response.content.decode())
        self.assertNotIn(participant.participant_code, response.content.decode())
        self.assertEqual(self.state(), before)

    def test_both_endpoints_use_the_importer_guard_before_any_domain_query(self):
        self.client.force_authenticate(user=self.user)
        with patch.object(bundle, '_require_local_development', side_effect=CommandError(bundle.LOCAL_ONLY)) as guard:
            for path in (self.list_url, self.detail_url()):
                with self.assertNumQueries(0):
                    self.assert_response(self.client.get(path), 404, {'detail': 'Not found.'})
            self.assertEqual(guard.call_count, 2)
        with patch.object(bundle, '_require_local_development', wraps=bundle._require_local_development) as guard:
            for path in (self.list_url, self.detail_url()):
                with CaptureQueriesContext(connection) as queries:
                    self.assertEqual(self.client.get(path).status_code, 200)
                self.assertTrue(queries.captured_queries[0]['sql'].startswith('SELECT current_database()'))
            self.assertEqual(guard.call_count, 2)

    def test_disabled_environment_returns_generic_404_without_domain_queries(self):
        self.client.force_authenticate(user=self.user)
        for environment in ('', 'production', 'staging', 'test', 'dev', 'Development'):
            with self.subTest(environment=environment), patch.dict(os.environ, {'ENVIRONMENT': environment}):
                for path in (self.list_url, self.detail_url()):
                    with self.assertNumQueries(0):
                        self.assert_response(self.client.get(path), 404, {'detail': 'Not found.'})
        with patch.dict(os.environ):
            os.environ.pop('ENVIRONMENT')
            with self.assertNumQueries(0):
                self.assert_response(self.client.get(self.list_url), 404, {'detail': 'Not found.'})
        for options in ({'DEBUG': False}, {'DEBUG': 1}, {'DATABASE_ROUTERS': [object()]}):
            with self.subTest(settings=options), self.settings(**options):
                for path in (self.list_url, self.detail_url()):
                    with self.assertNumQueries(0):
                        self.assert_response(self.client.get(path), 404, {'detail': 'Not found.'})
        for key in ('RENDER', 'RENDER_EXTERNAL_HOSTNAME'):
            with patch.dict(os.environ, {key: 'deployment-present'}), self.assertNumQueries(0):
                self.assert_response(self.client.get(self.detail_url()), 404, {'detail': 'Not found.'})
        for config in ({'HOST': '192.0.2.1'}, {'NAME': 'postgres'},
                       {'ENGINE': 'django.db.backends.sqlite3'}, {'OPTIONS': {'host': 'override'}}):
            with self.subTest(config=config), patch.dict(connection.settings_dict, config):
                for path in (self.list_url, self.detail_url()):
                    with self.assertNumQueries(0):
                        self.assert_response(self.client.get(path), 404, {'detail': 'Not found.'})

    def test_actual_database_guard_rejection_performs_only_the_importers_server_identity_query(self):
        self.client.force_authenticate(user=self.user)
        for database, address in ((connection.settings_dict['NAME'], '192.0.2.1'),
                                  ('unexpected_database', '127.0.0.1')):
            for path in (self.list_url, self.detail_url()):
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

    def test_only_get_is_supported_and_legacy_routes_status_counts_and_rows_are_unchanged(self):
        from genetics import urls

        self.assertEqual([str(route.pattern) for route in urls.urlpatterns], [
            'genetics/diseases/', 'genetics/patient-variants/<int:user_id>/', 'genetics/variantes/',
            'genetics/ancestry/', 'genetics/indigenous/', 'genetics/traits/', 'genetics/biometrics/',
            'genetics/biomarkers/', 'genetics/pharmacogenetics/', 'ingest/upload-genetic-file/',
            'ingest/delete-genetic-file/', 'ingest/user-report-status/<int:user_id>/',
            'genomics/v1/services/', 'genomics/v1/services/<str:service_request_id>/results/',
        ])
        self.assertEqual(resolve('/api/report/pdf/').view_name, 'api_report_pdf')
        self.assertEqual(resolve('/api/ingest/user-report-status/1/').view_name, 'api_user_report_status')
        self.assertEqual(resolve('/api/auth/service/status/').view_name, 'api_service_status')
        snp = SNP.objects.create(rsid='rs-read-legacy', genotipo='unknown', fenotipo='Legacy row')
        UserSNP.objects.create(user=self.user, snp=snp)
        Profile.objects.create(user=self.user, service_status=ServiceStatus.COMPLETED, report_filename='legacy.txt')
        legacy_paths = ('/api/auth/service/status/', '/api/genetics/traits/', '/api/genetics/ancestry/')
        legacy_before = [(self.client.get(path).status_code, self.client.get(path).json()) for path in legacy_paths]
        before = self.state()
        for path in (self.list_url, self.detail_url()):
            self.assertEqual(self.client.get(path).status_code, 200)
            self.assertEqual(self.client.post(path, {}, format='json').status_code, 405)
        self.assertEqual([(self.client.get(path).status_code, self.client.get(path).json())
                          for path in legacy_paths], legacy_before)
        self.assertEqual(self.state(), before)
        grant_admin_role(self.other)
        self.authenticate(self.other)
        self.assert_response(self.client.get(f'/api/ingest/user-report-status/{self.user.pk}/'), 200, {
            'user_id': self.user.pk, 'has_report': False, 'snp_count': 1,
            'service_status': ServiceStatus.NO_PURCHASED, 'report_filename': None, 'report_date': None,
        })


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
        call_command('import_synthetic_genomics', '--user-id', str((user or self.user).pk), stdout=output)
        return output.getvalue()

    def legacy_state(self):
        return [list(model.objects.order_by('pk').values()) for model in (
            User, AppUser, Profile, SNP, UserSNP, domain.Genotype, domain.Variant,
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
        from services.legacy_profile import get_legacy_service_projection
        projection = get_legacy_service_projection(self.user)
        # No history is fabricated to satisfy the unchanged fail-closed legacy projection.
        self.assertEqual(projection.service_status, ServiceStatus.NO_PURCHASED)
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
        from genetics.synthetic_import import DEMO_NAME, DEMO_VERSION
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

    def test_legacy_rows_and_raw_report_counters_are_preserved_without_publishing_placeholders(self):
        grant_admin_role(self.other)
        snp = SNP.objects.create(rsid='rs-synthetic-legacy', genotipo='unknown', fenotipo='Legacy row')
        UserSNP.objects.create(user=self.user, snp=snp)
        UserSNP.objects.create(user=self.other, snp=snp)
        Profile.objects.create(
            user=self.user, service_status=ServiceStatus.COMPLETED, sample_code='LEGACY-SYNTHETIC',
            report_filename='legacy.txt', report_uploaded_at=timezone.now(),
        )
        before = self.legacy_state()
        self.import_demo()
        self.assertEqual(self.legacy_state(), before)
        self.client.cookies[settings.AUTH_COOKIE_NAME] = encode_jwt({'sub': str(self.other.pk)})
        response = self.client.get(f'/api/ingest/user-report-status/{self.user.pk}/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {
            'user_id': self.user.pk, 'has_report': False, 'snp_count': 1,
            'service_status': ServiceStatus.NO_PURCHASED, 'report_filename': None, 'report_date': None,
        })
        self.assertEqual(UserSNP.objects.filter(user=self.other).count(), 1)

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
                call_command('import_synthetic_genomics', '--user-id', str(user_id), stdout=output)
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
            reload(import_module('genetics.synthetic_import'))
            reload(import_module('genetics.management.commands.import_synthetic_genomics'))
        output = StringIO()
        call_command('makemigrations', check=True, dry_run=True, stdout=output)
        self.assertIn('No changes detected', output.getvalue())


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
        migration = import_module('genetics.migrations.0014_artifact').Migration
        self.assertIn(('genetics', '0013_genotype'), migration.dependencies)
        loader = MigrationLoader(connection)
        state = loader.project_state([('genetics', '0014_artifact')])
        historical = state.apps.get_model('genetics', 'Artifact')
        self.assertEqual(
            {field.name: field.deconstruct()[1:] for field in historical._meta.local_fields},
            {field.name: field.deconstruct()[1:] for field in domain.Artifact._meta.local_fields},
        )
        self.assertEqual(historical._meta.indexes, domain.Artifact._meta.indexes)
        self.assertEqual(historical._meta.constraints, domain.Artifact._meta.constraints)
        self.assertIn(('genetics', '0013_genotype'), loader.graph.forwards_plan(('genetics', '0014_artifact')))


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
        migration = import_module('genetics.migrations.0014_artifact')
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
        self.assertIs(migration.Migration.operations[-1].reverse_code, migration.restore_artifact_fks)

    def test_fk_lookup_failure_does_not_partially_replace_constraints(self):
        self.assertTrue(hasattr(domain, 'Artifact'), 'Artifact schema model is missing.')
        migration = import_module('genetics.migrations.0014_artifact')
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
        migration = import_module('genetics.migrations.0015_analysis_result').Migration
        self.assertIn(('genetics', '0014_artifact'), migration.dependencies)
        loader = MigrationLoader(connection)
        state = loader.project_state([('genetics', '0015_analysis_result')])
        historical = state.apps.get_model('genetics', 'AnalysisResult')
        self.assertEqual(
            {field.name: field.deconstruct()[1:] for field in historical._meta.local_fields},
            {field.name: field.deconstruct()[1:] for field in domain.AnalysisResult._meta.local_fields},
        )
        self.assertEqual(historical._meta.indexes, domain.AnalysisResult._meta.indexes)
        self.assertEqual(historical._meta.constraints, domain.AnalysisResult._meta.constraints)
        self.assertIn(('genetics', '0014_artifact'), loader.graph.forwards_plan(('genetics', '0015_analysis_result')))


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
        migration = import_module('genetics.migrations.0015_analysis_result')
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
        migration = import_module('genetics.migrations.0015_analysis_result')
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
        migration = import_module('genetics.migrations.0013_genotype').Migration
        self.assertEqual(set(migration.dependencies), {
            ('genetics', '0012_release_epigenetic_feature'),
            ('participants', '0003_participant_metadata_support'),
            ('services', '0004_sample'),
        })
        loader = MigrationLoader(connection)
        state = loader.project_state([('genetics', '0013_genotype')])
        historical = state.apps.get_model('genetics', 'Genotype')
        self.assertEqual(
            {field.name: field.deconstruct()[1:] for field in historical._meta.local_fields},
            {field.name: field.deconstruct()[1:] for field in domain.Genotype._meta.local_fields},
        )
        self.assertEqual(historical._meta.indexes, domain.Genotype._meta.indexes)
        self.assertEqual(historical._meta.constraints, domain.Genotype._meta.constraints)
        self.assertIn(('genetics', '0013_genotype'), loader.graph.nodes)
        self.assertIn(('participants', '0003_participant_metadata_support'),
                      loader.graph.forwards_plan(('genetics', '0013_genotype')))
        self.assertIn(('services', '0004_sample'), loader.graph.forwards_plan(('genetics', '0013_genotype')))


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
        migration = import_module('genetics.migrations.0013_genotype')
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
        self.assertIs(migration.Migration.operations[-1].reverse_code, migration.restore_genotype_fks)

    def test_fk_lookup_resolves_every_relation_before_any_constraint_ddl(self):
        migration = import_module('genetics.migrations.0013_genotype')
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
        migration = import_module('genetics.migrations.0012_release_epigenetic_feature').Migration
        return migration.operations[2], MigrationLoader(connection).project_state([('genetics', '0012_release_epigenetic_feature')])

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
        others = (SNP, UserSNP, domain.DataRelease, domain.EpigeneticFeature, domain.Analysis, domain.ReleaseVariant,
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
            operation.database_backwards('genetics', editor, state, state)
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
            operation.database_forwards('genetics', editor, state, state)
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
                                        apply('genetics', editor, state, state)
                                    execute.assert_not_called()
                                self.assertEqual(editor.deferred_sql, ['SELECT 1'])
                            finally:
                                editor.deferred_sql.clear()
                            self.assertEqual(self.fk_actions(), before)
                            transaction.set_rollback(True)
                operation.database_backwards('genetics', editor, state, state)
            operation.database_forwards('genetics', editor, state, state)
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
            operation.database_forwards('genetics', editor, state, state)
            self.assertEqual(self.fk_actions(), expected | decoys)
            for field, _, _, name, _, _ in self.fk_specs:
                quoted = '"' + f'reverse "{field}" FK'.replace('"', '""') + '"'
                cursor.execute(f'ALTER TABLE release_epigenetic_feature RENAME CONSTRAINT {name} TO {quoted}')
            operation.database_backwards('genetics', editor, state, state)
            self.assertEqual(self.fk_actions(), {name: ('a', 'a', True, True) for name in expected} | decoys)
            transaction.set_rollback(True)

    def test_full_migration_reversal_and_reapplication_preserve_parents_and_exact_catalog(self):
        migration = import_module('genetics.migrations.0012_release_epigenetic_feature').Migration('0012_release_epigenetic_feature', 'genetics')
        prior = MigrationLoader(connection).project_state([('genetics', '0011_release_variant')])
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
            migration = reload(import_module('genetics.migrations.0012_release_epigenetic_feature')).Migration
        self.assertEqual(migration.dependencies, [('genetics', '0011_release_variant')])
        self.assertEqual([type(operation).__name__ for operation in migration.operations], ['CreateModel', 'RunPython', 'RunPython'])
        self.assertEqual(migration.operations[0].name, 'ReleaseEpigeneticFeature')
        self.assertTrue(all(operation.reversible for operation in migration.operations))
        historical = MigrationLoader(connection).project_state([('genetics', '0012_release_epigenetic_feature')]).apps.get_model('genetics', 'ReleaseEpigeneticFeature')
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
        migration = import_module('genetics.migrations.0011_release_variant').Migration
        return migration.operations[1], MigrationLoader(connection).project_state([('genetics', '0011_release_variant')])

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
        others = (SNP, UserSNP, domain.DataRelease, domain.Variant, domain.VariantPlacement, domain.Analysis,
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
            operation.database_backwards('genetics', editor, state, state)
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
            operation.database_forwards('genetics', editor, state, state)
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
                                    apply('genetics', editor, state, state)
                                execute.assert_not_called()
                            self.assertEqual(self.fk_actions(), before)
                            transaction.set_rollback(True)
                operation.database_backwards('genetics', editor, state, state)
            operation.database_forwards('genetics', editor, state, state)
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
            operation.database_forwards('genetics', editor, state, state)
            self.assertEqual(self.fk_actions(), expected | decoys)
            operation.database_backwards('genetics', editor, state, state)
            self.assertEqual(self.fk_actions(), {name: ('a', 'a', True, True) for name in expected} | decoys)
            transaction.set_rollback(True)

    def test_entire_migration_reverses_table_then_recreates_exact_schema_and_accepts_native_keys(self):
        migration = import_module('genetics.migrations.0011_release_variant').Migration('0011_release_variant', 'genetics')
        prior = MigrationLoader(connection).project_state([('genetics', '0010_allele_frequency')])
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
            migration = reload(import_module('genetics.migrations.0011_release_variant')).Migration
        self.assertEqual(migration.dependencies, [('genetics', '0010_allele_frequency')])
        self.assertEqual([type(operation).__name__ for operation in migration.operations], ['CreateModel', 'RunPython'])
        self.assertEqual(migration.operations[0].name, 'ReleaseVariant')
        self.assertTrue(migration.operations[1].reversible)
        historical = MigrationLoader(connection).project_state([('genetics', '0011_release_variant')]).apps.get_model('genetics', 'ReleaseVariant')
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
        others = (SNP, UserSNP, domain.DataRelease, domain.Variant, domain.Population, domain.Analysis,
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
        operation = import_module('genetics.migrations.0010_allele_frequency').Migration.operations[1]
        state = MigrationLoader(connection).project_state([('genetics', '0010_allele_frequency')])
        frequency, release, analysis = self.linked_frequency()
        parents = {'release': release, 'variant': self.variant, 'population': self.population, 'analysis': analysis}
        # Flush the fixture's unrelated, deferred Analysis.release FK before schema DDL.
        connection.check_constraints()
        expected = self.fk_actions()
        with connection.schema_editor() as editor, connection.cursor() as cursor:
            operation.database_backwards('genetics', editor, state, state)
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
            operation.database_forwards('genetics', editor, state, state)
            self.assertEqual(self.fk_actions(), expected)

    def test_every_missing_or_ambiguous_lookup_fails_before_any_fk_replacement_in_both_directions(self):
        operation = import_module('genetics.migrations.0010_allele_frequency').Migration.operations[1]
        state = MigrationLoader(connection).project_state([('genetics', '0010_allele_frequency')])
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
                                    apply('genetics', editor, state, state)
                                execute.assert_not_called()
                            self.assertEqual(self.fk_actions(), before)
                            transaction.set_rollback(True)
                operation.database_backwards('genetics', editor, state, state)
            operation.database_forwards('genetics', editor, state, state)
            self.assertEqual(self.fk_actions(), expected)

    def test_fk_lookup_matches_exact_relations_attnums_and_quotes_discovered_names(self):
        operation = import_module('genetics.migrations.0010_allele_frequency').Migration.operations[1]
        state = MigrationLoader(connection).project_state([('genetics', '0010_allele_frequency')])
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
            operation.database_forwards('genetics', editor, state, state)
            self.assertEqual(self.fk_actions(), expected | decoys)
            operation.database_backwards('genetics', editor, state, state)
            self.assertEqual(self.fk_actions(), {name: ('a', 'a', True, True) for name in expected} | decoys)
            transaction.set_rollback(True)

    def test_schema_only_migration_dependency_state_and_postgresql_index_deconstruction(self):
        with self.assertNumQueries(0):
            migration = reload(import_module('genetics.migrations.0010_allele_frequency')).Migration
        self.assertEqual(migration.dependencies, [('genetics', '0009_variant_annotation')])
        self.assertEqual([type(operation).__name__ for operation in migration.operations], ['CreateModel', 'RunPython'])
        self.assertEqual(migration.operations[0].name, 'AlleleFrequency')
        self.assertTrue(migration.operations[1].reversible)
        historical = MigrationLoader(connection).project_state([('genetics', '0010_allele_frequency')]).apps.get_model('genetics', 'AlleleFrequency')
        self.assertEqual(historical._meta.db_table, domain.AlleleFrequency._meta.db_table)
        self.assertEqual({field.name: field.deconstruct()[1:] for field in historical._meta.local_fields},
                         {field.name: field.deconstruct()[1:] for field in domain.AlleleFrequency._meta.local_fields})
        self.assertEqual(historical._meta.indexes, domain.AlleleFrequency._meta.indexes)
        self.assertEqual(historical._meta.constraints, domain.AlleleFrequency._meta.constraints)
        index = domain.AlleleFrequency._meta.indexes[0]
        self.assertIsInstance(index, domain.PostgreSQLIndex)
        self.assertEqual(index.max_name_length, 63)
        path, args, kwargs = index.deconstruct()
        self.assertEqual(path, 'genetics.models.PostgreSQLIndex')
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
        others = (SNP, UserSNP, domain.Variant, domain.VariantPlacement, domain.Analysis,
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
        operation = import_module('genetics.migrations.0009_variant_annotation').Migration.operations[1]
        state = MigrationLoader(connection).project_state([('genetics', '0009_variant_annotation')])
        with connection.schema_editor() as editor, connection.cursor() as cursor:
            expected = self.fk_actions()
            operation.database_backwards('genetics', editor, state, state)
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
                                apply('genetics', editor, state, state)
                            self.assertEqual(self.fk_actions(), before)
                            transaction.set_rollback(True)
                operation.database_forwards('genetics', editor, state, state)
            self.assertEqual(self.fk_actions(), expected)

    def test_fk_lookup_uses_exact_relations_attnums_and_quotes_discovered_names(self):
        operation = import_module('genetics.migrations.0009_variant_annotation').Migration.operations[1]
        state = MigrationLoader(connection).project_state([('genetics', '0009_variant_annotation')])
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
            operation.database_forwards('genetics', editor, state, state)
            self.assertEqual(self.fk_actions(), expected | decoys)
            operation.database_backwards('genetics', editor, state, state)
            self.assertEqual(self.fk_actions(), {name: ('a', 'a', True, True) for name in expected} | decoys)
            transaction.set_rollback(True)

    def test_schema_only_migration_dependency_and_state_match_model(self):
        with self.assertNumQueries(0):
            migration = reload(import_module('genetics.migrations.0009_variant_annotation')).Migration
        self.assertEqual(migration.dependencies, [('genetics', '0008_epigenetic_feature')])
        self.assertEqual([type(operation).__name__ for operation in migration.operations], ['CreateModel', 'RunPython'])
        self.assertEqual(migration.operations[0].name, 'VariantAnnotation')
        self.assertTrue(migration.operations[1].reversible)
        historical = MigrationLoader(connection).project_state([('genetics', '0009_variant_annotation')]).apps.get_model('genetics', 'VariantAnnotation')
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

    def test_explicit_values_and_duplicate_regions_preserve_unrelated_legacy_rows(self):
        legacy = SNP.objects.create(rsid='synthetic-epi', genotipo='AA', fenotipo='Unrelated legacy row')
        UserSNP.objects.create(user=User.objects.create_user(username='epigenetic-legacy'), snp=legacy)
        self.assertEqual((SNP.objects.count(), UserSNP.objects.count()), (1, 1))
        other_models = (SNP, UserSNP, domain.Analysis, domain.DataRelease, domain.Variant,
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
        legacy.refresh_from_db()
        self.assertEqual(legacy.fenotipo, 'Unrelated legacy row')

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
            migration = reload(import_module('genetics.migrations.0008_epigenetic_feature')).Migration
        self.assertEqual(migration.dependencies, [('genetics', '0007_population')])
        self.assertEqual([type(operation).__name__ for operation in migration.operations], ['CreateModel'])
        self.assertEqual(migration.operations[0].name, 'EpigeneticFeature')
        historical = MigrationLoader(connection).project_state([('genetics', '0008_epigenetic_feature')]).apps.get_model(
            'genetics', 'EpigeneticFeature',
        )
        self.assertEqual(historical._meta.db_table, domain.EpigeneticFeature._meta.db_table)
        self.assertEqual({field.name: field.deconstruct()[1:] for field in historical._meta.local_fields},
                         {field.name: field.deconstruct()[1:] for field in domain.EpigeneticFeature._meta.local_fields})
        self.assertEqual(historical._meta.indexes, domain.EpigeneticFeature._meta.indexes)
        self.assertEqual(historical._meta.constraints, domain.EpigeneticFeature._meta.constraints)
        field = domain.EpigeneticFeature._meta.get_field('strand')
        _, path, args, kwargs = field.deconstruct()
        self.assertEqual(path, 'genetics.models.FixedCharField')
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
        other_models = (SNP, UserSNP, domain.Analysis, domain.DataRelease, domain.Variant,
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
        operation = import_module('genetics.migrations.0007_population').Migration.operations[1]
        state = MigrationLoader(connection).project_state([('genetics', '0007_population')])
        with connection.schema_editor() as editor, connection.cursor() as cursor:
            expected = self.fk_actions()
            operation.database_backwards('genetics', editor, state, state)
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
                        operation.database_forwards('genetics', editor, state, state)
                    self.assertEqual(self.fk_actions(), before)
                    transaction.set_rollback(True)
            operation.database_forwards('genetics', editor, state, state)
            self.assertEqual(self.fk_actions(), expected)

    def test_fk_lookup_matches_exact_source_and_target_attnums(self):
        operation = import_module('genetics.migrations.0007_population').Migration.operations[1]
        state = MigrationLoader(connection).project_state([('genetics', '0007_population')])
        with transaction.atomic(), connection.schema_editor() as editor, connection.cursor() as cursor:
            expected = self.fk_actions()
            cursor.execute('ALTER TABLE population ADD CONSTRAINT decoy_unique UNIQUE (parent_population_id)')
            for name, source, target in (('decoy_source', 'population_id', 'population_id'),
                                         ('decoy_target', 'parent_population_id', 'parent_population_id')):
                cursor.execute(f'ALTER TABLE population ADD CONSTRAINT {name} FOREIGN KEY ({source}) '
                               f'REFERENCES population ({target}) DEFERRABLE INITIALLY DEFERRED')
            operation.database_backwards('genetics', editor, state, state)
            operation.database_forwards('genetics', editor, state, state)
            self.assertEqual(self.fk_actions(), expected | {name: ('a', 'a', True, True) for name in ('decoy_source', 'decoy_target')})
            transaction.set_rollback(True)

    def test_schema_only_migration_dependency_and_state_match_model(self):
        with self.assertNumQueries(0):
            migration = reload(import_module('genetics.migrations.0007_population')).Migration
        self.assertEqual(migration.dependencies, [('genetics', '0006_external_identifier')])
        self.assertEqual([type(operation).__name__ for operation in migration.operations], ['CreateModel', 'RunPython'])
        self.assertEqual(migration.operations[0].name, 'Population')
        self.assertTrue(migration.operations[1].reversible)
        historical = MigrationLoader(connection).project_state([('genetics', '0007_population')]).apps.get_model('genetics', 'Population')
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
