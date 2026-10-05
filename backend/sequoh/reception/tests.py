import json
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
from profiles.models import Profile, SampleStatus, ServiceStatus
from profiles.utils import ensure_sample_code
from reception.views import serialize_reception_profile
from services import models as domain


class ReceptionServiceProjectionTests(APITestCase):
    def setUp(self):
        self.now = timezone.now()
        self.receptionist = User.objects.create_user(username='projection-reception')
        grant_reception_role(self.receptionist)
        self.client.cookies[settings.AUTH_COOKIE_NAME] = encode_jwt({'sub': str(self.receptionist.pk)})
        self.owner = User.objects.create_user(username='reception-client', email='client@example.com')
        self.profile = Profile.objects.create(
            user=self.owner, phone='5550100', rut='10000000-K', sample_code='KEEP-CODE',
            service_status=ServiceStatus.COMPLETED, sample_status=SampleStatus.SENT_TO_LAB,
            sample_code_created_at=self.now - timedelta(days=4),
            arrival_confirmed_at=self.now - timedelta(days=3),
            sample_taken_at=self.now - timedelta(days=2), sample_sent_at=self.now - timedelta(days=1),
        )

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

    def expected_payload(self, service_status, *, paid=False, samples=()):
        return {
            'user_id': self.owner.pk, 'first_name': self.owner.first_name,
            'last_name': self.owner.last_name, 'email': self.owner.email,
            'phone': self.profile.phone, 'rut': self.profile.rut,
            'sample_code': None if paid else self.profile.sample_code,
            'sample_status': None if paid else self.profile.sample_status,
            'sample_status_display': '' if paid else SampleStatus(self.profile.sample_status).label,
            'arrival_confirmed_at': None if paid else self.profile.arrival_confirmed_at,
            'sample_taken_at': None if paid else self.profile.sample_taken_at,
            'sample_sent_at': None if paid else self.profile.sample_sent_at,
            'service_status': service_status, 'service_samples': [self.sample_payload(sample) for sample in samples],
        }

    def assert_projection(self, service_status, *, paid=True, samples=()):
        before = self.snapshot()
        expected = self.expected_payload(service_status, paid=paid, samples=samples)
        with patch('reception.views.ensure_sample_code', wraps=ensure_sample_code) as sample_code:
            response = self.client.get('/api/reception/search/', {'email': self.owner.email})
            self.assertEqual(response.status_code, 200, response.data)
            self.assertEqual(response.data, {'results': [expected]})
            self.assertEqual(serialize_reception_profile(self.profile), expected)
            if paid:
                self.assertEqual(serialize_reception_profile(self.profile, service_status=ServiceStatus.COMPLETED),
                                 expected)
                sample_code.assert_not_called()
        self.assertEqual(self.snapshot(), before)

    def test_paid_waiting_returns_only_operational_samples_without_legacy_fallback(self):
        service = self.paid_service()
        sample = self.sample(service, 'PAID-SAMPLE')
        second = self.sample(service, 'SECOND-PAID-SAMPLE', status='stored')
        samples = sorted([sample, second], key=lambda item: (item.created_at, item.pk))
        self.assert_projection(ServiceStatus.PENDING, samples=samples)
        # GDB03c2 will add lookup by service sample code; this slice keeps legacy lookup only.
        self.assertEqual(self.client.get('/api/reception/search/', {'sample_code': sample.sample_code}).data,
                         {'results': []})

    def test_legacy_only_fallback_including_pending_purchase_preserves_contract(self):
        self.assert_projection(ServiceStatus.COMPLETED, paid=False)
        pending = self.paid_service()
        self.sample(pending, 'LEGACY-ONLY-PENDING')
        domain.Purchase.objects.filter(pk=pending.purchase_id).update(
            status=domain.PurchaseStatus.objects.get(code='PENDING'), purchased_at=None,
            created_at=self.now + timedelta(days=10),
        )
        for legacy in ServiceStatus.values:
            with self.subTest(legacy=legacy):
                Profile.objects.filter(pk=self.profile.pk).update(service_status=legacy)
                self.profile.refresh_from_db()
                self.assert_projection(legacy, paid=False)

    def test_paid_states_project_samples_while_hiding_profile_sample_summary(self):
        for index, code in enumerate(('WAITING_SAMPLE', 'SAMPLE_RECEIVED', 'PROCESSING', 'COMPLETED')):
            with self.subTest(code=code):
                service = self.paid_service(code, paid_at=self.now + timedelta(days=index))
                sample = self.sample(service, f'STATE-{code}')
                self.assert_projection(ServiceStatus.COMPLETED if code == 'COMPLETED' else ServiceStatus.PENDING,
                                       samples=[sample])

    def test_newest_paid_overrides_older_completed_even_with_older_creation_time(self):
        older = self.paid_service('COMPLETED', paid_at=self.now - timedelta(days=1),
                                  created_at=self.now + timedelta(days=10))
        self.sample(older, 'OLDER-COMPLETED')
        newer = self.paid_service(created_at=self.now - timedelta(days=2))
        sample = self.sample(newer, 'NEWER-WAITING')
        self.assert_projection(ServiceStatus.PENDING, samples=[sample])
        Profile.objects.filter(pk=self.profile.pk).update(service_status=ServiceStatus.NO_PURCHASED)
        self.profile.refresh_from_db()
        self.paid_service('COMPLETED', paid_at=self.now + timedelta(days=1))
        self.assert_projection(ServiceStatus.COMPLETED)

    def test_paid_sample_ranking_breaks_ties_by_creation_and_purchase_uuid(self):
        first = self.paid_service('COMPLETED', created_at=self.now)
        self.sample(first, 'FIRST-TIE')
        later = self.paid_service(created_at=self.now + timedelta(seconds=1))
        sample = self.sample(later, 'LATER-TIE')
        self.assert_projection(ServiceStatus.PENDING, samples=[sample])
        domain.Purchase.objects.create(
            pk=uuid.UUID('ffffffff-ffff-ffff-ffff-ffffffffffff'), owner=self.owner.app_user,
            status=domain.PurchaseStatus.objects.get(code='PAID'), purchased_at=self.now,
            created_at=later.purchase.created_at,
        )
        self.assert_projection(ServiceStatus.NO_PURCHASED)

    def test_newer_pending_purchase_does_not_shadow_paid_completion(self):
        Profile.objects.filter(pk=self.profile.pk).update(service_status=ServiceStatus.PENDING)
        self.profile.refresh_from_db()
        paid = self.paid_service('COMPLETED')
        sample = self.sample(paid, 'PAID-COMPLETED')
        pending = self.paid_service(paid_at=self.now + timedelta(days=10))
        self.sample(pending, 'PENDING-PURCHASE')
        domain.Purchase.objects.filter(pk=pending.purchase_id).update(
            status=domain.PurchaseStatus.objects.get(code='PENDING'),
        )
        self.assert_projection(ServiceStatus.COMPLETED, samples=[sample])

    def test_malformed_newest_paid_never_falls_back_to_older_completion(self):
        older = self.paid_service('COMPLETED', paid_at=self.now - timedelta(days=1))
        self.sample(older, 'MALFORMED-OLDER')
        Profile.objects.filter(pk=self.profile.pk).update(sample_code=None, sample_code_created_at=None)
        self.profile.refresh_from_db()
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
                self.assert_projection(ServiceStatus.NO_PURCHASED)

    def test_dirty_sample_and_upstream_ownership_are_filtered_at_read_time(self):
        service = self.paid_service()
        sample = self.sample(service, 'VALID-SAMPLE')
        other = User.objects.create_user(username='dirty-other')
        foreign = Participant.objects.create(user=other, participant_code='dirty-other')
        domain.Sample.objects.bulk_create([domain.Sample(
            service_request=service, participant=foreign, sample_code='DIRTY-BULK', sample_type='blood',
        )])
        self.assert_projection(ServiceStatus.PENDING, samples=[sample])
        domain.Sample.objects.filter(pk=sample.pk).update(participant=foreign)
        self.assert_projection(ServiceStatus.PENDING)
        # Even matching dirty sample/request participants cannot bypass purchase ownership.
        domain.ServiceRequest.objects.filter(pk=service.pk).update(participant=foreign)
        self.assert_projection(ServiceStatus.NO_PURCHASED)
        domain.ServiceRequest.objects.filter(pk=service.pk).update(participant_id=service.participant_id)
        domain.Sample.objects.filter(pk=sample.pk).update(participant_id=service.participant_id)
        new_owner = User.objects.create_user(username='dirty-reassigned-owner')
        Participant.objects.filter(pk=service.participant_id).update(user=new_owner)
        self.assert_projection(ServiceStatus.NO_PURCHASED)
        domain.ServiceRequest.objects.filter(pk=service.pk).update(participant=None)
        self.assert_projection(ServiceStatus.PENDING)

    def test_missing_paid_legacy_sample_code_is_never_generated_or_written(self):
        self.paid_service()
        Profile.objects.filter(pk=self.profile.pk).update(sample_code=None, sample_code_created_at=None, sample_status='')
        self.profile.refresh_from_db()
        self.assert_projection(ServiceStatus.PENDING)

    def test_search_keeps_case_insensitive_combined_filters_and_username_lookup(self):
        before = self.snapshot()
        for params in ({'rut': self.profile.rut.lower()}, {'email': self.owner.email.upper()},
                       {'email': self.owner.username.upper()}, {'sample_code': self.profile.sample_code.lower()},
                       {'rut': self.profile.rut, 'email': self.owner.email, 'sample_code': self.profile.sample_code}):
            with self.subTest(params=params):
                response = self.client.get('/api/reception/search/', params)
                self.assertEqual(response.status_code, 200, response.data)
                self.assertEqual(response.data, {'results': [self.expected_payload(ServiceStatus.COMPLETED)]})
        for params in ({'rut': self.profile.rut, 'email': 'other@example.com'},
                       {'email': self.owner.email, 'sample_code': 'missing'}):
            self.assertEqual(self.client.get('/api/reception/search/', params).data, {'results': []})
        self.assertEqual(self.client.get('/api/reception/search/', {'email': '  '}).status_code, 400)
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
            Profile.objects.create(
                user=user, sample_code=f'BULK-{index}',
                service_status=ServiceStatus.COMPLETED if index % 2 == 0 else ServiceStatus.PENDING,
            )
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
        self.assertTrue(all(row['service_status'] == ServiceStatus.PENDING for row in rows))
        self.assertTrue(all(set(row) == set(self.expected_payload(ServiceStatus.PENDING)) for row in rows))
        self.assertTrue(all(len(row['service_samples']) == (1 if row['sample_code'] is None else 0) for row in rows))
        sample_queries = [query['sql'] for query in many.captured_queries if 'FROM "sample"' in query['sql']]
        self.assertEqual(len(sample_queries), 1)
        self.assertNotIn('metadata', sample_queries[0])
        self.assertNotIn('storage_location', sample_queries[0])
        self.assertEqual(len(many), len(single), f'1 profile: {len(single)} queries; 25 profiles: {len(many)}')
        self.assertEqual(self.snapshot(), before)

    def test_missing_legacy_only_sample_code_is_generated_once_without_changing_other_profile_fields(self):
        Profile.objects.filter(pk=self.profile.pk).update(sample_code=None, sample_code_created_at=None, sample_status='')
        before = Profile.objects.filter(pk=self.profile.pk).values().get()
        response = self.client.get('/api/reception/search/', {'email': self.owner.email})
        self.assertEqual(response.status_code, 200, response.data)
        row = response.data['results'][0]
        self.assertTrue(row['sample_code'].startswith(f'SC-{self.owner.pk:05d}-'))
        self.assertEqual(row['sample_status'], SampleStatus.PENDING_COLLECTION)
        self.assertEqual(row['service_status'], ServiceStatus.COMPLETED)
        self.assertEqual(row['service_samples'], [])
        after = Profile.objects.filter(pk=self.profile.pk).values().get()
        self.assertEqual(after['sample_code'], row['sample_code'])
        self.assertIsNotNone(after['sample_code_created_at'])
        for field in ('sample_code', 'sample_code_created_at'):
            before.pop(field)
        self.assertEqual({key: value for key, value in after.items() if key in before}, before)
        self.assertEqual(self.client.get('/api/reception/search/', {'email': self.owner.email}).data['results'][0], row)
        self.assertEqual(Profile.objects.filter(pk=self.profile.pk).values().get(), after)

    def test_legacy_sample_code_response_preserves_existing_fields_only(self):
        before = self.snapshot()
        self.client.cookies['csrftoken'] = 'valid-test-csrf'
        response = self.client.post(
            '/api/reception/sample-code/', data={'userId': self.owner.pk}, format='json',
            HTTP_X_CSRFTOKEN='valid-test-csrf',
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data, {'user': self.expected_payload(ServiceStatus.COMPLETED)})
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
            with self.subTest(actor=actor), patch('reception.views.ensure_sample_code') as sample_code:
                self.client.cookies.pop(settings.AUTH_COOKIE_NAME, None)
                if actor is not None:
                    self.client.cookies[settings.AUTH_COOKIE_NAME] = encode_jwt({'sub': str(actor.pk)})
                response = self.client.get('/api/reception/search/', {'email': self.owner.email})
                self.assertIn(response.status_code, (401, 403))
                sample_code.assert_not_called()
        admin = User.objects.create_user(username='projection-admin')
        grant_admin_role(admin)
        for actor in (self.receptionist, admin):
            self.client.cookies[settings.AUTH_COOKIE_NAME] = encode_jwt({'sub': str(actor.pk)})
            self.assert_projection(ServiceStatus.PENDING, samples=[sample])
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
        )
        for username, flags, role, group, expected in cases:
            if role is None:
                user = User.objects.bulk_create([User(username=username, email=f'{username}@example.com')])[0]
            else:
                user = User.objects.create_user(username=username, email=f'{username}@example.com', **flags)
                AppUser.objects.filter(django_user=user).update(role=Role.objects.get(code=role))
            if group:
                user.groups.add(Group.objects.get_or_create(name=group)[0])
            Profile.objects.create(user=user, sample_code=f'CODE-{username}')
            with self.subTest(username=username):
                response = self.client.get(f'/api/reception/search/?email={username}@example.com')
                self.assertEqual(response.status_code, 200, response.data)
                self.assertEqual([row['user_id'] for row in response.data['results']],
                                 [user.pk] if expected else [])


class ReceptionMutationTargetTests(APITestCase):
    routes = (
        ('/api/reception/arrival/', {}),
        ('/api/reception/sample-code/', {'resend': True}),
        ('/api/reception/sample-status/', {'action': 'mark_taken'}),
    )

    def setUp(self):
        self.now = timezone.now()
        self.receptionist = User.objects.create_user(username='mutation-reception')
        grant_reception_role(self.receptionist)
        self.admin = User.objects.create_user(username='mutation-admin')
        grant_admin_role(self.admin)
        self.client.cookies['csrftoken'] = 'valid-test-csrf'

    def as_actor(self, actor):
        if actor is None:
            self.client.cookies.pop(settings.AUTH_COOKIE_NAME, None)
        else:
            self.client.cookies[settings.AUTH_COOKIE_NAME] = encode_jwt({'sub': str(actor.pk)})

    def target(self, name, role='CLIENTE', group=None, **flags):
        if role is None:
            user = User.objects.bulk_create([User(username=name, **flags)])[0]
        else:
            user = User.objects.create_user(username=name, **flags)
            AppUser.objects.filter(django_user=user).update(role=Role.objects.get(code=role))
        if group:
            user.groups.add(Group.objects.get_or_create(name=group)[0])
        return user, Profile.objects.create(user=user)

    def post_target(self, path, user_id, extra, *, key='userId'):
        self.client.cookies['csrftoken'] = 'valid-test-csrf'
        return self.client.post(
            path, data=json.dumps({key: user_id, **extra}),
            content_type='application/json', HTTP_X_CSRFTOKEN='valid-test-csrf',
        )

    def test_all_mutations_return_uniform_404_without_side_effects_for_nonclients(self):
        cases = (
            ('admin', 'ADMIN', None, {}),
            ('analyst', 'ANALISTA', None, {}),
            ('reception', 'RECEPCION', None, {}),
            ('unmapped', None, None, {}),
            ('legacy-client-only', None, 'CLIENTE', {}),
            ('inactive-client', 'CLIENTE', None, {'is_active': False}),
        )
        for actor in (self.receptionist, self.admin):
            self.as_actor(actor)
            for name, role, group, flags in cases:
                user, profile = self.target(f'{actor.username}-{name}', role, group, **flags)
                profile.sample_code = f'KEEP{user.pk}'
                profile.sample_status = SampleStatus.SENT_TO_LAB
                profile.service_status = ServiceStatus.COMPLETED
                profile.save(update_fields=['sample_code', 'sample_status', 'service_status'])
                before = Profile.objects.filter(pk=profile.pk).values().get()
                for path, extra in self.routes:
                    with self.subTest(actor=actor.username, target=name, path=path), \
                            patch('reception.views.ensure_sample_code') as sample_code, \
                            patch('reception.views.send_email') as send_email:
                        response = self.post_target(path, user.pk, extra)
                        self.assertEqual(response.status_code, 404, response.data)
                        self.assertEqual(response.data, {'error': 'Usuario no encontrado'})
                        sample_code.assert_not_called()
                        send_email.assert_not_called()
                        self.assertEqual(Profile.objects.filter(pk=profile.pk).values().get(), before)

    def test_mapped_clients_including_staff_only_and_legacy_mislabeled_can_mutate(self):
        for actor in (self.receptionist, self.admin):
            self.as_actor(actor)
            for label, flags, group in (
                ('staff-client', {'is_staff': True}, None),
                ('legacy-group-client', {}, 'CLIENTE'),
                ('mislabeled-client', {}, 'ADMIN'),
            ):
                user, profile = self.target(f'{actor.username}-{label}', group=group, **flags)
                with self.subTest(actor=actor.username, target=label):
                    with patch('reception.views.send_email', return_value=True) as send_email:
                        arrival = self.post_target(self.routes[0][0], user.pk, {})
                        self.assertEqual(arrival.status_code, 200, arrival.data)
                        self.assertTrue(arrival.data['user']['sample_code'])
                        profile.refresh_from_db()
                        self.assertIsNotNone(profile.arrival_confirmed_at)
                        self.assertEqual(profile.service_status, ServiceStatus.NO_PURCHASED)

                        code = self.post_target(self.routes[1][0], user.pk, {'resend': True})
                        self.assertEqual(code.status_code, 200, code.data)
                        self.assertEqual(code.data['user']['sample_code'], profile.sample_code)
                        self.assertTrue(code.data['user']['sample_code_sent'])
                        send_email.assert_called_once()

                        taken = self.post_target(self.routes[2][0], user.pk, {'action': 'mark_taken'})
                        self.assertEqual(taken.status_code, 200, taken.data)
                        profile.refresh_from_db()
                        self.assertEqual(profile.sample_status, SampleStatus.COLLECTED_PENDING_ANALYSIS)
                        self.assertIsNotNone(profile.sample_taken_at)

    def snapshot(self):
        return {model._meta.label: list(model.objects.order_by('pk').values()) for model in (
            Profile, domain.Purchase, domain.PurchaseStatus, domain.ServiceRequest,
            domain.ServiceStatus, domain.ServiceStatusLog,
        )}

    def assert_rejected(self, path, user, extra, status_code, *, key='userId', error_key='error'):
        before = self.snapshot()
        with patch('reception.views.ensure_sample_code', wraps=ensure_sample_code) as sample_code, \
                patch('reception.views.send_email') as send_email:
            response = self.post_target(path, user.pk, extra, key=key)
        self.assertEqual(response.status_code, status_code, response.data)
        self.assertIn(error_key, response.data)
        sample_code.assert_not_called()
        send_email.assert_not_called()
        self.assertEqual(self.snapshot(), before)
        return response

    def paid_service(self, user, code):
        purchase = domain.Purchase.objects.create(
            owner=user.app_user, status=domain.PurchaseStatus.objects.get(code='PAID'),
            purchased_at=self.now - timedelta(days=2),
        )
        state = domain.ServiceStatus.objects.get(code=code)
        service = domain.ServiceRequest.objects.create(
            purchase=purchase, status=state, started_at=purchase.purchased_at,
            completed_at=self.now if code == 'COMPLETED' else None,
        )
        for status_code, changed_at in (('WAITING_SAMPLE', purchase.purchased_at), (code, self.now)):
            domain.ServiceStatusLog.objects.create(
                request=service, status=domain.ServiceStatus.objects.get(code=status_code),
                actor=self.admin.app_user, changed_at=changed_at,
            )
        return service

    def test_any_purchase_rejects_user_only_mutations_before_code_profile_or_email(self):
        cases = (('PENDING', ServiceStatus.NO_PURCHASED), ('PAID', ServiceStatus.NO_PURCHASED),
                 ('PENDING', ServiceStatus.PENDING), ('PAID', ServiceStatus.COMPLETED),
                 ('CANCELLED', ServiceStatus.NO_PURCHASED), ('REFUNDED', ServiceStatus.NO_PURCHASED),
                 (None, ServiceStatus.NO_PURCHASED))
        for index, (code, legacy) in enumerate(cases):
            user, profile = self.target(f'purchase-target-{index}')
            Profile.objects.filter(pk=profile.pk).update(service_status=legacy, sample_status='')
            domain.Purchase.objects.create(
                owner=user.app_user, status=domain.PurchaseStatus.objects.get(code=code) if code else None,
                purchased_at=self.now if code == 'PAID' else None,
            )
            for actor in (self.receptionist, self.admin):
                self.as_actor(actor)
                for path, extra in self.routes:
                    with self.subTest(code=code, legacy=legacy, actor=actor.username, path=path):
                        self.assert_rejected(path, user, extra, 409)

    def test_multiple_paid_and_pending_services_reject_both_id_aliases_without_changes(self):
        user, profile = self.target('multi-service-target')
        Profile.objects.filter(pk=profile.pk).update(
            sample_code='KEEP-MULTI', sample_code_created_at=self.now - timedelta(days=4),
            sample_status=SampleStatus.SENT_TO_LAB, service_status=ServiceStatus.COMPLETED,
            arrival_confirmed_at=self.now - timedelta(days=3),
            sample_taken_at=self.now - timedelta(days=2), sample_sent_at=self.now - timedelta(days=1),
            phone='5550100', rut='10000000-K', report_filename='keep.pdf', report_uploaded_at=self.now,
        )
        self.paid_service(user, 'COMPLETED')
        self.paid_service(user, 'WAITING_SAMPLE')
        domain.Purchase.objects.create(
            owner=user.app_user, status=domain.PurchaseStatus.objects.get(code='PENDING'),
        )
        other, _ = self.target('unrelated-service-target')
        self.paid_service(other, 'PROCESSING')
        for actor in (self.receptionist, self.admin):
            self.as_actor(actor)
            for key in ('userId', 'user_id'):
                for path, extra in self.routes:
                    with self.subTest(actor=actor.username, key=key, path=path):
                        self.assert_rejected(path, user, extra, 409, key=key)

    def test_legacy_actions_preserve_service_status_timestamps_and_response_contract(self):
        other, _ = self.target('legacy-unrelated-paid-owner')
        self.paid_service(other, 'PROCESSING')
        cases = [(self.routes[0][0], {}, {'arrival_confirmed_at': self.now}),
                 (self.routes[1][0], {}, {}), (self.routes[1][0], {'resend': True}, {})]
        for action, state, timestamp in (
            (None, SampleStatus.COLLECTED_PENDING_ANALYSIS, 'sample_taken_at'),
            ('mark_taken', SampleStatus.COLLECTED_PENDING_ANALYSIS, 'sample_taken_at'),
            ('taken', SampleStatus.COLLECTED_PENDING_ANALYSIS, 'sample_taken_at'),
            ('sent_lab', SampleStatus.SENT_TO_LAB, 'sample_sent_at'),
            ('sent_to_lab', SampleStatus.SENT_TO_LAB, 'sample_sent_at'),
        ):
            cases.append((self.routes[2][0], {'action': action} if action else {},
                          {'sample_status': state, timestamp: self.now}))
        self.as_actor(self.receptionist)
        for legacy in ServiceStatus.values:
            for existing in (False, True):
                for index, (path, extra, changes) in enumerate(cases):
                    with self.subTest(legacy=legacy, existing=existing, path=path, extra=extra):
                        user, profile = self.target(f'legacy-{legacy}-{existing}-{index}')
                        Profile.objects.filter(pk=profile.pk).update(
                            phone='5550199', rut=f'{user.pk:08d}-K', service_status=legacy,
                            service_updated_at=self.now - timedelta(days=10),
                            sample_code=f'KEEP-{user.pk}' if existing else None,
                            sample_code_created_at=self.now - timedelta(days=4) if existing else None,
                            sample_status=SampleStatus.SENT_TO_LAB if existing else '',
                            arrival_confirmed_at=self.now - timedelta(days=3),
                            sample_taken_at=self.now - timedelta(days=2), sample_sent_at=self.now - timedelta(days=1),
                            report_filename='legacy.pdf', report_uploaded_at=self.now - timedelta(days=5),
                        )
                        before = self.snapshot()
                        expected = {**Profile.objects.filter(pk=profile.pk).values().get(), **changes}
                        with patch('reception.views.timezone.now', return_value=self.now), \
                                patch('reception.views.send_email', return_value=True) as send_email:
                            response = self.post_target(path, user.pk, extra, key='userId' if existing else 'user_id')
                        self.assertEqual(response.status_code, 200, response.data)
                        payload = response.data['user']
                        if not existing:
                            self.assertTrue(payload['sample_code'].startswith(f'SC-{user.pk:05d}-'))
                            expected.update(sample_code=payload['sample_code'], sample_code_created_at=self.now)
                            if path == self.routes[0][0]:
                                expected['sample_status'] = SampleStatus.PENDING_COLLECTION
                        expected_payload = {field: expected[field] for field in (
                            'phone', 'rut', 'sample_code', 'arrival_confirmed_at', 'sample_taken_at',
                            'sample_sent_at', 'service_status',
                        )}
                        sample_status = expected['sample_status'] or SampleStatus.PENDING_COLLECTION
                        expected_payload.update(
                            user_id=user.pk, first_name=user.first_name, last_name=user.last_name, email=user.email,
                            sample_status=sample_status, sample_status_display=SampleStatus(sample_status).label,
                            service_samples=[],
                        )
                        if extra.get('resend'):
                            expected_payload['sample_code_sent'] = True
                            send_email.assert_called_once()
                        else:
                            send_email.assert_not_called()
                        self.assertEqual(response.data, {'user': expected_payload})
                        before[Profile._meta.label] = [expected if row['id'] == profile.pk else row
                                                      for row in before[Profile._meta.label]]
                        self.assertEqual(self.snapshot(), before)

    def test_invalid_legacy_sample_status_is_400_before_sample_code_generation(self):
        self.as_actor(self.admin)
        for existing in (False, True):
            user, profile = self.target(f'invalid-action-{existing}')
            if existing:
                Profile.objects.filter(pk=profile.pk).update(sample_code='KEEP-INVALID')
            for action in ('unsupported', 'receive_sample', 'PROCESSING'):
                with self.subTest(existing=existing, action=action):
                    response = self.assert_rejected(self.routes[2][0], user, {'action': action}, 400)
                    self.assertEqual(response.data, {'error': 'Acción no soportada'})

    def test_all_mutations_require_functional_staff_roles_before_purchase_guard(self):
        legacy, _ = self.target('role-legacy-target')
        purchased, _ = self.target('role-purchase-target')
        domain.Purchase.objects.create(
            owner=purchased.app_user, status=domain.PurchaseStatus.objects.get(code='PENDING'),
        )
        flagged, _ = self.target('mutation-flagged', group='RECEPCION', is_staff=True, is_superuser=True)
        analyst, _ = self.target('mutation-analyst', role='ANALISTA')
        unmapped, _ = self.target('mutation-unmapped', role=None)
        for actor in (None, legacy, flagged, analyst, unmapped):
            self.as_actor(actor)
            for user in (legacy, purchased):
                for path, extra in self.routes:
                    with self.subTest(actor=actor, user=user, path=path):
                        self.assert_rejected(path, user, extra, 403, error_key='detail' if actor is None else 'error')

    def test_csrf_missing_or_mismatched_blocks_legacy_and_purchased_targets(self):
        legacy, _ = self.target('csrf-legacy-target')
        purchased, _ = self.target('csrf-purchase-target')
        domain.Purchase.objects.create(
            owner=purchased.app_user, status=domain.PurchaseStatus.objects.get(code='PENDING'),
        )
        for actor in (self.receptionist, self.admin):
            self.as_actor(actor)
            for user in (legacy, purchased):
                for path, extra in self.routes:
                    for cookie, header in ((None, 'matching'), ('matching', None), ('different', 'matching')):
                        with self.subTest(actor=actor.username, user=user, path=path, cookie=cookie, header=header), \
                                patch('reception.views.ensure_sample_code') as sample_code, \
                                patch('reception.views.send_email') as send_email:
                            self.client.cookies.pop('csrftoken', None)
                            if cookie:
                                self.client.cookies['csrftoken'] = cookie
                            before = self.snapshot()
                            response = self.client.post(
                                path, data=json.dumps({'userId': user.pk, **extra}), content_type='application/json',
                                **({'HTTP_X_CSRFTOKEN': header} if header else {}),
                            )
                            self.assertEqual(response.status_code, 403, response.data)
                            sample_code.assert_not_called()
                            send_email.assert_not_called()
                            self.assertEqual(self.snapshot(), before)
