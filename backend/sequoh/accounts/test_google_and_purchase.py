from datetime import date
import json
import time
from unittest.mock import patch

from allauth.account.models import EmailAddress
from django.conf import settings
from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from accounts.jwt_utils import encode_jwt
from accounts.models import AppUser
from accounts.roles import grant_reception_role
from participants.models import Participant
from profiles.models import Profile, normalize_rut

CLAIMS = {'sub': 'google-sub-1', 'email': 'Ana@Gmail.com', 'email_verified': True,
          'given_name': 'Ana', 'family_name': 'Pérez'}


@override_settings(GOOGLE_CLIENT_ID='test-client-id')
@patch('accounts.google_auth.send_welcome_email', return_value=True)
class GoogleSignInTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()

    def google(self, claims=CLAIMS, **body):
        with patch('accounts.google_auth.google_id_token.verify_oauth2_token', return_value=dict(claims)) as verify:
            response = self.client.post('/api/auth/google/', {'credential': 'id-token', **body}, format='json')
        return response, verify

    def complete(self, pending, username='ana.g', terminos=True):
        return self.client.post('/api/auth/google/complete/',
                                {'pending': pending, 'username': username, 'terminos': terminos}, format='json')

    def test_new_user_picks_username_then_logs_in_with_google(self, _welcome):
        response, verify = self.google()
        self.assertEqual(verify.call_args.args[2], 'test-client-id')  # aud checked against our client.
        self.assertTrue(response.data['needs_username'])
        self.assertFalse(User.objects.exists())  # Nothing stored before the username step.

        response = self.complete(response.data['pending'])
        self.assertEqual(response.status_code, 201, response.data)
        self.assertIn(settings.AUTH_COOKIE_NAME, response.cookies)
        user = User.objects.get(username='ana.g')
        self.assertEqual((user.email, user.first_name, user.last_name), ('ana@gmail.com', 'Ana', 'Pérez'))
        self.assertFalse(user.has_usable_password())
        self.assertIsNotNone(user.last_login)
        self.assertTrue(EmailAddress.objects.get(user=user).verified)
        mapping = AppUser.objects.get(django_user=user)
        self.assertEqual((mapping.role.code, mapping.oidc_subject), ('CLIENTE', 'google-sub-1'))
        self.assertFalse(Profile.objects.exists())
        self.assertFalse(Participant.objects.exists())

        self.client.cookies.clear()
        response, _ = self.google({**CLAIMS, 'email': 'changed@gmail.com'})  # Matched by sub, not email.
        self.assertEqual(response.status_code, 200)
        self.assertIn(settings.AUTH_COOKIE_NAME, response.cookies)

    def test_rejects_unverified_email_and_bad_tokens(self, _welcome):
        response, _ = self.google({**CLAIMS, 'email_verified': False})
        self.assertEqual(response.status_code, 400)
        with patch('accounts.google_auth.google_id_token.verify_oauth2_token', side_effect=ValueError('bad aud')):
            response = self.client.post('/api/auth/google/', {'credential': 'forged'}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.complete('tampered').status_code, 400)

    def test_existing_password_account_is_not_merged(self, _welcome):
        User.objects.create_user(username='local', email='ana@gmail.com', password='Secret-pass-1!')
        response, _ = self.google()
        self.assertEqual(response.status_code, 409)
        self.assertTrue(response.data['email_exists'])
        self.assertFalse(AppUser.objects.filter(oidc_subject='google-sub-1').exists())

    def test_sign_up_does_not_log_in_an_already_linked_account(self, _welcome):
        self.complete(self.google()[0].data['pending'])
        self.client.cookies.clear()

        response, _ = self.google(intent='signup')

        self.assertEqual(response.status_code, 409)
        self.assertTrue(response.data['email_exists'])
        self.assertNotIn(settings.AUTH_COOKIE_NAME, response.cookies)

    def test_google_only_user_deletes_account_with_fresh_google_reauth(self, _welcome):
        self.complete(self.google()[0].data['pending'])
        user = User.objects.get(username='ana.g')
        self.client.cookies['csrftoken'] = 'csrf'

        def delete(claims):
            self.client.cookies['csrftoken'] = 'csrf'
            with patch('accounts.google_auth.google_id_token.verify_oauth2_token', return_value=claims):
                return self.client.delete('/api/auth/me/delete-account/',
                                          data=json.dumps({'confirmation': 'ELIMINAR', 'googleCredential': 't'}),
                                          content_type='application/json', HTTP_X_CSRFTOKEN='csrf')

        now = int(time.time())
        for claims in ({**CLAIMS, 'iat': now - 600}, {**CLAIMS, 'sub': 'someone-else', 'iat': now}):
            response = delete(claims)
            self.assertEqual(response.status_code, 400)
            self.assertTrue(response.data['requires_google_reauth'])
        self.assertEqual(delete({**CLAIMS, 'iat': now}).status_code, 200)
        self.assertFalse(User.objects.filter(pk=user.pk).exists())

    def test_username_and_terms_are_validated(self, _welcome):
        pending = self.google()[0].data['pending']
        User.objects.create_user(username='taken')
        self.assertEqual(self.complete(pending, username='TAKEN').status_code, 400)
        self.assertEqual(self.complete(pending, terminos=False).status_code, 400)
        self.assertEqual(self.complete(pending, username='a!').status_code, 400)
        self.assertEqual(User.objects.count(), 1)


@patch('accounts.views.send_client_code_email', return_value=True)
class PurchaseProfileTests(TestCase):
    URL = '/api/auth/me/purchase-profile/'
    PAYLOAD = {'nombre': 'Ana', 'apellido': 'Pérez', 'rut': '12.345.678-5', 'telefono': '912345678',
               'sexoAlNacer': 'female', 'anioNacimiento': 1990}

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.user = User.objects.create_user(username='buyer', email='buyer@example.com')
        self.login(self.user)

    def login(self, user):
        self.client.cookies[settings.AUTH_COOKIE_NAME] = encode_jwt({'sub': str(user.pk)})
        self.client.cookies['csrftoken'] = 'csrf'

    def post(self, **changes):
        cache.clear()  # Each call counts against the 'register' throttle.
        self.client.cookies['csrftoken'] = 'csrf'  # Responses may rotate the CSRF cookie.
        return self.client.post(self.URL, data=json.dumps({**self.PAYLOAD, **changes}),
                                content_type='application/json', HTTP_X_CSRFTOKEN='csrf')

    def test_rut_check_digit(self, _send_code):
        self.assertEqual(normalize_rut('12.345.678-5'), '12345678-5')
        self.assertEqual(normalize_rut('7654321-6'), '7654321-6')
        self.assertIsNone(normalize_rut('12345678-K'))
        self.assertIsNone(normalize_rut('abc'))

    def test_stores_purchase_identity_and_issues_client_code(self, send_code):
        response = self.post()
        self.assertEqual(response.status_code, 201, response.data)
        profile = Profile.objects.get(user=self.user)
        self.assertEqual((profile.rut, profile.phone), ('12345678-5', '+56912345678'))
        participant = Participant.objects.get(user=self.user)
        self.assertEqual(response.data['clientCode'], participant.participant_code)
        self.assertEqual((participant.sex_at_birth, participant.birth_year), ('female', 1990))
        self.user.refresh_from_db()
        self.assertEqual((self.user.first_name, self.user.last_name), ('Ana', 'Pérez'))
        send_code.assert_called_once_with(self.user, participant.participant_code)
        me = self.client.get('/api/auth/me/').data['user']
        self.assertTrue(me['purchase_profile_complete'])
        self.assertEqual(self.post().status_code, 409)  # RUT is set once.

    def test_rejects_invalid_or_duplicate_data(self, _send_code):
        for changes in ({'rut': '12345678-K'}, {'telefono': '123'}, {'sexoAlNacer': 'x'},
                        {'anioNacimiento': 1800}, {'anioNacimiento': '1990'},
                        {'anioNacimiento': date.today().year + 1}, {'nombre': ''},
                        {'nombre': 'A' * 31}, {'apellido': 'B' * 31}):
            with self.subTest(changes=changes):
                response = self.post(**changes)
                self.assertEqual(response.status_code, 400, response.data)
        other = User.objects.create_user(username='other')
        Profile.objects.create(user=other, rut='12345678-5')
        self.assertTrue(self.post().data['rut_exists'])
        self.assertFalse(Participant.objects.filter(user=self.user).exists())

    def test_accepts_other_sex_and_thirty_character_names(self, _send_code):
        response = self.post(sexoAlNacer='other', nombre='A' * 30, apellido='González Pérez')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(Participant.objects.get(user=self.user).sex_at_birth, 'other')

    def test_staff_cannot_submit_purchase_data(self, _send_code):
        staff = User.objects.create_user(username='desk')
        grant_reception_role(staff)
        self.login(staff)
        self.assertEqual(self.post().status_code, 403)
