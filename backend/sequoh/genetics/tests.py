import json
from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth.models import Group, User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.jwt_utils import encode_jwt
from accounts.models import AppUser
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
