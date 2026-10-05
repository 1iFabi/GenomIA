import json
from unittest.mock import patch

from rest_framework.test import APITestCase
from django.contrib.auth.models import Group, User
from django.conf import settings
from accounts.jwt_utils import encode_jwt
from accounts.models import AppUser, Role
from accounts.roles import grant_admin_role, grant_reception_role
from profiles.models import Profile, SampleStatus, ServiceStatus


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
        self.receptionist = User.objects.create_user(username='mutation-reception')
        grant_reception_role(self.receptionist)
        self.admin = User.objects.create_user(username='mutation-admin')
        grant_admin_role(self.admin)
        self.client.cookies['csrftoken'] = 'valid-test-csrf'

    def as_actor(self, actor):
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

    def post_target(self, path, user_id, extra):
        self.client.cookies['csrftoken'] = 'valid-test-csrf'
        return self.client.post(
            path, data=json.dumps({'userId': user_id, **extra}),
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
                        self.assertEqual(profile.service_status, ServiceStatus.PENDING)

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
