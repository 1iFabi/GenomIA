import json
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from accounts.jwt_utils import encode_jwt
from accounts.roles import grant_admin_role, grant_analyst_role, grant_reception_role
from genetics.models import SNP, UserSNP
from genetics.upload_views import UploadGeneticFileAPIView
from profiles.models import Profile, ServiceStatus
from services.models import (
    Purchase, PurchaseStatus, ServiceRequest, ServiceStatus as RequestStatus,
    ServiceStatusLog,
)


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
