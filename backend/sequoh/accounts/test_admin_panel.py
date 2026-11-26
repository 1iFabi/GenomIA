import json
from urllib.parse import urlencode
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import User
from django.db.models import F
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from participants.models import Participant
from reception.models import ReceptionAccessLog
from services.models import Purchase, PurchaseStatus, ServiceRequest, ServiceStatus as RequestStatus, ServiceStatusLog

from .jwt_utils import encode_jwt
from .models import GeneticDataAccessLog
from .roles import grant_admin_role, grant_analyst_role, grant_reception_role

OVERVIEW = '/api/admin/overview/'
ACTIVITY = '/api/admin/activity/'


class PanelFixtures:
    """Admin and analyst accounts plus a paid-service builder (same shape as AccountReadProjectionTests)."""

    def setUp(self):
        self.admin = User.objects.create_user(username='panel-admin')
        grant_admin_role(self.admin)
        self.analyst = User.objects.create_user(username='panel-analyst')
        grant_analyst_role(self.analyst)
        self.waiting = RequestStatus.objects.get(code='WAITING_SAMPLE')
        self.paid = PurchaseStatus.objects.get(code='PAID')
        self.now = timezone.now()

    def read_as(self, actor, path):
        client = APIClient()
        if actor is not None:
            client.cookies[settings.AUTH_COOKIE_NAME] = encode_jwt({'sub': str(actor.pk)})
        return client.get(path)

    def paid_service(self, user, code='WAITING_SAMPLE', *, purchased_at=None):
        purchase = Purchase.objects.create(
            owner=user.app_user, status=self.paid, purchased_at=purchased_at or self.now,
        )
        state = RequestStatus.objects.get(code=code)
        service = ServiceRequest.objects.create(
            purchase=purchase, status=state, started_at=self.now,
            completed_at=self.now + timedelta(seconds=1) if code == 'COMPLETED' else None,
        )
        ServiceStatusLog.objects.create(
            request=service, status=self.waiting, actor=self.admin.app_user, changed_at=self.now,
        )
        if code != 'WAITING_SAMPLE':
            ServiceStatusLog.objects.create(
                request=service, status=state, actor=self.admin.app_user,
                changed_at=self.now + timedelta(seconds=2),
            )
        return service

    def assert_admin_only(self, path):
        reception = User.objects.create_user(username='panel-reception')
        grant_reception_role(reception)
        client = User.objects.create_user(username='panel-client')
        self.assertEqual(self.read_as(self.admin, path).status_code, 200)
        for actor in (self.analyst, reception, client):
            with self.subTest(actor=actor.username):
                self.assertEqual(self.read_as(actor, path).status_code, 403)
        # No credential at all: this app answers 403 by design (JWTAuthentication.authenticate_header).
        self.assertEqual(self.read_as(None, path).status_code, 403)


class AdminOverviewTests(PanelFixtures, TestCase):
    def test_overview_permissions(self):
        self.assert_admin_only(OVERVIEW)

    def test_overview_counts(self):
        for name, code in (('done', 'COMPLETED'), ('wait', 'WAITING_SAMPLE'), ('proc', 'PROCESSING')):
            self.paid_service(User.objects.create_user(username=f'ov-{name}'), code)
        unpaid = User.objects.create_user(username='ov-unpaid')
        Purchase.objects.create(owner=unpaid.app_user, status=PurchaseStatus.objects.get(code='PENDING'))
        self.paid_service(User.objects.create_user(username='ov-inactive', is_active=False))

        response = self.read_as(self.admin, OVERVIEW)
        self.assertEqual(response.status_code, 200, response.data)
        data = response.data
        self.assertEqual(set(data), {
            'clients', 'purchases_pending', 'services_open', 'services_completed', 'stages', 'staff', 'generated_at',
        })
        self.assertEqual((data['clients'], data['purchases_pending'], data['services_open'],
                          data['services_completed']), (4, 1, 2, 1))
        self.assertEqual([s['code'] for s in data['stages']],
                         ['WAITING_SAMPLE', 'SAMPLE_RECEIVED', 'PROCESSING', 'COMPLETED'])
        self.assertEqual([s['count'] for s in data['stages']], [1, 0, 1, 1])
        self.assertIn('no-store', response['Cache-Control'])

    def test_overview_oldest_days(self):
        service = self.paid_service(User.objects.create_user(username='ov-old'), 'PROCESSING')
        self.paid_service(User.objects.create_user(username='ov-done'), 'COMPLETED')
        # Shift the whole history so the latest log still matches the service state.
        service.status_history.update(changed_at=F('changed_at') - timedelta(days=9, hours=1))

        stages = {s['code']: s for s in self.read_as(self.admin, OVERVIEW).data['stages']}
        self.assertEqual(stages['PROCESSING']['oldest_days'], 9)
        self.assertIsNone(stages['COMPLETED']['oldest_days'])
        self.assertIsNone(stages['SAMPLE_RECEIVED']['oldest_days'])

    def test_overview_staff_counts(self):
        self.assertEqual(self.read_as(self.admin, OVERVIEW).data['staff'],
                         {'ADMIN': 1, 'ANALISTA': 1, 'RECEPCION': 0})

    def test_overview_empty_database(self):
        data = self.read_as(self.admin, OVERVIEW).data
        self.assertEqual((data['clients'], data['purchases_pending'], data['services_open'],
                          data['services_completed']), (0, 0, 0, 0))
        self.assertEqual([s['count'] for s in data['stages']], [0, 0, 0, 0])

    def test_stats_unchanged(self):
        self.assertEqual(set(self.read_as(self.admin, '/api/admin/stats/').data),
                         {'total_users', 'pending_reports', 'analysis_count', 'last_update'})


class UsersFieldsTests(PanelFixtures, TestCase):
    def test_admin_rows_carry_dates(self):
        client = User.objects.create_user(username='dates-client')
        self.paid_service(client)
        rows = {row['id']: row for row in self.read_as(self.admin, '/api/admin/users/').data}
        self.assertIn('date_joined', rows[client.pk])
        self.assertIsNone(rows[client.pk]['last_login'])
        analyst_rows = self.read_as(self.analyst, '/api/admin/users/').data
        self.assertTrue(analyst_rows)
        self.assertTrue(all(set(row) == {'id', 'service_request_id', 'service_status'} for row in analyst_rows))


class AdminActivityTests(PanelFixtures, TestCase):
    def setUp(self):
        super().setUp()
        self.reception = User.objects.create_user(username='act-reception', first_name='Rosa', last_name='Rec')
        grant_reception_role(self.reception)
        self.client_user = User.objects.create_user(
            username='act-client', email='juan.soto@example.com', first_name='Juan', last_name='Soto')
        Participant.objects.create(user=self.client_user, participant_code='GX-0042')

    def genetic(self, at, subject_id=None, **extra):
        subject_id = subject_id or self.client_user.pk
        log = GeneticDataAccessLog.objects.create(actor_user_id=subject_id, subject_user_id=subject_id,
                                                  resource='results', outcome='granted', **extra)
        GeneticDataAccessLog.objects.filter(pk=log.pk).update(created_at=at)
        return log

    def reception_log(self, at, **extra):
        return ReceptionAccessLog.objects.create(actor=self.reception.app_user, action='search',
                                                 target_user=self.client_user, outcome='1 result(s)',
                                                 created_at=at, **extra)

    def status_log(self, at):
        service = self.paid_service(self.client_user)
        service.status_history.update(changed_at=at)
        return service

    def test_activity_permissions(self):
        self.assert_admin_only(ACTIVITY)

    def test_activity_merges_three_sources_newest_first(self):
        self.status_log(self.now - timedelta(hours=3))
        self.genetic(self.now - timedelta(hours=2))
        self.reception_log(self.now - timedelta(hours=1))
        response = self.read_as(self.admin, ACTIVITY)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual([e['kind'] for e in response.data['events']], ['reception', 'genetic', 'status'])
        event = response.data['events'][0]
        self.assertEqual(set(event), {'id', 'kind', 'at', 'actor', 'subject', 'action', 'outcome'})
        self.assertEqual(event['actor'], {'id': self.reception.pk, 'name': 'Rosa Rec', 'email': '',
                                          'role': 'RECEPCION'})
        self.assertEqual(event['subject'], {'id': self.client_user.pk, 'name': 'Juan Soto',
                                            'email': 'juan.soto@example.com', 'sample_code': 'GX-0042'})
        self.assertEqual(response.data['events'][2]['action'], 'WAITING_SAMPLE')
        self.assertIsNone(response.data['next_before'])
        self.assertIn('no-store', response['Cache-Control'])

    def test_activity_kind_filter(self):
        self.genetic(self.now)
        self.reception_log(self.now)
        kinds = {e['kind'] for e in self.read_as(self.admin, ACTIVITY + '?kind=reception').data['events']}
        self.assertEqual(kinds, {'reception'})
        self.assertEqual(self.read_as(self.admin, ACTIVITY + '?kind=x').status_code, 400)

    def test_activity_q_matches_actor_or_subject(self):
        self.reception_log(self.now)
        self.assertEqual(len(self.read_as(self.admin, ACTIVITY + '?q=SOTO@example').data['events']), 1)
        self.assertEqual(len(self.read_as(self.admin, ACTIVITY + '?q=rosa').data['events']), 1)
        self.assertEqual(self.read_as(self.admin, ACTIVITY + '?q=nadie-coincide').data['events'], [])

    def test_activity_cursor(self):
        for minute in range(55):
            self.reception_log(self.now - timedelta(minutes=minute))
        first = self.read_as(self.admin, ACTIVITY).data
        self.assertEqual(len(first['events']), 50)
        self.assertIsNotNone(first['next_before'])
        second = self.read_as(self.admin, ACTIVITY + '?' + urlencode({'before': first['next_before']})).data
        self.assertEqual(len(second['events']), 5)
        self.assertIsNone(second['next_before'])

    def test_activity_rejects_bad_cursor(self):
        response = self.read_as(self.admin, ACTIVITY + '?before=ayer')
        self.assertEqual(response.status_code, 400)
        self.assertIn('error', response.data)

    def test_activity_deleted_account(self):
        self.genetic(self.now, subject_id=999999)
        event = self.read_as(self.admin, ACTIVITY).data['events'][0]
        self.assertEqual(event['subject']['name'], 'Cuenta eliminada')
        self.assertEqual(event['actor']['name'], 'Cuenta eliminada')

    def test_activity_hides_sensitive_fields(self):
        self.reception_log(self.now, query='GX-TYPED-1')
        self.genetic(self.now, ip='10.0.0.1')
        body = json.dumps(self.read_as(self.admin, ACTIVITY).data, default=str)
        self.assertNotIn('GX-TYPED-1', body)
        self.assertNotIn('10.0.0.1', body)
