import json
import uuid
from datetime import timedelta
from unittest.mock import patch

from rest_framework.test import APITestCase
from django.contrib.auth.models import Group, User
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from accounts.jwt_utils import encode_jwt
from accounts.models import AppUser, Role
from accounts.roles import grant_admin_role, grant_reception_role
from participants.models import Participant
from profiles.models import Profile
from reception.models import ReceptionAccessLog
from reception.views import serialize_reception_profile
from services import models as domain
from services.status import ClientStatus, get_service_projections

PERSONAL_FIELDS = {'email', 'phone', 'rut', 'username'}


class ReceptionServiceProjectionTests(APITestCase):
    def setUp(self):
        self.now = timezone.now()
        self.receptionist = User.objects.create_user(username='projection-reception')
        grant_reception_role(self.receptionist)
        self.client.cookies[settings.AUTH_COOKIE_NAME] = encode_jwt({'sub': str(self.receptionist.pk)})
        self.owner = User.objects.create_user(username='reception-client', email='client@example.com')
        self.profile = Profile.objects.create(user=self.owner, phone='5550100', rut='10000000-K')

    def paid_service(self, code='WAITING_SAMPLE', *, user=None, paid_at=None, created_at=None,
                     initial=True, current=True):
        user = user or self.owner
        paid_at = paid_at or self.now
        purchase = domain.Purchase.objects.create(
            owner=user.app_user, status=domain.PurchaseStatus.objects.get(code='PAID'),
            purchased_at=paid_at, created_at=created_at or paid_at,
        )
        state = domain.ServiceStatus.objects.get(code=code)
        participant, _ = Participant.objects.get_or_create(
            user=user, defaults={'participant_code': f'GX-CLIENT{user.pk}'},
        )
        service = domain.ServiceRequest.objects.create(
            purchase=purchase, participant=participant, status=state, started_at=paid_at,
            completed_at=paid_at + timedelta(seconds=1) if code == 'COMPLETED' else None,
        )
        if initial:
            domain.ServiceStatusLog.objects.create(
                request=service, status=domain.ServiceStatus.objects.get(code='WAITING_SAMPLE'),
                actor=self.receptionist.app_user, changed_at=paid_at,
            )
        if current and code != 'WAITING_SAMPLE':
            domain.ServiceStatusLog.objects.create(
                request=service, status=state, actor=self.receptionist.app_user,
                changed_at=paid_at + timedelta(seconds=2),
            )
        return service

    def sample(self, service, code, **values):
        return domain.Sample.objects.create(
            service_request=service, participant_id=service.participant_id,
            sample_code=code, sample_type='saliva', collected_at=self.now, created_at=self.now,
            storage_location='private-storage', metadata={'private': 'not-operational'}, **values,
        )

    def sample_payload(self, sample):
        return {field: getattr(sample, field) for field in (
            'sample_code', 'sample_type', 'status', 'collected_at', 'created_at',
        )}

    def client_code(self, user=None):
        return Participant.objects.filter(user=user or self.owner).values_list('participant_code', flat=True).first()

    def snapshot(self):
        return {model._meta.label: list(model.objects.order_by('pk').values()) for model in (
            Profile, Participant, domain.Purchase, domain.ServiceRequest, domain.ServiceStatusLog, domain.Sample,
        )}

    def expected_payload(self, service_status, *, samples=(), request_status=None):
        return {
            'user_id': self.owner.pk, 'first_name': self.owner.first_name, 'last_name': self.owner.last_name,
            'client_code': self.client_code(), 'service_status': service_status,
            'service_request_status': request_status,
            'service_samples': [self.sample_payload(sample) for sample in samples],
        }

    def search(self, code):
        response = self.client.get('/api/reception/search/', {'sample_code': code})
        self.assertEqual(response.status_code, 200, response.data)
        return response.data['results']

    def assert_projection(self, service_status, *, samples=(), request_status=None):
        expected = self.expected_payload(service_status, samples=samples, request_status=request_status)
        projection = get_service_projections([self.owner.pk], include_samples=True).get(self.owner.pk)
        self.assertEqual(serialize_reception_profile(self.profile, projection, self.client_code()), expected)
        if self.client_code():
            before = self.snapshot()
            self.assertEqual(self.search(self.client_code()), [expected])
            self.assertEqual(self.snapshot(), before)

    def assert_sample_search(self, code, expected=()):
        before = self.snapshot()
        self.assertEqual(self.search(code), list(expected))
        self.assertEqual(self.snapshot(), before)

    def test_paid_waiting_returns_only_operational_samples_and_no_personal_data(self):
        service = self.paid_service()
        sample = self.sample(service, 'PAID-SAMPLE')
        second = self.sample(service, 'SECOND-PAID-SAMPLE', status='stored')
        samples = sorted([sample, second], key=lambda item: (item.created_at, item.pk))
        self.assert_projection(ClientStatus.PENDING, samples=samples, request_status='WAITING_SAMPLE')
        expected = [self.expected_payload(ClientStatus.PENDING, samples=samples, request_status='WAITING_SAMPLE')]
        for code in (' paid-sample ', 'second-paid-sample'):
            self.assert_sample_search(code, expected)
        for code in ('PAID', 'PAID-SAMPLE-EXTRA'):
            self.assert_sample_search(code)
        self.assertTrue(PERSONAL_FIELDS.isdisjoint(self.search('PAID-SAMPLE')[0]))

    def test_client_without_purchase_is_found_by_client_code_only(self):
        self.assert_sample_search('GX-NOT-ISSUED')
        Participant.objects.create(user=self.owner, participant_code='GX-WELCOME1')
        self.assert_projection(ClientStatus.NO_PURCHASED)
        self.assertEqual(self.search('gx-welcome1'), [self.expected_payload(ClientStatus.NO_PURCHASED)])

    def test_pending_purchase_samples_are_hidden(self):
        pending = self.paid_service()
        self.sample(pending, 'PENDING-ONLY-CODE')
        domain.Purchase.objects.filter(pk=pending.purchase_id).update(
            status=domain.PurchaseStatus.objects.get(code='PENDING'), purchased_at=None,
        )
        self.assert_projection(ClientStatus.NO_PURCHASED)
        self.assert_sample_search('PENDING-ONLY-CODE')

    def test_paid_states_project_samples_and_detailed_status(self):
        for index, code in enumerate(('WAITING_SAMPLE', 'SAMPLE_RECEIVED', 'PROCESSING', 'COMPLETED')):
            with self.subTest(code=code):
                service = self.paid_service(code, paid_at=self.now + timedelta(days=index))
                sample = self.sample(service, f'STATE-{code}')
                expected = ClientStatus.COMPLETED if code == 'COMPLETED' else ClientStatus.PENDING
                self.assert_projection(expected, samples=[sample], request_status=code)
                self.assert_sample_search(sample.sample_code.lower(), [
                    self.expected_payload(expected, samples=[sample], request_status=code),
                ])

    def test_newest_paid_overrides_older_completed_even_with_older_creation_time(self):
        older = self.paid_service('COMPLETED', paid_at=self.now - timedelta(days=1),
                                  created_at=self.now + timedelta(days=10))
        self.sample(older, 'OLDER-COMPLETED')
        newer = self.paid_service(created_at=self.now - timedelta(days=2))
        sample = self.sample(newer, 'NEWER-WAITING')
        self.assert_projection(ClientStatus.PENDING, samples=[sample], request_status='WAITING_SAMPLE')
        self.assert_sample_search('OLDER-COMPLETED')
        self.paid_service('COMPLETED', paid_at=self.now + timedelta(days=1))
        self.assert_projection(ClientStatus.COMPLETED, request_status='COMPLETED')
        self.assert_sample_search('NEWER-WAITING')

    def test_paid_sample_ranking_breaks_ties_by_creation_and_purchase_uuid(self):
        first = self.paid_service('COMPLETED', created_at=self.now)
        self.sample(first, 'FIRST-TIE')
        later = self.paid_service(created_at=self.now + timedelta(seconds=1))
        sample = self.sample(later, 'LATER-TIE')
        self.assert_projection(ClientStatus.PENDING, samples=[sample], request_status='WAITING_SAMPLE')
        self.assert_sample_search('FIRST-TIE')
        domain.Purchase.objects.create(
            pk=uuid.UUID('ffffffff-ffff-ffff-ffff-ffffffffffff'), owner=self.owner.app_user,
            status=domain.PurchaseStatus.objects.get(code='PAID'), purchased_at=self.now,
            created_at=later.purchase.created_at,
        )
        self.assert_projection(ClientStatus.NO_PURCHASED)
        self.assert_sample_search('LATER-TIE')

    def test_malformed_newest_paid_never_falls_back_to_older_completion(self):
        older = self.paid_service('COMPLETED', paid_at=self.now - timedelta(days=1))
        self.sample(older, 'MALFORMED-OLDER')
        other = User.objects.create_user(username='projection-other')
        participant = Participant.objects.create(user=other, participant_code='reception-other')
        defects = ('missing_request', 'missing_initial', 'missing_current', 'history_mismatch',
                   'missing_completion', 'wrong_participant', 'missing_payment_time')
        for index, defect in enumerate(defects, 1):
            with self.subTest(defect=defect):
                paid_at = self.now + timedelta(days=index)
                if defect == 'missing_request':
                    domain.Purchase.objects.create(
                        owner=self.owner.app_user, status=domain.PurchaseStatus.objects.get(code='PAID'),
                        purchased_at=paid_at,
                    )
                else:
                    service = self.paid_service(
                        'COMPLETED' if defect in ('missing_current', 'missing_completion') else 'PROCESSING',
                        paid_at=paid_at, initial=defect != 'missing_initial', current=defect != 'missing_current',
                    )
                    self.sample(service, f'MALFORMED-{defect}')
                    if defect == 'history_mismatch':
                        domain.ServiceStatusLog.objects.create(
                            request=service, status=domain.ServiceStatus.objects.get(code='WAITING_SAMPLE'),
                            actor=self.receptionist.app_user, changed_at=paid_at + timedelta(seconds=3),
                        )
                    elif defect == 'missing_completion':
                        domain.ServiceRequest.objects.filter(pk=service.pk).update(completed_at=None)
                    elif defect == 'wrong_participant':
                        domain.ServiceRequest.objects.filter(pk=service.pk).update(participant=participant)
                    elif defect == 'missing_payment_time':
                        domain.Purchase.objects.filter(pk=service.purchase_id).update(purchased_at=None)
                self.assert_projection(ClientStatus.NO_PURCHASED)
                self.assert_sample_search('MALFORMED-OLDER')
                self.assert_sample_search(f'MALFORMED-{defect}')

    def test_dirty_sample_ownership_is_filtered_at_read_time(self):
        service = self.paid_service()
        sample = self.sample(service, 'VALID-SAMPLE')
        other = User.objects.create_user(username='dirty-other')
        foreign = Participant.objects.create(user=other, participant_code='dirty-other')
        domain.Sample.objects.bulk_create([domain.Sample(
            service_request=service, participant=foreign, sample_code='DIRTY-BULK', sample_type='blood',
        )])
        self.assert_projection(ClientStatus.PENDING, samples=[sample], request_status='WAITING_SAMPLE')
        self.assert_sample_search('DIRTY-BULK')
        domain.Sample.objects.filter(pk=sample.pk).update(participant=foreign)
        self.assert_projection(ClientStatus.PENDING, request_status='WAITING_SAMPLE')
        self.assert_sample_search('VALID-SAMPLE')

    def test_search_requires_an_active_functional_client(self):
        sample = self.sample(self.paid_service(), 'ELIGIBLE-PAID-CODE')
        for role in ('ANALISTA', 'ADMIN', 'RECEPCION'):
            with self.subTest(role=role):
                AppUser.objects.filter(django_user=self.owner).update(role=Role.objects.get(code=role))
                self.assert_sample_search(sample.sample_code)
                self.assert_sample_search(self.client_code())
        AppUser.objects.filter(django_user=self.owner).update(role=Role.objects.get(code='CLIENTE'))
        User.objects.filter(pk=self.owner.pk).update(is_active=False)
        self.assert_sample_search(sample.sample_code)
        User.objects.filter(pk=self.owner.pk).update(is_active=True, is_staff=True, is_superuser=True)
        self.assertEqual([row['user_id'] for row in self.search(sample.sample_code)], [self.owner.pk])

    def test_only_sample_code_is_accepted(self):
        self.paid_service()
        for params in ({}, {'email': self.owner.email}, {'rut': self.profile.rut}, {'sample_code': '  '}):
            with self.subTest(params=params):
                self.assertEqual(self.client.get('/api/reception/search/', params).status_code, 400)

    def test_search_requires_functional_reception_or_admin_not_flags_or_groups(self):
        flagged = User.objects.create_user(username='flagged-reception', is_staff=True, is_superuser=True)
        flagged.groups.add(Group.objects.get_or_create(name='RECEPCION')[0])
        analyst = User.objects.create_user(username='projection-analyst')
        AppUser.objects.filter(django_user=analyst).update(role=Role.objects.get(code='ANALISTA'))
        unmapped = User.objects.bulk_create([User(username='projection-unmapped')])[0]
        sample = self.sample(self.paid_service(), 'ROLE-PAID-SAMPLE')
        for actor in (None, self.owner, flagged, analyst, unmapped):
            with self.subTest(actor=actor):
                self.client.cookies.pop(settings.AUTH_COOKIE_NAME, None)
                if actor is not None:
                    self.client.cookies[settings.AUTH_COOKIE_NAME] = encode_jwt({'sub': str(actor.pk)})
                response = self.client.get('/api/reception/search/', {'sample_code': sample.sample_code})
                self.assertIn(response.status_code, (401, 403), response.data)
        self.assertFalse(ReceptionAccessLog.objects.exists())
        admin = User.objects.create_user(username='projection-admin')
        grant_admin_role(admin)
        for actor in (self.receptionist, admin):
            self.client.cookies[settings.AUTH_COOKIE_NAME] = encode_jwt({'sub': str(actor.pk)})
            self.assert_sample_search(sample.sample_code, [
                self.expected_payload(ClientStatus.PENDING, samples=[sample], request_status='WAITING_SAMPLE'),
            ])

    def test_every_search_is_audited_without_personal_data(self):
        sample = self.sample(self.paid_service(), 'AUDITED-CODE')
        self.search(sample.sample_code)
        self.search('UNKNOWN-CODE')
        logs = list(ReceptionAccessLog.objects.order_by('created_at', 'pk').values(
            'actor__django_user_id', 'action', 'query', 'target_user_id', 'outcome'))
        self.assertEqual(logs, [
            {'actor__django_user_id': self.receptionist.pk, 'action': 'search', 'query': 'AUDITED-CODE',
             'target_user_id': self.owner.pk, 'outcome': '1 result(s)'},
            {'actor__django_user_id': self.receptionist.pk, 'action': 'search', 'query': 'UNKNOWN-CODE',
             'target_user_id': None, 'outcome': '0 result(s)'},
        ])


class ReceptionVerifyRutTests(APITestCase):
    def setUp(self):
        cache.clear()  # Throttle counters live in the cache.
        self.receptionist = User.objects.create_user(username='rut-reception')
        grant_reception_role(self.receptionist)
        self.owner = User.objects.create_user(username='rut-client')
        Profile.objects.create(user=self.owner, rut='12345678-K')
        self.as_actor(self.receptionist)

    def as_actor(self, user):
        self.client.cookies[settings.AUTH_COOKIE_NAME] = encode_jwt({'sub': str(user.pk)})
        self.client.cookies['csrftoken'] = 'matching-csrf'

    def verify(self, rut, user_id=None, csrf='matching-csrf'):
        self.client.cookies['csrftoken'] = 'matching-csrf'
        return self.client.post('/api/reception/verify-rut/', data=json.dumps({'userId': user_id or self.owner.pk,
                                                                             'rut': rut}),
                                content_type='application/json', HTTP_X_CSRFTOKEN=csrf)

    def test_answers_only_match_or_no_match_and_audits_without_the_rut(self):
        for rut, matches in (('12345678-K', True), ('12.345.678-k', True), ('12345678-9', False)):
            with self.subTest(rut=rut):
                response = self.verify(rut)
                self.assertEqual(response.status_code, 200, response.data)
                self.assertEqual(response.data, {'matches': matches})
        logs = list(ReceptionAccessLog.objects.values_list('action', 'target_user_id', 'outcome', 'query'))
        self.assertEqual(sorted(logs), sorted([('verify_rut', self.owner.pk, 'match', '')] * 2
                                              + [('verify_rut', self.owner.pk, 'no_match', '')]))

    def test_rejects_bad_input_unknown_clients_roles_and_csrf(self):
        self.assertEqual(self.verify('not-a-rut').status_code, 400)
        self.assertEqual(self.verify('12345678-K', user_id=999999).status_code, 404)
        staff = User.objects.create_user(username='rut-staff-target')
        grant_reception_role(staff)
        Profile.objects.create(user=staff, rut='11111111-1')
        self.assertEqual(self.verify('11111111-1', user_id=staff.pk).status_code, 404)
        self.assertEqual(self.verify('12345678-K', csrf='forged').status_code, 403)
        self.as_actor(self.owner)
        self.assertEqual(self.verify('12345678-K').status_code, 403)
        self.assertFalse(ReceptionAccessLog.objects.exists())

    def test_client_without_rut_never_matches(self):
        Profile.objects.filter(user=self.owner).update(rut=None)
        self.assertEqual(self.verify('12345678-K').data, {'matches': False})

    def test_guessing_is_rate_limited(self):
        statuses = [self.verify('12345678-9').status_code for _ in range(31)]
        self.assertEqual(statuses[:30], [200] * 30)
        self.assertEqual(statuses[30], 429)


class ReceptionTests(APITestCase):
    def test_reception_requires_auth(self):
        """Sin autenticación, los endpoints de recepción deben rechazar."""
        r = self.client.get('/api/reception/search/', {'sample_code': 'X'})
        self.assertIn(r.status_code, (401, 403))

    def test_search_returns_only_mapped_clients_regardless_of_django_flags_or_groups(self):
        receptionist = User.objects.create_user(username='receptionist')
        grant_reception_role(receptionist)
        self.client.cookies[settings.AUTH_COOKIE_NAME] = encode_jwt({'sub': str(receptionist.pk)})
        cases = (
            ('staff-client', {'is_staff': True}, 'CLIENTE', 'ADMIN', True),
            ('super-client', {'is_superuser': True}, 'CLIENTE', 'ANALISTA', True),
            ('analyst', {}, 'ANALISTA', None, False),
            ('admin', {}, 'ADMIN', None, False),
            ('other-reception', {}, 'RECEPCION', None, False),
            ('unmapped', {}, None, 'CLIENTE', False),
            ('inactive-client', {'is_active': False}, 'CLIENTE', None, False),
        )
        for username, flags, role, group, expected in cases:
            if role is None:
                user = User.objects.bulk_create([User(username=username)])[0]
            else:
                user = User.objects.create_user(username=username, **flags)
                AppUser.objects.filter(django_user=user).update(role=Role.objects.get(code=role))
            if group:
                user.groups.add(Group.objects.get_or_create(name=group)[0])
            Profile.objects.create(user=user)
            Participant.objects.create(user=user, participant_code=f'GX-{username}')
            with self.subTest(username=username):
                response = self.client.get('/api/reception/search/', {'sample_code': f'gx-{username}'})
                self.assertEqual(response.status_code, 200, response.data)
                self.assertEqual([row['user_id'] for row in response.data['results']],
                                 [user.pk] if expected else [])
