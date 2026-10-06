import uuid
from datetime import timedelta
from unittest.mock import patch

from rest_framework.test import APITestCase
from django.contrib.auth.models import Group, User
from django.conf import settings
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from accounts.jwt_utils import encode_jwt
from accounts.models import AppUser, Role
from accounts.roles import grant_admin_role, grant_reception_role
from participants.models import Participant
from profiles.models import Profile
from reception.views import serialize_reception_profile
from services import models as domain
from services.status import ClientStatus, get_service_projections


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
            user=user, defaults={'participant_code': f'reception-{user.pk}'},
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

    def snapshot(self):
        return {model._meta.label: list(model.objects.order_by('pk').values()) for model in (
            Profile, Participant, domain.Purchase, domain.ServiceRequest, domain.ServiceStatusLog, domain.Sample,
        )}

    def expected_payload(self, service_status, *, samples=()):
        return {
            'user_id': self.owner.pk, 'first_name': self.owner.first_name,
            'last_name': self.owner.last_name, 'email': self.owner.email,
            'phone': self.profile.phone, 'rut': self.profile.rut,
            'service_status': service_status, 'service_samples': [self.sample_payload(sample) for sample in samples],
        }

    def assert_projection(self, service_status, *, samples=()):
        before = self.snapshot()
        expected = self.expected_payload(service_status, samples=samples)
        response = self.client.get('/api/reception/search/', {'email': self.owner.email})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data, {'results': [expected]})
        projection = get_service_projections([self.owner.pk], include_samples=True).get(self.owner.pk)
        self.assertEqual(serialize_reception_profile(self.profile, projection), expected)
        self.assertEqual(self.snapshot(), before)

    def assert_sample_search(self, code, expected=(), **filters):
        before = self.snapshot()
        response = self.client.get('/api/reception/search/', {'sample_code': code, **filters})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data, {'results': list(expected)})
        self.assertEqual(self.snapshot(), before)

    def test_paid_waiting_returns_only_operational_samples(self):
        service = self.paid_service()
        sample = self.sample(service, 'PAID-SAMPLE')
        second = self.sample(service, 'SECOND-PAID-SAMPLE', status='stored')
        samples = sorted([sample, second], key=lambda item: (item.created_at, item.pk))
        self.assert_projection(ClientStatus.PENDING, samples=samples)
        expected = [self.expected_payload(ClientStatus.PENDING, samples=samples)]
        for code in (' paid-sample ', 'second-paid-sample'):
            self.assert_sample_search(code, expected)
        for code in ('PAID', 'PAID-SAMPLE-EXTRA'):
            self.assert_sample_search(code)

    def test_client_without_paid_service_is_not_purchased_and_pending_samples_are_hidden(self):
        self.assert_projection(ClientStatus.NO_PURCHASED)
        pending = self.paid_service()
        self.sample(pending, 'PENDING-ONLY-CODE')
        domain.Purchase.objects.filter(pk=pending.purchase_id).update(
            status=domain.PurchaseStatus.objects.get(code='PENDING'), purchased_at=None,
        )
        self.assert_projection(ClientStatus.NO_PURCHASED)
        self.assert_sample_search('PENDING-ONLY-CODE')

    def test_paid_states_project_samples(self):
        for index, code in enumerate(('WAITING_SAMPLE', 'SAMPLE_RECEIVED', 'PROCESSING', 'COMPLETED')):
            with self.subTest(code=code):
                service = self.paid_service(code, paid_at=self.now + timedelta(days=index))
                sample = self.sample(service, f'STATE-{code}')
                expected = ClientStatus.COMPLETED if code == 'COMPLETED' else ClientStatus.PENDING
                self.assert_projection(expected, samples=[sample])
                self.assert_sample_search(sample.sample_code.lower(), [
                    self.expected_payload(expected, samples=[sample]),
                ])

    def test_newest_paid_overrides_older_completed_even_with_older_creation_time(self):
        older = self.paid_service('COMPLETED', paid_at=self.now - timedelta(days=1),
                                  created_at=self.now + timedelta(days=10))
        self.sample(older, 'OLDER-COMPLETED')
        newer = self.paid_service(created_at=self.now - timedelta(days=2))
        sample = self.sample(newer, 'NEWER-WAITING')
        self.assert_projection(ClientStatus.PENDING, samples=[sample])
        self.assert_sample_search('newer-waiting', [self.expected_payload(ClientStatus.PENDING, samples=[sample])])
        self.assert_sample_search('OLDER-COMPLETED')
        self.paid_service('COMPLETED', paid_at=self.now + timedelta(days=1))
        self.assert_projection(ClientStatus.COMPLETED)
        self.assert_sample_search('NEWER-WAITING')

    def test_paid_sample_ranking_breaks_ties_by_creation_and_purchase_uuid(self):
        first = self.paid_service('COMPLETED', created_at=self.now)
        self.sample(first, 'FIRST-TIE')
        later = self.paid_service(created_at=self.now + timedelta(seconds=1))
        sample = self.sample(later, 'LATER-TIE')
        self.assert_projection(ClientStatus.PENDING, samples=[sample])
        self.assert_sample_search('FIRST-TIE')
        self.assert_sample_search('later-tie', [self.expected_payload(ClientStatus.PENDING, samples=[sample])])
        domain.Purchase.objects.create(
            pk=uuid.UUID('ffffffff-ffff-ffff-ffff-ffffffffffff'), owner=self.owner.app_user,
            status=domain.PurchaseStatus.objects.get(code='PAID'), purchased_at=self.now,
            created_at=later.purchase.created_at,
        )
        self.assert_projection(ClientStatus.NO_PURCHASED)
        self.assert_sample_search('LATER-TIE')

    def test_newer_pending_purchase_does_not_shadow_paid_completion(self):
        paid = self.paid_service('COMPLETED')
        sample = self.sample(paid, 'PAID-COMPLETED')
        pending = self.paid_service(paid_at=self.now + timedelta(days=10))
        self.sample(pending, 'PENDING-PURCHASE')
        domain.Purchase.objects.filter(pk=pending.purchase_id).update(
            status=domain.PurchaseStatus.objects.get(code='PENDING'),
        )
        self.assert_projection(ClientStatus.COMPLETED, samples=[sample])
        self.assert_sample_search('paid-completed', [self.expected_payload(ClientStatus.COMPLETED, samples=[sample])])
        self.assert_sample_search('PENDING-PURCHASE')

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

    def test_dirty_sample_and_upstream_ownership_are_filtered_at_read_time(self):
        service = self.paid_service()
        sample = self.sample(service, 'VALID-SAMPLE')
        other = User.objects.create_user(username='dirty-other')
        foreign = Participant.objects.create(user=other, participant_code='dirty-other')
        domain.Sample.objects.bulk_create([domain.Sample(
            service_request=service, participant=foreign, sample_code='DIRTY-BULK', sample_type='blood',
        )])
        self.assert_projection(ClientStatus.PENDING, samples=[sample])
        self.assert_sample_search('DIRTY-BULK')
        self.assert_sample_search('valid-sample', [self.expected_payload(ClientStatus.PENDING, samples=[sample])])
        domain.Sample.objects.filter(pk=sample.pk).update(participant=foreign)
        self.assert_projection(ClientStatus.PENDING)
        self.assert_sample_search('VALID-SAMPLE')
        # Even matching dirty sample/request participants cannot bypass purchase ownership.
        domain.ServiceRequest.objects.filter(pk=service.pk).update(participant=foreign)
        self.assert_projection(ClientStatus.NO_PURCHASED)
        self.assert_sample_search('DIRTY-BULK')
        self.assert_sample_search('VALID-SAMPLE')
        domain.ServiceRequest.objects.filter(pk=service.pk).update(participant_id=service.participant_id)
        domain.Sample.objects.filter(pk=sample.pk).update(participant_id=service.participant_id)
        new_owner = User.objects.create_user(username='dirty-reassigned-owner')
        Participant.objects.filter(pk=service.participant_id).update(user=new_owner)
        self.assert_projection(ClientStatus.NO_PURCHASED)
        self.assert_sample_search('VALID-SAMPLE')
        domain.ServiceRequest.objects.filter(pk=service.pk).update(participant=None)
        self.assert_projection(ClientStatus.PENDING)
        self.assert_sample_search('VALID-SAMPLE')

    def test_paid_sample_search_keeps_combined_filters_as_exact_and_conditions(self):
        sample = self.sample(self.paid_service(), 'COMBINED-PAID-CODE')
        expected = [self.expected_payload(ClientStatus.PENDING, samples=[sample])]
        for filters in ({'rut': self.profile.rut.lower()}, {'email': self.owner.email.upper()},
                        {'email': self.owner.username.upper()},
                        {'rut': f' {self.profile.rut.lower()} ', 'email': f' {self.owner.email.upper()} '}):
            with self.subTest(filters=filters):
                self.assert_sample_search(' combined-paid-code ', expected, **filters)
        for filters in ({'rut': 'wrong-rut'}, {'email': 'other@example.com'},
                        {'rut': self.profile.rut, 'email': 'other@example.com'},
                        {'rut': 'wrong-rut', 'email': self.owner.email}):
            with self.subTest(filters=filters):
                self.assert_sample_search(sample.sample_code, **filters)
        self.assert_sample_search('COMBINED-PAID', rut=self.profile.rut, email=self.owner.email)

    def test_paid_sample_search_requires_an_active_functional_client(self):
        sample = self.sample(self.paid_service(), 'ELIGIBLE-PAID-CODE')
        for role in ('ANALISTA', 'ADMIN', 'RECEPCION'):
            with self.subTest(role=role):
                AppUser.objects.filter(django_user=self.owner).update(role=Role.objects.get(code=role))
                self.assert_sample_search(sample.sample_code)
        AppUser.objects.filter(django_user=self.owner).update(role=Role.objects.get(code='CLIENTE'))
        User.objects.filter(pk=self.owner.pk).update(is_active=False)
        self.assert_sample_search(sample.sample_code)
        User.objects.filter(pk=self.owner.pk).update(is_active=True, is_staff=True, is_superuser=True)
        self.owner.groups.add(Group.objects.get_or_create(name='ADMIN')[0])
        self.assert_sample_search(sample.sample_code, [self.expected_payload(ClientStatus.PENDING, samples=[sample])])

    def test_sample_search_projects_only_candidates_without_the_broad_search_limit(self):
        for index in range(27):
            user = User.objects.create_user(username=f'code-decoy-{index}', email=self.owner.email)
            Profile.objects.create(user=user)
        late = User.objects.create_user(username='late-code-owner', email=self.owner.email)
        late_profile = Profile.objects.create(user=late)
        sample = self.sample(self.paid_service(user=late), 'LATE-PAID-CODE')
        projected_ids = []

        def project(user_ids, **kwargs):
            ids = list(user_ids)
            projected_ids.extend(ids)
            return get_service_projections(ids, **kwargs)

        before = self.snapshot()
        with patch('reception.views.get_service_projections', side_effect=project) as projection, \
                CaptureQueriesContext(connection) as queries:
            response = self.client.get('/api/reception/search/', {'sample_code': 'late-paid-code', 'email': late.email})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual([row['user_id'] for row in response.data['results']], [late.pk])
        self.assertEqual(projected_ids, [late.pk])
        projection.assert_called_once()
        profile_queries = [query['sql'] for query in queries if f'FROM "{Profile._meta.db_table}"' in query['sql']]
        self.assertEqual(len(profile_queries), 1)
        self.assertNotIn('LIMIT 25', profile_queries[0])
        late_projection = get_service_projections([late.pk], include_samples=True)[late.pk]
        self.assertEqual(response.data['results'], [serialize_reception_profile(late_profile, late_projection)])
        self.assertEqual(response.data['results'][0]['service_samples'], [self.sample_payload(sample)])
        self.assertEqual(self.snapshot(), before)

    def test_search_keeps_case_insensitive_combined_filters_and_username_lookup(self):
        sample = self.sample(self.paid_service(), 'CASE-CODE')
        expected = {'results': [self.expected_payload(ClientStatus.PENDING, samples=[sample])]}
        before = self.snapshot()
        for params in ({'rut': self.profile.rut.lower()}, {'email': self.owner.email.upper()},
                       {'email': self.owner.username.upper()}, {'sample_code': 'case-code'},
                       {'rut': self.profile.rut, 'email': self.owner.email, 'sample_code': 'CASE-CODE'}):
            with self.subTest(params=params):
                response = self.client.get('/api/reception/search/', params)
                self.assertEqual(response.status_code, 200, response.data)
                self.assertEqual(response.data, expected)
        for params in ({'rut': self.profile.rut, 'email': 'other@example.com'},
                       {'email': self.owner.email, 'sample_code': 'missing'}):
            self.assertEqual(self.client.get('/api/reception/search/', params).data, {'results': []})
        for filters in ({'email': '  '}, {'sample_code': '  '}, {'rut': ' ', 'email': ' ', 'sample_code': ' '}):
            self.assertEqual(self.client.get('/api/reception/search/', filters).status_code, 400)
        self.assertEqual(self.snapshot(), before)

    def test_search_caps_active_clients_at_25_without_per_profile_queries(self):
        self.sample(self.paid_service(), 'SINGLE-BULK')
        with CaptureQueriesContext(connection) as single:
            response = self.client.get('/api/reception/search/', {'email': self.owner.email})
        self.assertEqual(response.status_code, 200, response.data)
        excluded = User.objects.create_user(username='bulk-inactive', email='bulk@example.com', is_active=False)
        Profile.objects.create(user=excluded)
        analyst = User.objects.create_user(username='bulk-analyst', email='bulk@example.com')
        AppUser.objects.filter(django_user=analyst).update(role=Role.objects.get(code='ANALISTA'))
        Profile.objects.create(user=analyst)
        client_ids = set()
        for index in range(27):
            user = User.objects.create_user(username=f'bulk-client-{index}', email='bulk@example.com')
            Profile.objects.create(user=user)
            if index % 2 == 0:
                self.sample(self.paid_service(user=user), f'BULK-SAMPLE-{index}')
            client_ids.add(user.pk)
        before = self.snapshot()
        with CaptureQueriesContext(connection) as many:
            response = self.client.get('/api/reception/search/', {'email': 'bulk@example.com'})
        self.assertEqual(response.status_code, 200, response.data)
        rows = response.data['results']
        self.assertEqual(len(rows), 25)
        self.assertTrue({row['user_id'] for row in rows} <= client_ids)
        self.assertTrue(all(set(row) == set(self.expected_payload(ClientStatus.PENDING)) for row in rows))
        self.assertTrue(all(len(row['service_samples']) == (row['service_status'] == ClientStatus.PENDING)
                            for row in rows))
        sample_queries = [query['sql'] for query in many.captured_queries if 'FROM "sample"' in query['sql']]
        self.assertEqual(len(sample_queries), 1)
        self.assertNotIn('metadata', sample_queries[0])
        self.assertNotIn('storage_location', sample_queries[0])
        self.assertEqual(len(many), len(single), f'1 profile: {len(single)} queries; 25 profiles: {len(many)}')
        self.assertEqual(self.snapshot(), before)

    def test_search_requires_functional_reception_or_admin_not_flags_or_groups(self):
        flagged = User.objects.create_user(username='flagged-reception', is_staff=True, is_superuser=True)
        flagged.groups.add(Group.objects.get_or_create(name='RECEPCION')[0])
        analyst = User.objects.create_user(username='projection-analyst')
        AppUser.objects.filter(django_user=analyst).update(role=Role.objects.get(code='ANALISTA'))
        unmapped = User.objects.bulk_create([User(username='projection-unmapped')])[0]
        sample = self.sample(self.paid_service(), 'ROLE-PAID-SAMPLE')
        before = self.snapshot()
        for actor in (None, self.owner, flagged, analyst, unmapped):
            with self.subTest(actor=actor):
                self.client.cookies.pop(settings.AUTH_COOKIE_NAME, None)
                if actor is not None:
                    self.client.cookies[settings.AUTH_COOKIE_NAME] = encode_jwt({'sub': str(actor.pk)})
                for filters in ({'email': self.owner.email}, {'sample_code': sample.sample_code}):
                    response = self.client.get('/api/reception/search/', filters)
                    self.assertEqual(response.status_code, 403, response.data)
        admin = User.objects.create_user(username='projection-admin')
        grant_admin_role(admin)
        for actor in (self.receptionist, admin):
            self.client.cookies[settings.AUTH_COOKIE_NAME] = encode_jwt({'sub': str(actor.pk)})
            self.assert_projection(ClientStatus.PENDING, samples=[sample])
            self.assert_sample_search(sample.sample_code, [self.expected_payload(ClientStatus.PENDING, samples=[sample])])
        self.assertEqual(self.snapshot(), before)


class ReceptionTests(APITestCase):
    def test_reception_requires_auth(self):
        """Sin autenticación, los endpoints de recepción deben rechazar."""
        r = self.client.get('/api/reception/search/')
        self.assertIn(r.status_code, (401, 403))

    def test_reception_search_allows_reception(self):
        """Un usuario con rol de recepción puede buscar."""
        user = User.objects.create_user(username='rec', password='x', email='rec@test.com')
        grant_reception_role(user)
        self.client.force_authenticate(user=user)
        r = self.client.get('/api/reception/search/?email=rec@test.com')
        self.assertEqual(r.status_code, 200)

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
                user = User.objects.bulk_create([User(username=username, email=f'{username}@example.com')])[0]
            else:
                user = User.objects.create_user(username=username, email=f'{username}@example.com', **flags)
                AppUser.objects.filter(django_user=user).update(role=Role.objects.get(code=role))
            if group:
                user.groups.add(Group.objects.get_or_create(name=group)[0])
            Profile.objects.create(user=user)
            with self.subTest(username=username):
                response = self.client.get('/api/reception/search/', {'email': user.email})
                self.assertEqual(response.status_code, 200, response.data)
                self.assertEqual([row['user_id'] for row in response.data['results']],
                                 [user.pk] if expected else [])
