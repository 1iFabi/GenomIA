import json
from datetime import timedelta
from importlib import import_module
from types import SimpleNamespace
from django.utils import timezone
from unittest.mock import patch

from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, User
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.test.utils import CaptureQueriesContext
from django.db.migrations.loader import MigrationLoader
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse
import uuid
from rest_framework.test import APIClient

from .jwt_utils import encode_jwt, decode_jwt
from .models import AppUser, RevokedToken, Role
from .signals import assign_new_user_client_role
from .roles import (
    grant_admin_role, grant_analyst_role, grant_reception_role,
    is_admin, is_analyst, is_reception, revoke_analyst_role, revoke_reception_role,
)
from profiles.models import Profile
from participants.models import Participant
from services.models import Purchase, PurchaseStatus, ServiceRequest, ServiceStatus as RequestStatus, ServiceStatusLog


@override_settings(REQUIRE_EMAIL_VERIFICATION=False)
class AuthHttpOnlyCookieTests(TestCase):
    """Verifica el flujo auth JWT en cookie HttpOnly + blacklist (Opción B)."""

    def setUp(self):
        self.client = APIClient()
        self.username = "user@example.com"
        self.password = "SuperSecret123!"
        self.user = User.objects.create_user(
            username=self.username, email=self.username, password=self.password, is_active=True
        )
        self.cookie_name = getattr(settings, 'AUTH_COOKIE_NAME', 'access_token')

    def _login(self, username=None, password=None, remember=False):
        return self.client.post(
            "/api/auth/login/",
            data=json.dumps({
                "username": self.username if username is None else username,
                "password": self.password if password is None else password,
                "remember": remember,
            }),
            content_type="application/json",
        )

    def test_login_replaces_expired_auth_cookie(self):
        expired_token = encode_jwt({"sub": str(self.user.id), "email": self.username}, ttl_seconds=-1)
        self.client.cookies[self.cookie_name] = expired_token

        resp = self._login()

        self.assertEqual(resp.status_code, 200)
        replacement_cookie = resp.cookies.get(self.cookie_name)
        self.assertIsNotNone(replacement_cookie)
        self.assertNotEqual(replacement_cookie.value, expired_token)

    def test_login_sets_httponly_cookie_and_no_token_body(self):
        resp = self._login()
        self.assertEqual(resp.status_code, 200)
        cookie = resp.cookies.get(self.cookie_name)
        self.assertIsNotNone(cookie, "login debe setear la cookie de sesión")
        self.assertTrue(
            str(cookie.get('httponly')).lower() == 'true',
            "la cookie debe ser HttpOnly (ilegible por JS)",
        )
        # El token no debe estar expuesto en el body JSON.
        self.assertNotIn('token', resp.data)

    def test_remember_true_sets_max_age(self):
        self.client.cookies.clear()
        resp = self._login(remember=True)
        cookie = resp.cookies.get(self.cookie_name)
        self.assertIsNotNone(cookie)
        self.assertIsNotNone(cookie.get('max-age'), "remember=true debe persistir (Max-Age)")
        self.assertTrue(int(float(cookie['max-age'])) >= 8 * 3600)

    def test_remember_false_session_cookie(self):
        self.client.cookies.clear()
        resp = self._login(remember=False)
        cookie = resp.cookies.get(self.cookie_name)
        self.assertIsNotNone(cookie)
        self.assertIn(cookie.get('max-age'), (None, ''), "remember=false = cookie de sesión (sin Max-Age)")

    def test_inactive_user_is_rejected(self):
        self._login()
        self.user.is_active = False
        self.user.save()
        resp = self.client.get("/api/auth/me/")
        self.assertIn(resp.status_code, (401, 403))

    def test_sub_non_integer_returns_401_not_500(self):
        token = encode_jwt({"sub": "abc", "email": self.username})
        self.client.cookies[self.cookie_name] = token
        resp = self.client.get("/api/auth/me/")
        self.assertNotEqual(resp.status_code, 500)
        self.assertIn(resp.status_code, (401, 403))

    def test_logout_revokes_token_and_rejects(self):
        resp = self._login()
        self.assertEqual(resp.status_code, 200)
        token = resp.cookies.get(self.cookie_name).value
        jti = decode_jwt(token)['jti']

        self.client.cookies[self.cookie_name] = token
        self.client.get("/api/auth/csrf/")
        csrf_cookie = self.client.cookies.get('csrftoken')
        self.assertIsNotNone(csrf_cookie)
        logout = self.client.post(
            "/api/auth/logout/",
            HTTP_X_CSRFTOKEN=csrf_cookie.value,
        )
        self.assertEqual(logout.status_code, 200)
        self.assertTrue(RevokedToken.objects.filter(jti=jti).exists(), "el jti debe quedar en la blacklist")

        me = self.client.get("/api/auth/me/")
        self.assertIn(me.status_code, (401, 403))

    def test_decode_with_other_key_fails(self):
        token = encode_jwt({"sub": str(self.user.id), "email": self.username})
        with override_settings(JWT_SECRET_KEY="otra-clave-distinta"):
            with self.assertRaises(Exception):
                decode_jwt(token)

    def test_token_ttl_about_8_hours(self):
        token = encode_jwt({"sub": str(self.user.id), "email": self.username})
        payload = decode_jwt(token)
        delta = payload['exp'] - payload['iat']  # segundos (timestamps int)
        self.assertAlmostEqual(delta, 8 * 3600, delta=120)

    def test_csrf_endpoint_sets_cookie(self):
        resp = self.client.get("/api/auth/csrf/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn('csrftoken', resp.cookies)

    def test_change_password_requires_csrf(self):
        self._login()
        # Sin X-CSRFToken -> 403 (CSRF)
        no_csrf = self.client.post(
            "/api/auth/me/change-password/",
            data=json.dumps({
                "current_password": self.password,
                "new_password": "NewPassword456!",
                "confirm_password": "NewPassword456!",
            }),
            content_type="application/json",
        )
        self.assertEqual(no_csrf.status_code, 403)

        # Obtener el csrftoken vía /csrf/ y enviarlo en X-CSRFToken -> 200
        self.client.get("/api/auth/csrf/")
        csrf_cookie = self.client.cookies.get('csrftoken')
        self.assertIsNotNone(csrf_cookie)
        ok = self.client.post(
            "/api/auth/me/change-password/",
            data=json.dumps({
                "current_password": self.password,
                "new_password": "NewPassword456!",
                "confirm_password": "NewPassword456!",
            }),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_cookie.value,
        )
        self.assertEqual(ok.status_code, 200)

    def test_protected_mutations_require_csrf(self):
        admin = User.objects.create_user(
            username="admin@example.com",
            email="admin@example.com",
            password="AdminSecret123!",
            is_staff=True,
        )
        self.client.cookies[self.cookie_name] = encode_jwt({
            "sub": str(admin.id),
            "email": admin.email,
        })

        mutations = (
            ("POST", "/api/auth/service/status/", {"userId": self.user.id, "status": "PENDING"}),
            ("POST", "/api/auth/logout/", {}),
            ("POST", "/api/admin/analysts/", {"userId": self.user.id, "grant": True}),
            ("POST", "/api/genetics/variantes/", {}),
            ("POST", "/api/ingest/upload-genetic-file/", {}),
            ("POST", "/api/ingest/delete-genetic-file/", {}),
            ("POST", "/api/reception/arrival/", {}),
            ("POST", "/api/reception/sample-code/", {}),
            ("POST", "/api/reception/sample-status/", {}),
            ("POST", "/api/auth/me/change-password/", {}),
            ("DELETE", "/api/auth/me/delete-account/", {}),
        )

        for method, path, payload in mutations:
            with self.subTest(path=path):
                if method == "DELETE":
                    response = self.client.delete(
                        path,
                        data=json.dumps(payload),
                        content_type="application/json",
                    )
                else:
                    response = self.client.post(
                        path,
                        data=json.dumps(payload),
                        content_type="application/json",
                    )
                self.assertEqual(response.status_code, 403)

    def test_csrf_rejects_mismatched_cookie_and_header(self):
        admin = User.objects.create_user(
            username="admin@example.com",
            email="admin@example.com",
            password="AdminSecret123!",
            is_staff=True,
        )
        self.client.cookies[self.cookie_name] = encode_jwt({
            "sub": str(admin.id),
            "email": admin.email,
        })
        self.client.cookies["csrftoken"] = "expected-token"

        response = self.client.post(
            "/api/auth/service/status/",
            data=json.dumps({"userId": self.user.id, "status": "PENDING"}),
            content_type="application/json",
            HTTP_X_CSRFTOKEN="different-token",
        )

        self.assertEqual(response.status_code, 403)

    @patch("accounts.views.send_email", return_value=True)
    def test_contact_email_escapes_untrusted_html(self, send_email):
        response = self.client.post(
            "/api/contact/",
            data=json.dumps({
                "nombre": "<script>alert(1)</script>",
                "email": "visitor@example.com",
                "mensaje": "</div><img src=x onerror=alert(1)>",
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        html_body = send_email.call_args.kwargs["html_body"]
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html_body)
        self.assertIn("&lt;/div&gt;&lt;img src=x onerror=alert(1)&gt;", html_body)
        self.assertNotIn("<script>alert(1)</script>", html_body)

    def test_handle_based_user_can_login_by_email(self):
        handle_user = User.objects.create_user(
            username="ana_handle",
            email="ana@example.com",
            password="HandleSecret123!",
            is_active=True,
        )

        response = self._login(username="ANA@EXAMPLE.COM", password="HandleSecret123!")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["success"])
        self.assertIsNotNone(response.cookies.get(self.cookie_name))
        self.assertEqual(handle_user.username, "ana_handle")

    def test_handle_based_user_can_login_by_username_case_insensitively(self):
        User.objects.create_user(
            username="ana_handle",
            email="ana@example.com",
            password="HandleSecret123!",
            is_active=True,
        )

        response = self._login(username=" ANA_HANDLE ", password="HandleSecret123!")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["success"])

    def test_me_includes_username(self):
        User.objects.create_user(
            username="ana_handle",
            email="ana@example.com",
            password="HandleSecret123!",
            is_active=True,
        )

        response = self._login(username="ana_handle", password="HandleSecret123!")
        self.assertEqual(response.status_code, 200)

        me = self.client.get("/api/auth/me/")

        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.data["user"]["username"], "ana_handle")


class FunctionalRoleAuthorizationTests(TestCase):
    """Only the one explicit AppUser role authorizes privileged API actions."""

    def setUp(self):
        self.target = User.objects.create_user(username='target', email='target@example.com')
        Profile.objects.create(user=self.target)
        self.routes = (
            ('GET', '/api/admin/users/', None, {'ADMIN', 'ANALISTA'}, 200),
            ('GET', '/api/admin/stats/', None, {'ADMIN', 'ANALISTA'}, 200),
            ('POST', '/api/auth/service/status/',
             {'userId': self.target.pk, 'status': 'PENDING'}, {'ADMIN', 'ANALISTA'}, 200),
            ('POST', '/api/admin/analysts/',
             {'userId': self.target.pk, 'grant': False}, {'ADMIN'}, 200),
            ('GET', '/api/reception/search/?email=target@example.com',
             None, {'ADMIN', 'RECEPCION'}, 200),
            ('POST', '/api/reception/arrival/',
             {'userId': self.target.pk}, {'ADMIN', 'RECEPCION'}, 200),
            ('POST', '/api/genetics/variantes/', {}, {'ADMIN', 'ANALISTA'}, 400),
        )

    def request_as(self, user, method, path, payload):
        client = APIClient()
        client.cookies[settings.AUTH_COOKIE_NAME] = encode_jwt({'sub': str(user.pk)})
        client.cookies['csrftoken'] = 'valid-test-csrf'
        if method == 'POST':
            return client.post(path, data=json.dumps(payload), content_type='application/json',
                               HTTP_X_CSRFTOKEN='valid-test-csrf')
        return client.get(path)

    def test_flags_legacy_groups_cliente_and_unmapped_never_elevate(self):
        users = [
            User.objects.create_user(username='staff-only', is_staff=True),
            User.objects.create_user(username='superuser-only', is_superuser=True),
            User.objects.create_user(username='client'),
        ]
        for role_code in ('ADMIN', 'ANALISTA', 'RECEPCION'):
            user = User.objects.create_user(username=f'legacy-{role_code.lower()}')
            user.groups.add(Group.objects.get_or_create(name=role_code)[0])
            users.append(user)
        unmapped = User.objects.bulk_create([User(username='unmapped')])[0]
        users.append(unmapped)
        for user in users:
            with self.subTest(user=user.username):
                self.assertFalse(is_admin(user))
                self.assertFalse(is_analyst(user))
                self.assertFalse(is_reception(user))
                for method, path, payload, _, _ in self.routes:
                    response = self.request_as(user, method, path, payload)
                    self.assertEqual(response.status_code, 403, (user.username, path, response.data))
                    self.assertNotIn('CSRF', str(response.data))

    def test_explicit_role_admits_only_its_routes_even_without_staff_or_groups(self):
        for code in ('ADMIN', 'ANALISTA', 'RECEPCION'):
            user = User.objects.create_user(username=code.lower())
            user.app_user.role = Role.objects.get(code=code)
            user.app_user.save(update_fields=['role'])
            self.assertFalse(user.is_staff)
            self.assertFalse(user.groups.exists())
            for method, path, payload, permitted, expected in self.routes:
                with self.subTest(role=code, path=path):
                    response = self.request_as(user, method, path, payload)
                    self.assertEqual(response.status_code, expected if code in permitted else 403,
                                     (code, path, response.data))
                    self.assertNotIn('CSRF', str(response.data))

    def test_grants_and_revokes_change_one_role_without_changing_django_flags_or_groups(self):
        user = User.objects.create_user(username='mutated')
        legacy = Group.objects.get_or_create(name='ANALISTA')[0]
        user.groups.add(legacy)
        grant_admin_role(user)
        user.refresh_from_db()
        self.assertEqual(user.app_user.role.code, 'ADMIN')
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        revoke_analyst_role(user)
        self.assertEqual(AppUser.objects.get(django_user=user).role.code, 'ADMIN')
        grant_reception_role(user)
        self.assertEqual(AppUser.objects.get(django_user=user).role.code, 'RECEPCION')
        revoke_analyst_role(user)
        self.assertEqual(AppUser.objects.get(django_user=user).role.code, 'RECEPCION')
        grant_analyst_role(user)
        self.assertEqual(AppUser.objects.get(django_user=user).role.code, 'ANALISTA')
        revoke_reception_role(user)
        self.assertEqual(AppUser.objects.get(django_user=user).role.code, 'ANALISTA')
        revoke_analyst_role(user)
        self.assertEqual(AppUser.objects.get(django_user=user).role.code, 'CLIENTE')
        self.assertEqual(list(user.groups.values_list('name', flat=True)), ['ANALISTA'])
        self.assertFalse(User.objects.get(pk=user.pk).is_staff)

    def test_unmapped_target_is_not_implicitly_assigned_a_privileged_role(self):
        admin = User.objects.create_user(username='mapped-admin')
        grant_admin_role(admin)
        unmapped = User.objects.bulk_create([User(username='unmapped-target')])[0]
        response = self.request_as(admin, 'POST', '/api/admin/analysts/',
                                   {'userId': unmapped.pk, 'grant': True, 'role': 'analyst'})
        self.assertEqual(response.status_code, 400, response.data)
        self.assertFalse(AppUser.objects.filter(django_user=unmapped).exists())

    def test_conflicting_legacy_group_does_not_override_explicit_role(self):
        admin = User.objects.create_user(username='mapped-admin')
        admin.groups.add(Group.objects.get_or_create(name='RECEPCION')[0])
        grant_admin_role(admin)
        self.assertTrue(is_admin(admin))
        self.assertFalse(is_reception(admin))
        response = self.request_as(admin, 'GET', '/api/reception/search/?email=target@example.com', None)
        self.assertEqual(response.status_code, 200)

    def test_manage_role_rejects_non_boolean_grant_without_mutation(self):
        admin = User.objects.create_user(username='boolean-admin')
        grant_admin_role(admin)
        path = '/api/admin/analysts/'
        invalid_values = ('false', 'true', 0, 1, 2, [], [False], {}, None)
        for role, code in (('analyst', 'ANALISTA'), ('reception', 'RECEPCION')):
            for original in ('CLIENTE', code):
                for value in invalid_values:
                    with self.subTest(role=role, original=original, grant=value):
                        AppUser.objects.filter(django_user=self.target).update(
                            role=Role.objects.get(code=original)
                        )
                        response = self.request_as(admin, 'POST', path, {
                            'userId': self.target.pk, 'grant': value, 'role': role,
                        })
                        self.assertEqual(response.status_code, 400, response.data)
                        self.assertEqual(
                            AppUser.objects.get(django_user=self.target).role.code, original
                        )

    def test_manage_role_accepts_json_true_and_false_for_both_roles(self):
        admin = User.objects.create_user(username='boolean-admin')
        grant_admin_role(admin)
        for role, code in (('analyst', 'ANALISTA'), ('reception', 'RECEPCION')):
            for value, expected in ((True, code), (False, 'CLIENTE')):
                with self.subTest(role=role, grant=value):
                    response = self.request_as(admin, 'POST', '/api/admin/analysts/', {
                        'userId': self.target.pk, 'grant': value, 'role': role,
                    })
                    self.assertEqual(response.status_code, 200, response.data)
                    self.assertEqual(response.data['roles'], [expected])
                    self.assertEqual(
                        AppUser.objects.get(django_user=self.target).role.code, expected
                    )

    def test_manage_role_preserves_response_but_reports_only_functional_role(self):
        admin = User.objects.create_user(username='functional-admin')
        grant_admin_role(admin)
        self.target.groups.add(Group.objects.get_or_create(name='ADMIN')[0])
        path = '/api/admin/analysts/'
        for role, expected in (('analyst', 'ANALISTA'), ('reception', 'RECEPCION')):
            response = self.request_as(admin, 'POST', path,
                                       {'userId': self.target.pk, 'grant': True, 'role': role})
            self.assertEqual(response.status_code, 200, response.data)
            self.assertEqual(response.data['role'], role)
            self.assertEqual(response.data['roles'], [expected])
            self.assertEqual(AppUser.objects.get(django_user=self.target).role.code, expected)
            self.assertEqual(response.data['is_analyst'], role == 'analyst')
            self.assertEqual(response.data['is_reception'], role == 'reception')
        response = self.request_as(admin, 'POST', path,
                                   {'userId': self.target.pk, 'grant': False, 'role': 'analyst'})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['roles'], ['RECEPCION'])
        response = self.request_as(admin, 'POST', path,
                                   {'userId': self.target.pk, 'grant': False, 'role': 'reception'})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['roles'], ['CLIENTE'])
        self.assertEqual(list(self.target.groups.values_list('name', flat=True)), ['ADMIN'])


class FunctionalRoleReadSurfaceTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username='api-admin')
        self.admin.app_user.role = Role.objects.get(code='ADMIN')
        self.admin.app_user.save(update_fields=['role'])
        self.analyst = User.objects.create_user(username='api-analyst')
        self.analyst.app_user.role = Role.objects.get(code='ANALISTA')
        self.analyst.app_user.save(update_fields=['role'])
        self.reception = User.objects.create_user(username='api-reception')
        self.reception.app_user.role = Role.objects.get(code='RECEPCION')
        self.reception.app_user.save(update_fields=['role'])
        self.client_user = User.objects.create_user(username='client-staff', is_staff=True)
        self.client_user.groups.add(Group.objects.get_or_create(name='ADMIN')[0])
        self.super_client = User.objects.create_user(username='client-super', is_superuser=True)
        self.super_client.groups.add(Group.objects.get_or_create(name='ANALISTA')[0])
        self.unmapped = User.objects.bulk_create([User(username='unmapped-client')])[0]
        self.unmapped.groups.add(Group.objects.get_or_create(name='ADMIN')[0])
        for index, (user, status) in enumerate((
            (self.client_user, 'PENDING'), (self.super_client, 'COMPLETED'),
            (self.admin, 'PENDING'), (self.analyst, 'COMPLETED'),
            (self.reception, 'PENDING'), (self.unmapped, 'COMPLETED'),
        )):
            Profile.objects.create(user=user, service_status=status, sample_code=f'SAMPLE-{index}')

    def get_as(self, user, path):
        client = APIClient()
        client.cookies[settings.AUTH_COOKIE_NAME] = encode_jwt({'sub': str(user.pk)})
        return client.get(path)

    def test_me_reports_only_functional_role_and_does_not_create_groups(self):
        cases = (
            (self.client_user, ['CLIENTE'], 'user', (False, False, False)),
            (self.super_client, ['CLIENTE'], 'user', (False, False, False)),
            (self.admin, ['ADMIN'], 'admin', (True, False, False)),
            (self.analyst, ['ANALISTA'], 'analyst', (False, True, False)),
            (self.reception, ['RECEPCION'], 'reception', (False, False, True)),
            (self.unmapped, [], 'user', (False, False, False)),
        )
        initial_groups = list(Group.objects.order_by('pk').values_list('pk', 'name'))
        for user, expected_roles, user_type, flags in cases:
            with self.subTest(user=user.username):
                response = self.get_as(user, '/api/auth/me/')
                self.assertEqual(response.status_code, 200, response.data)
                data = response.data['user']
                self.assertEqual(data['roles'], expected_roles)
                self.assertEqual(data['user_type'], user_type)
                self.assertEqual((data['is_admin'], data['is_analyst'], data['is_reception']), flags)
                self.assertEqual(data['is_staff'], user.is_staff)
                self.assertEqual(data['is_superuser'], user.is_superuser)
        self.assertEqual(list(Group.objects.order_by('pk').values_list('pk', 'name')), initial_groups)

    def test_admin_listing_reports_real_role_and_analyst_only_sees_clients(self):
        listing = self.get_as(self.admin, '/api/admin/users/')
        self.assertEqual(listing.status_code, 200, listing.data)
        users = {user['id']: user for user in listing.data}
        self.assertEqual(set(users), {user.pk for user in (
            self.admin, self.analyst, self.reception, self.client_user,
            self.super_client, self.unmapped,
        )})
        for user, role, flags in (
            (self.client_user, 'CLIENTE', (False, False, False)),
            (self.super_client, 'CLIENTE', (False, False, False)),
            (self.admin, 'ADMIN', (True, False, False)),
            (self.analyst, 'ANALISTA', (False, True, False)),
            (self.reception, 'RECEPCION', (False, False, True)),
            (self.unmapped, None, (False, False, False)),
        ):
            with self.subTest(user=user.username):
                self.assertEqual(users[user.pk]['roles'], [role] if role else [])
                self.assertEqual(tuple(users[user.pk][field] for field in
                                       ('is_admin', 'is_analyst', 'is_reception')), flags)
        listing = self.get_as(self.analyst, '/api/admin/users/')
        self.assertEqual(listing.status_code, 200, listing.data)
        self.assertEqual({user['id'] for user in listing.data},
                         {self.client_user.pk, self.super_client.pk})
        self.assertTrue(all(set(user) == {'id', 'sample_code', 'service_status'}
                            for user in listing.data))

    def test_stats_count_active_functional_clients_only_in_normal_and_fallback_paths(self):
        response = self.get_as(self.analyst, '/api/admin/stats/')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['total_users'], 2)
        self.assertEqual(response.data['analysis_count'], 1)
        self.assertEqual(response.data['pending_reports'], 1)
        self.assertIn('variants_count', response.data)
        with patch('accounts.views.SNP.objects.count', side_effect=RuntimeError('test failure')):
            fallback = self.get_as(self.admin, '/api/admin/stats/')
        self.assertEqual(fallback.status_code, 200, fallback.data)
        self.assertEqual(fallback.data['total_users'], 2)


class AccountReadProjectionTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username='read-admin')
        grant_admin_role(self.admin)
        self.analyst = User.objects.create_user(username='read-analyst')
        grant_analyst_role(self.analyst)
        self.waiting = RequestStatus.objects.get(code='WAITING_SAMPLE')
        self.paid = PurchaseStatus.objects.get(code='PAID')
        self.now = timezone.now()

    def read_as(self, actor, path):
        client = APIClient()
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
        return purchase

    def test_lists_project_newest_paid_without_changing_legacy_fallback_or_shape(self):
        client = User.objects.create_user(username='read-client')
        Profile.objects.create(user=client, sample_code='READ-CLIENT', service_status='COMPLETED')
        self.paid_service(client, 'COMPLETED', purchased_at=self.now - timedelta(days=1))
        self.paid_service(client, 'WAITING_SAMPLE', purchased_at=self.now)
        no_profile = User.objects.create_user(username='read-no-profile')
        self.paid_service(no_profile)
        legacy = User.objects.create_user(username='read-legacy')
        Profile.objects.create(user=legacy, sample_code='READ-LEGACY', service_status='COMPLETED')
        absent = User.objects.create_user(username='read-absent')

        admin = self.read_as(self.admin, '/api/admin/users/')
        analyst = self.read_as(self.analyst, '/api/admin/users/')
        self.assertEqual((admin.status_code, analyst.status_code), (200, 200))
        rows = {row['id']: row for row in admin.data}
        self.assertEqual(set(rows[client.pk]), {
            'id', 'username', 'email', 'first_name', 'last_name', 'is_staff', 'is_superuser',
            'rut', 'sample_code', 'service_status', 'roles', 'is_admin', 'is_analyst', 'is_reception',
        })
        self.assertEqual(rows[client.pk]['service_status'], 'PENDING')
        self.assertEqual(rows[no_profile.pk]['service_status'], 'PENDING')
        self.assertEqual(rows[no_profile.pk]['sample_code'], None)
        self.assertEqual(rows[legacy.pk]['service_status'], 'COMPLETED')
        self.assertIsNone(rows[absent.pk]['service_status'])
        analyst_rows = {row['id']: row for row in analyst.data}
        self.assertEqual(set(analyst_rows), {client.pk, legacy.pk})
        self.assertEqual(analyst_rows[client.pk], {
            'id': client.pk, 'sample_code': 'READ-CLIENT', 'service_status': 'PENDING',
        })
        self.assertEqual(analyst_rows[legacy.pk]['service_status'], 'COMPLETED')
        Profile.objects.create(user=no_profile)
        refreshed = {row['id']: row for row in self.read_as(self.analyst, '/api/admin/users/').data}
        self.assertEqual(refreshed[no_profile.pk]['service_status'], 'PENDING')
        self.assertTrue(refreshed[no_profile.pk]['sample_code'])
        self.assertEqual(Profile.objects.get(user=no_profile).sample_code,
                         refreshed[no_profile.pk]['sample_code'])

    def test_stats_count_only_active_clients_but_include_paid_without_profile(self):
        legacy = User.objects.create_user(username='stats-legacy')
        Profile.objects.create(user=legacy, service_status='COMPLETED')
        paid = User.objects.create_user(username='stats-paid')
        self.paid_service(paid, 'COMPLETED')  # No Profile; still an active client.
        waiting = User.objects.create_user(username='stats-waiting')
        Profile.objects.create(user=waiting, service_status='COMPLETED')
        self.paid_service(waiting)
        broken = User.objects.create_user(username='stats-broken')
        Profile.objects.create(user=broken, service_status='COMPLETED')
        self.paid_service(broken, 'COMPLETED', purchased_at=self.now - timedelta(days=1))
        Purchase.objects.create(owner=broken.app_user, status=self.paid)  # Missing timestamp/request.
        inactive = User.objects.create_user(username='stats-inactive', is_active=False)
        Profile.objects.create(user=inactive, service_status='PENDING')
        nonclient = User.objects.create_user(username='stats-reception')
        grant_reception_role(nonclient)
        Profile.objects.create(user=nonclient, service_status='PENDING')
        unmapped = User.objects.bulk_create([User(username='stats-unmapped')])[0]
        Profile.objects.create(user=unmapped, service_status='COMPLETED')
        Purchase.objects.create(owner=legacy.app_user, status=PurchaseStatus.objects.get(code='PENDING'),
                                created_at=self.now + timedelta(days=2))

        for actor in (self.admin, self.analyst):
            with self.subTest(actor=actor.username):
                response = self.read_as(actor, '/api/admin/stats/')
                self.assertEqual(response.status_code, 200, response.data)
                self.assertEqual(set(response.data), {
                    'total_users', 'pending_reports', 'analysis_count', 'variants_count',
                    'user_growth', 'report_growth', 'analysis_growth', 'last_update',
                })
                self.assertEqual((response.data['total_users'], response.data['pending_reports'],
                                  response.data['analysis_count']), (4, 1, 2))
                self.assertEqual(response.data['variants_count'], 0)
                self.assertIn('no-store', response['Cache-Control'])
        rows = {row['id']: row for row in self.read_as(self.admin, '/api/admin/users/').data}
        self.assertEqual(rows[broken.pk]['service_status'], 'NO_PURCHASED')
        self.assertEqual(rows[legacy.pk]['service_status'], 'COMPLETED')
        analyst_rows = {row['id']: row for row in self.read_as(self.analyst, '/api/admin/users/').data}
        self.assertEqual(analyst_rows[broken.pk]['service_status'], 'NO_PURCHASED')
        self.assertNotIn(inactive.pk, analyst_rows)
        self.assertNotIn(nonclient.pk, analyst_rows)
        self.assertNotIn(unmapped.pk, analyst_rows)

    def test_invalid_paid_participant_ownership_fails_closed_across_reads(self):
        owner = User.objects.create_user(username='bad-participant-owner')
        other = User.objects.create_user(username='bad-participant-other')
        Profile.objects.create(user=owner, sample_code='BAD-OWNER', service_status='COMPLETED')
        purchase = self.paid_service(owner, 'COMPLETED')
        participant = Participant.objects.create(user=other, participant_code='bad-owner')
        ServiceRequest.objects.filter(purchase=purchase).update(participant=participant)
        admin_rows = {row['id']: row for row in self.read_as(self.admin, '/api/admin/users/').data}
        analyst_rows = {row['id']: row for row in self.read_as(self.analyst, '/api/admin/users/').data}
        self.assertEqual(admin_rows[owner.pk]['service_status'], 'NO_PURCHASED')
        self.assertEqual(analyst_rows[owner.pk]['service_status'], 'NO_PURCHASED')
        self.assertEqual(self.read_as(self.admin, '/api/admin/stats/').data['analysis_count'], 0)

        # Even after ownership is repaired, a missing initial log or a latest
        # history/status disagreement cannot expose the old completed Profile.
        service = ServiceRequest.objects.get(purchase=purchase)
        ServiceRequest.objects.filter(pk=service.pk).update(participant=None)
        ServiceStatusLog.objects.filter(request=service, status=self.waiting).delete()
        rows = {row['id']: row for row in self.read_as(self.admin, '/api/admin/users/').data}
        self.assertEqual(rows[owner.pk]['service_status'], 'NO_PURCHASED')
        ServiceStatusLog.objects.create(
            request=service, status=self.waiting, actor=self.admin.app_user,
            changed_at=self.now + timedelta(seconds=3),
        )
        analyst_rows = {row['id']: row for row in self.read_as(self.analyst, '/api/admin/users/').data}
        self.assertEqual(analyst_rows[owner.pk]['service_status'], 'NO_PURCHASED')
        self.assertEqual(self.read_as(self.analyst, '/api/admin/stats/').data['analysis_count'], 0)

    def test_dashboard_retains_legacy_profile_cohort_and_metric_keys(self):
        legacy = User.objects.create_user(username='dashboard-legacy')
        Profile.objects.create(user=legacy, service_status='COMPLETED')
        waiting = User.objects.create_user(username='dashboard-waiting')
        Profile.objects.create(user=waiting, service_status='COMPLETED')
        self.paid_service(waiting)
        paid_no_profile = User.objects.create_user(username='dashboard-no-profile')
        self.paid_service(paid_no_profile, 'COMPLETED')
        inactive = User.objects.create_user(username='dashboard-inactive', is_active=False)
        Profile.objects.create(user=inactive, service_status='COMPLETED')
        Profile.objects.create(user=self.analyst, service_status='COMPLETED')

        response = self.read_as(self.admin, '/api/auth/dashboard/')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(set(response.data), {
            'user', 'profile', 'total_users', 'processed_reports', 'variants_count',
            'analysis_count', 'user_growth', 'report_growth', 'analysis_growth', 'last_update',
        })
        self.assertEqual(response.data['total_users'], 5)  # Inactive Profile still counts in analysis.
        self.assertEqual(response.data['analysis_count'], 3)  # Legacy, inactive, analyst; no profile excluded.
        self.assertEqual((response.data['processed_reports'], response.data['variants_count']), (0, 0))
        self.assertIn('no-store', response['Cache-Control'])

    def test_list_and_stats_query_count_does_not_grow_per_paid_client(self):
        for index in range(18):
            user = User.objects.create_user(username=f'bulk-client-{index}')
            Profile.objects.create(user=user, sample_code=f'BULK-{index}', service_status='COMPLETED')
            self.paid_service(user)
        for actor, path in (
            (self.admin, '/api/admin/users/'),
            (self.analyst, '/api/admin/users/'),
            (self.admin, '/api/admin/stats/'),
            (self.admin, '/api/auth/dashboard/'),
        ):
            with self.subTest(path=path):
                with CaptureQueriesContext(connection) as queries:
                    response = self.read_as(actor, path)
                self.assertEqual(response.status_code, 200, response.data)
                self.assertLessEqual(len(queries), 14, [query['sql'] for query in queries])


class LegacyServiceStatusPostTests(TestCase):
    """The userId-only endpoint is Profile-only and cannot select a paid service."""

    def setUp(self):
        self.target = User.objects.create_user(username='legacy-status-target')
        self.admin = User.objects.create_user(username='legacy-status-admin')
        grant_admin_role(self.admin)
        self.analyst = User.objects.create_user(username='legacy-status-analyst')
        grant_analyst_role(self.analyst)

    def client_as(self, actor, *, csrf=True):
        client = APIClient()
        client.cookies[settings.AUTH_COOKIE_NAME] = encode_jwt({'sub': str(actor.pk)})
        if csrf:
            client.cookies['csrftoken'] = 'legacy-status-csrf'
        return client

    def post_status(self, status, *, actor=None, csrf=True):
        return self.post_user_id(self.target.pk, status, actor=actor, csrf=csrf)

    def post_user_id(self, user_id, status='PENDING', *, actor=None, csrf=True):
        return self.client_as(actor or self.admin, csrf=csrf).post(
            '/api/auth/service/status/',
            data=json.dumps({'userId': user_id, 'status': status}),
            content_type='application/json',
            **({'HTTP_X_CSRFTOKEN': 'legacy-status-csrf'} if csrf else {}),
        )

    def purchase(self, code='PAID', *, purchased_at=None):
        return Purchase.objects.create(
            owner=self.target.app_user, status=PurchaseStatus.objects.get(code=code),
            purchased_at=purchased_at if purchased_at is not None else timezone.now(),
        )

    def test_truthy_mapping_user_id_is_400_without_profile_or_service_mutation(self):
        purchase = self.purchase()
        waiting = RequestStatus.objects.get(code='WAITING_SAMPLE')
        service = ServiceRequest.objects.create(purchase=purchase, status=waiting)
        ServiceStatusLog.objects.create(request=service, status=waiting, actor=self.admin.app_user)

        response = self.post_user_id({'id': self.target.pk})

        self.assertEqual(response.status_code, 400, response.data)
        self.assertFalse(Profile.objects.exists())
        self.assertEqual(Purchase.objects.filter(pk=purchase.pk, status__code='PAID').count(), 1)
        self.assertEqual(ServiceRequest.objects.filter(pk=service.pk, status=waiting).count(), 1)
        self.assertEqual(ServiceStatusLog.objects.filter(request=service).count(), 1)

    def test_malformed_user_ids_are_400_without_updating_existing_rows(self):
        profile = Profile.objects.create(user=self.target, service_status='PENDING')
        purchase = self.purchase()
        waiting = RequestStatus.objects.get(code='WAITING_SAMPLE')
        service = ServiceRequest.objects.create(purchase=purchase, status=waiting)
        log = ServiceStatusLog.objects.create(request=service, status=waiting, actor=self.admin.app_user)
        before_profile = (profile.service_status, profile.service_updated_at)
        before_purchase = (purchase.status_id, purchase.purchased_at)
        before_service = service.status_id
        before_log = (log.status_id, log.changed_at)
        invalid = (
            True, False, [self.target.pk], {'id': self.target.pk}, 1.0,
            1.5, -1, 0, None, [], {}, '', '-1', '0', 'not-an-id',
            f'0{self.target.pk}', f' {self.target.pk}', f'{self.target.pk} ',
            f'+{self.target.pk}', f'{self.target.pk}.0', '1e2', '\u0661',
            2**63, str(2**63), '9' * 50,
        )
        for raw_id in invalid:
            with self.subTest(user_id=raw_id):
                response = self.post_user_id(raw_id)
                self.assertEqual(response.status_code, 400, response.data)
                self.assertIn('error', response.data)
                profile.refresh_from_db()
                purchase.refresh_from_db()
                service.refresh_from_db()
                log.refresh_from_db()
                self.assertEqual((profile.service_status, profile.service_updated_at), before_profile)
                self.assertEqual((purchase.status_id, purchase.purchased_at), before_purchase)
                self.assertEqual(service.status_id, before_service)
                self.assertEqual((log.status_id, log.changed_at), before_log)
        self.assertEqual(Profile.objects.count(), 1)
        self.assertEqual(Purchase.objects.count(), 1)
        self.assertEqual(ServiceRequest.objects.count(), 1)
        self.assertEqual(ServiceStatusLog.objects.count(), 1)

    def test_canonical_decimal_string_id_preserves_legacy_write_and_paid_rejection(self):
        for requested in ('PENDING', 'NO_PURCHASED'):
            with self.subTest(status=requested):
                response = self.post_user_id(str(self.target.pk), requested)
                self.assertEqual(response.status_code, 200, response.data)
                profile = Profile.objects.get(user=self.target)
                self.assertEqual(response.data, {
                    'user_id': self.target.pk, 'service_status': requested,
                    'updated_at': profile.service_updated_at,
                })
        profile_updated_at = profile.service_updated_at
        self.purchase()
        response = self.post_user_id(str(self.target.pk))
        self.assertEqual(response.status_code, 409, response.data)
        profile.refresh_from_db()
        self.assertEqual((profile.service_status, profile.service_updated_at),
                         ('NO_PURCHASED', profile_updated_at))

    def test_any_status_rejects_one_paid_service_without_touching_profile_or_domain_rows(self):
        profile = Profile.objects.create(user=self.target, service_status='COMPLETED')
        purchase = self.purchase()
        waiting = RequestStatus.objects.get(code='WAITING_SAMPLE')
        service = ServiceRequest.objects.create(purchase=purchase, status=waiting)
        ServiceStatusLog.objects.create(request=service, status=waiting, actor=self.admin.app_user)
        original_updated_at = profile.service_updated_at

        for requested in ('NO_PURCHASED', 'PENDING', 'COMPLETED'):
            with self.subTest(status=requested):
                response = self.post_status(requested, actor=self.analyst)
                self.assertEqual(response.status_code, 409, response.data)
                profile.refresh_from_db()
                service.refresh_from_db()
                purchase.refresh_from_db()
                self.assertEqual((profile.service_status, profile.service_updated_at),
                                 ('COMPLETED', original_updated_at))
                self.assertEqual(service.status_id, waiting.pk)
                self.assertEqual(purchase.status.code, 'PAID')
                self.assertEqual(ServiceStatusLog.objects.filter(request=service).count(), 1)

    def test_multiple_paid_services_reject_even_when_newest_is_inconsistent(self):
        profile = Profile.objects.create(user=self.target, service_status='PENDING')
        older = self.purchase(purchased_at=timezone.now() - timedelta(days=1))
        waiting = RequestStatus.objects.get(code='WAITING_SAMPLE')
        service = ServiceRequest.objects.create(purchase=older, status=waiting)
        ServiceStatusLog.objects.create(request=service, status=waiting, actor=self.admin.app_user)
        newer = self.purchase()  # Missing request/history cannot select the older paid service.
        before = (profile.service_status, profile.service_updated_at)

        for requested in ('NO_PURCHASED', 'PENDING', 'COMPLETED'):
            with self.subTest(status=requested):
                response = self.post_status(requested)
                self.assertEqual(response.status_code, 409, response.data)
                profile.refresh_from_db()
                self.assertEqual((profile.service_status, profile.service_updated_at), before)
        self.assertEqual(Purchase.objects.filter(owner=self.target.app_user, status__code='PAID').count(), 2)
        self.assertFalse(ServiceRequest.objects.filter(purchase=newer).exists())
        self.assertEqual(ServiceStatusLog.objects.filter(request=service).count(), 1)

    def test_two_consistent_paid_services_still_require_an_explicit_service_id(self):
        waiting = RequestStatus.objects.get(code='WAITING_SAMPLE')
        for _ in range(2):
            purchase = self.purchase()
            service = ServiceRequest.objects.create(purchase=purchase, status=waiting)
            ServiceStatusLog.objects.create(request=service, status=waiting, actor=self.admin.app_user)
        for requested in ('NO_PURCHASED', 'PENDING', 'COMPLETED'):
            with self.subTest(status=requested):
                response = self.post_status(requested)
                self.assertEqual(response.status_code, 409, response.data)
                self.assertFalse(Profile.objects.filter(user=self.target).exists())
        self.assertEqual(Purchase.objects.filter(owner=self.target.app_user).count(), 2)
        self.assertEqual(ServiceStatusLog.objects.filter(request__purchase__owner=self.target.app_user).count(), 2)

    def test_inconsistent_paid_purchase_never_creates_a_profile(self):
        purchase = self.purchase()
        waiting = RequestStatus.objects.get(code='WAITING_SAMPLE')
        service = ServiceRequest.objects.create(purchase=purchase, status=waiting)
        # Missing initial history and then missing payment timestamp both remain paid.
        for requested in ('NO_PURCHASED', 'PENDING', 'COMPLETED'):
            with self.subTest(status=requested):
                response = self.post_status(requested)
                self.assertEqual(response.status_code, 409, response.data)
                self.assertFalse(Profile.objects.filter(user=self.target).exists())
        self.assertFalse(ServiceStatusLog.objects.filter(request=service).exists())
        purchase.purchased_at = None
        purchase.save(update_fields=['purchased_at'])
        self.assertEqual(self.post_status('PENDING').status_code, 409)
        self.assertFalse(Profile.objects.filter(user=self.target).exists())
        service.refresh_from_db()
        self.assertEqual(service.status_id, waiting.pk)
        purchase.refresh_from_db()
        self.assertIsNone(purchase.purchased_at)

    def test_no_paid_purchase_allows_pending_and_no_purchased_profile_only_writes(self):
        self.purchase('PENDING')
        other = User.objects.create_user(username='other-paid-owner')
        Purchase.objects.create(owner=other.app_user, status=PurchaseStatus.objects.get(code='PAID'))
        for requested in ('PENDING', 'NO_PURCHASED'):
            with self.subTest(status=requested):
                response = self.post_status(requested)
                self.assertEqual(response.status_code, 200, response.data)
                profile = Profile.objects.get(user=self.target)
                self.assertEqual(set(response.data), {'user_id', 'service_status', 'updated_at'})
                self.assertEqual(response.data, {
                    'user_id': self.target.pk, 'service_status': requested,
                    'updated_at': profile.service_updated_at,
                })
                self.assertEqual(profile.service_status, requested)
        self.assertFalse(ServiceRequest.objects.filter(purchase__owner=self.target.app_user).exists())
        self.assertFalse(ServiceStatusLog.objects.filter(request__purchase__owner=self.target.app_user).exists())

    def test_no_paid_completion_is_rejected_without_creating_or_updating_profile(self):
        self.assertEqual(self.post_status('COMPLETED').status_code, 409)
        self.assertFalse(Profile.objects.filter(user=self.target).exists())
        self.purchase('PENDING')
        profile = Profile.objects.create(user=self.target, service_status='COMPLETED')
        original_updated_at = profile.service_updated_at
        response = self.post_status('COMPLETED')
        self.assertEqual(response.status_code, 409, response.data)
        profile.refresh_from_db()
        self.assertEqual((profile.service_status, profile.service_updated_at),
                         ('COMPLETED', original_updated_at))
        # Existing legacy completions remain visible on GET until the read cutover.
        self.assertEqual(self.client_as(self.target).get('/api/auth/service/status/').data, {
            'user_id': self.target.pk, 'service_status': 'COMPLETED',
            'can_view_results': True, 'updated_at': original_updated_at,
        })

    def test_existing_role_and_csrf_barriers_still_precede_status_writes(self):
        self.assertEqual(self.post_status('PENDING', actor=self.target).status_code, 403)
        self.assertEqual(self.post_status('PENDING', actor=self.admin, csrf=False).status_code, 403)
        self.assertFalse(Profile.objects.filter(user=self.target).exists())
        self.assertEqual(self.post_status('PENDING', actor=self.analyst).status_code, 200)

    def test_invalid_status_and_unknown_target_keep_validation_and_lookup_responses(self):
        self.assertEqual(self.post_status('INVALID').status_code, 400)
        client = self.client_as(self.admin)
        response = client.post(
            '/api/auth/service/status/',
            data=json.dumps({'userId': self.target.pk + 10000, 'status': 'PENDING'}),
            content_type='application/json', HTTP_X_CSRFTOKEN='legacy-status-csrf',
        )
        self.assertEqual(response.status_code, 404, response.data)
        self.assertFalse(Profile.objects.filter(user=self.target).exists())


class SelfServiceProjectionTests(TestCase):
    def test_paid_waiting_overrides_legacy_completion_across_self_reads(self):
        user = User.objects.create_user(username='self-paid-waiting')
        Profile.objects.create(user=user, service_status='COMPLETED', phone='1234567')
        purchase = Purchase.objects.create(
            owner=user.app_user, status=PurchaseStatus.objects.get(code='PAID'),
            purchased_at=timezone.now(),
        )
        service = ServiceRequest.objects.create(
            purchase=purchase, status=RequestStatus.objects.get(code='WAITING_SAMPLE'),
        )
        log = ServiceStatusLog.objects.create(request=service, status=service.status, actor=user.app_user)
        client = APIClient()
        client.cookies[settings.AUTH_COOKIE_NAME] = encode_jwt({'sub': str(user.pk)})

        status = client.get('/api/auth/service/status/')
        me = client.get('/api/auth/me/')
        dashboard = client.get('/api/auth/dashboard/')
        for response in (status, me, dashboard):
            self.assertEqual(response.status_code, 200, getattr(response, 'data', None))
        self.assertEqual(status.data, {
            'user_id': user.pk, 'service_status': 'PENDING',
            'can_view_results': False, 'updated_at': log.changed_at,
        })
        self.assertEqual(me.data['user']['service_status'], 'PENDING')
        self.assertFalse(me.data['user']['can_view_results'])
        self.assertEqual(dashboard.data['profile'], {
            'phone': '1234567', 'service_status': 'PENDING', 'can_view_results': False,
        })
        profile = Profile.objects.get(user=user)
        self.assertEqual(profile.service_status, 'COMPLETED')  # The read does not repair legacy rows.
        self.assertEqual(ServiceStatusLog.objects.filter(request=service).count(), 1)

    def test_legacy_and_unmapped_users_keep_existing_self_response_shapes(self):
        legacy = User.objects.create_user(username='legacy-completed')
        Profile.objects.create(user=legacy, phone='legacy-phone', service_status='COMPLETED')
        client = APIClient()
        client.cookies[settings.AUTH_COOKIE_NAME] = encode_jwt({'sub': str(legacy.pk)})
        status = client.get('/api/auth/service/status/')
        me = client.get('/api/auth/me/')
        dashboard = client.get('/api/auth/dashboard/')
        self.assertEqual(status.status_code, 200)
        self.assertEqual(set(status.data), {'user_id', 'service_status', 'can_view_results', 'updated_at'})
        self.assertEqual(status.data['service_status'], 'COMPLETED')
        self.assertTrue(status.data['can_view_results'])
        self.assertEqual(status.data['updated_at'], legacy.profile.service_updated_at)
        self.assertEqual(me.data['user']['roles'], ['CLIENTE'])
        self.assertTrue(me.data['user']['can_view_results'])
        self.assertEqual(dashboard.data['profile'], {
            'phone': 'legacy-phone', 'service_status': 'COMPLETED', 'can_view_results': True,
        })
        self.assertIn('no-store', me['Cache-Control'])
        self.assertIn('no-store', dashboard['Cache-Control'])

        absent = User.objects.create_user(username='no-profile')
        client.cookies[settings.AUTH_COOKIE_NAME] = encode_jwt({'sub': str(absent.pk)})
        self.assertEqual(client.get('/api/auth/service/status/').data, {
            'user_id': absent.pk, 'service_status': 'NO_PURCHASED',
            'can_view_results': False, 'updated_at': None,
        })
        self.assertEqual(client.get('/api/auth/dashboard/').data['profile'], {
            'phone': None, 'service_status': 'NO_PURCHASED', 'can_view_results': False,
        })

    def test_completed_paid_service_exposes_results_only_with_history(self):
        user = User.objects.create_user(username='self-paid-completed')
        purchase = Purchase.objects.create(
            owner=user.app_user, status=PurchaseStatus.objects.get(code='PAID'),
            purchased_at=timezone.now(),
        )
        waiting = RequestStatus.objects.get(code='WAITING_SAMPLE')
        completed = RequestStatus.objects.get(code='COMPLETED')
        service = ServiceRequest.objects.create(
            purchase=purchase, status=completed,
            started_at=timezone.now() - timedelta(seconds=2), completed_at=timezone.now(),
        )
        ServiceStatusLog.objects.create(request=service, status=waiting, actor=user.app_user)
        completion = ServiceStatusLog.objects.create(
            request=service, status=completed, actor=user.app_user,
            changed_at=timezone.now() + timedelta(seconds=1),
        )
        client = APIClient()
        client.cookies[settings.AUTH_COOKIE_NAME] = encode_jwt({'sub': str(user.pk)})
        status = client.get('/api/auth/service/status/')
        self.assertEqual(status.data, {
            'user_id': user.pk, 'service_status': 'COMPLETED',
            'can_view_results': True, 'updated_at': completion.changed_at,
        })
        self.assertTrue(client.get('/api/auth/me/').data['user']['can_view_results'])
        self.assertTrue(client.get('/api/auth/dashboard/').data['profile']['can_view_results'])

    def test_paid_self_reads_preserve_role_boundary_without_exposing_other_account(self):
        user = User.objects.create_user(username='staff-with-client-role', is_staff=True)
        other = User.objects.create_user(username='other-completed')
        Profile.objects.create(user=other, service_status='COMPLETED')
        purchase = Purchase.objects.create(
            owner=user.app_user, status=PurchaseStatus.objects.get(code='PAID'),
            purchased_at=timezone.now(),
        )
        service = ServiceRequest.objects.create(
            purchase=purchase, status=RequestStatus.objects.get(code='WAITING_SAMPLE'),
        )
        ServiceStatusLog.objects.create(request=service, status=service.status, actor=user.app_user)
        client = APIClient()
        self.assertIn(client.get('/api/auth/service/status/').status_code, (401, 403))
        self.assertIn(client.get('/api/auth/me/').status_code, (401, 403))
        self.assertIn(client.get('/api/auth/dashboard/').status_code, (401, 403))
        client.cookies[settings.AUTH_COOKIE_NAME] = encode_jwt({'sub': str(user.pk)})
        me = client.get('/api/auth/me/')
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.data['user']['roles'], ['CLIENTE'])
        self.assertEqual(me.data['user']['user_type'], 'user')
        self.assertFalse(me.data['user']['is_admin'])
        self.assertTrue(me.data['user']['is_staff'])
        self.assertFalse(me.data['user']['can_view_results'])
        dashboard = client.get('/api/auth/dashboard/')
        self.assertEqual(set(dashboard.data), {'user', 'profile'})  # Django staff is not app ADMIN.
        self.assertFalse(dashboard.data['profile']['can_view_results'])
        self.assertEqual(client.get('/api/auth/service/status/').data['user_id'], user.pk)


class FunctionalRoleDjangoAdminTests(TestCase):
    def test_add_user_form_defers_role_edit_until_mapping_exists(self):
        superuser = User.objects.create_superuser(username='django-super', password='test-only')
        self.client.force_login(superuser)
        page = self.client.get(reverse('admin:auth_user_add'))
        self.assertEqual(page.status_code, 200)
        self.assertFalse(any(inline.formset.model is AppUser
                             for inline in page.context['inline_admin_formsets']))

    def test_superuser_changes_functional_role_without_staff_flags_or_mapping_rebind(self):
        superuser = User.objects.create_superuser(username='django-super', password='test-only')
        target = User.objects.create_user(username='functional-target')
        other = User.objects.create_user(username='other-target')
        Profile.objects.create(user=target)
        original_id = target.app_user.pk
        self.client.force_login(superuser)
        url = reverse('admin:auth_user_change', args=[target.pk])
        page = self.client.get(url)
        self.assertEqual(page.status_code, 200)
        role_id = Role.objects.get(code='ADMIN').pk
        payload = {
            'username': target.username, 'first_name': '', 'last_name': '',
            'email': '', 'is_active': 'on', '_save': 'Save',
            'date_joined_0': target.date_joined.strftime('%Y-%m-%d'),
            'date_joined_1': target.date_joined.strftime('%H:%M:%S'),
        }
        role_form_found = False
        role_prefix = None
        for inline in page.context['inline_admin_formsets']:
            forms = inline.formset
            prefix = forms.prefix
            for name, value in forms.management_form.initial.items():
                payload[f'{prefix}-{name}'] = value
            for index, form in enumerate(forms.initial_forms):
                payload[f'{prefix}-{index}-id'] = str(form.instance.pk)
                if isinstance(form.instance, Profile):
                    payload[f'{prefix}-{index}-phone'] = form.instance.phone
                    payload[f'{prefix}-{index}-service_status'] = form.instance.service_status
                if isinstance(form.instance, AppUser):
                    role_form_found = True
                    role_prefix = f'{prefix}-{index}'
                    payload[f'{role_prefix}-user_id'] = str(form.instance.pk)
                    payload[f'{role_prefix}-role'] = str(role_id)
        self.assertTrue(role_form_found, 'User admin must expose the AppUser role inline')
        result = self.client.post(url, payload)
        self.assertEqual(result.status_code, 302, (
            result.context['adminform'].form.errors,
            [(inline.formset.prefix, inline.formset.errors, inline.formset.non_form_errors())
             for inline in result.context['inline_admin_formsets']],
        ) if result.status_code == 200 else None)
        target.refresh_from_db()
        mapping = AppUser.objects.get(django_user=target)
        self.assertEqual(mapping.pk, original_id)
        self.assertEqual(mapping.role.code, 'ADMIN')
        self.assertFalse(target.is_staff)
        self.assertFalse(target.is_superuser)
        self.assertEqual(AppUser.objects.get(django_user=other).role.code, 'CLIENTE')
        self.assertEqual(AppUser.objects.filter(django_user=target).count(), 1)

        # The inline cannot delete a mapping or move it to another User.
        delete_attempt = self.client.post(url, {**payload, f'{role_prefix}-DELETE': 'on'})
        self.assertEqual(delete_attempt.status_code, 302)
        self.assertTrue(AppUser.objects.filter(pk=original_id, django_user=target).exists())
        forged = self.client.post(url, {**payload, f'{role_prefix}-django_user': str(other.pk)})
        self.assertEqual(forged.status_code, 200)
        self.assertTrue(AppUser.objects.filter(pk=original_id, django_user=target, role__code='ADMIN').exists())
        self.assertEqual(AppUser.objects.get(django_user=other).role.code, 'CLIENTE')
        wrong_id = self.client.post(url, {**payload, f'{role_prefix}-user_id': str(other.app_user.pk)})
        self.assertEqual(wrong_id.status_code, 200)
        self.assertTrue(AppUser.objects.filter(pk=original_id, django_user=target).exists())
        self.assertEqual(AppUser.objects.get(django_user=other).role.code, 'CLIENTE')


class ManageAnalystRoleAtomicResponseTests(TransactionTestCase):
    def test_role_mutation_and_response_snapshot_share_outer_transaction(self):
        admin = User.objects.create_user(username='atomic-admin')
        target = User.objects.create_user(username='atomic-target')
        grant_admin_role(admin)
        client = APIClient()
        client.cookies[settings.AUTH_COOKIE_NAME] = encode_jwt({'sub': str(admin.pk)})
        client.cookies['csrftoken'] = 'valid-test-csrf'
        original_grant = grant_analyst_role
        original_select_related = AppUser.objects.select_related
        observed = []

        def observe_grant(user):
            observed.append(('mutation', connection.in_atomic_block))
            return original_grant(user)

        def observe_snapshot(*fields):
            observed.append(('snapshot', connection.in_atomic_block))
            return original_select_related(*fields)

        with patch('accounts.views.grant_analyst_role', side_effect=observe_grant), \
                patch.object(AppUser.objects, 'select_related', side_effect=observe_snapshot):
            response = client.post(
                '/api/admin/analysts/',
                data=json.dumps({'userId': target.pk, 'grant': True, 'role': 'analyst'}),
                content_type='application/json',
                HTTP_X_CSRFTOKEN='valid-test-csrf',
            )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['roles'], ['ANALISTA'])
        self.assertEqual(observed, [('mutation', True), ('snapshot', True)])


class RoleBackfillMigrationTests(TestCase):
    """Exercise RunPython against the pre-seed historical model state, without schema changes."""

    def run_backfill(self):
        migration = import_module('accounts.migrations.0004_seed_roles_backfill')
        historical_apps = MigrationLoader(connection).project_state(
            [('accounts', '0003_role_appuser')]
        ).apps
        with transaction.atomic():
            migration.Migration.operations[0].code(
                historical_apps, SimpleNamespace(connection=connection)
            )

    def legacy_user(self, username, **flags):
        # Existing users predate the post_save hook; bulk_create skips signals.
        return User.objects.bulk_create([User(username=username, **flags)])[0]

    def test_seed_backfill_all_users_and_repeat_without_changing_explicit_mapping(self):
        Role.objects.all().delete()
        analyst = Role.objects.create(code='ANALISTA', name='Existing analyst')
        legacy_groups = {code: Group.objects.create(name=code) for code in Role.Code.values}
        other = Group.objects.create(name='OTHER')
        users = {
            code: self.legacy_user(code.lower()) for code in Role.Code.values
        }
        for code, user in users.items():
            user.groups.add(legacy_groups[code])
        unknown = self.legacy_user('unknown', is_staff=True)
        unknown.groups.add(other)
        superuser = self.legacy_user('superuser', is_staff=True, is_superuser=True)
        explicit = self.legacy_user('explicit')
        existing = AppUser.objects.create(django_user=explicit, role=analyst)

        self.run_backfill()

        self.assertEqual(set(Role.objects.values_list('code', flat=True)), set(Role.Code.values))
        self.assertEqual(Role.objects.get(code='ANALISTA').name, 'Existing analyst')
        for code, user in users.items():
            self.assertEqual(AppUser.objects.get(django_user=user).role.code, code)
        for user in (unknown, superuser):
            self.assertEqual(AppUser.objects.get(django_user=user).role.code, 'CLIENTE')
        self.assertEqual(AppUser.objects.get(django_user=explicit).pk, existing.pk)
        self.assertEqual(AppUser.objects.get(django_user=explicit).role_id, analyst.pk)
        role_ids = dict(Role.objects.values_list('code', 'pk'))
        mapping_ids = dict(AppUser.objects.values_list('django_user_id', 'pk'))

        self.run_backfill()

        self.assertEqual(dict(Role.objects.values_list('code', 'pk')), role_ids)
        self.assertEqual(dict(AppUser.objects.values_list('django_user_id', 'pk')), mapping_ids)

    def test_multiple_recognized_groups_abort_and_roll_back_all_seeds_and_mappings(self):
        Role.objects.all().delete()
        first = self.legacy_user('first')
        conflicted = self.legacy_user('conflicted', is_superuser=True, is_staff=True)
        conflicted.groups.add(Group.objects.create(name='ADMIN'))
        conflicted.groups.add(Group.objects.create(name='RECEPCION'))

        with self.assertRaisesRegex(RuntimeError, 'multiple recognized role Groups'):
            self.run_backfill()

        self.assertFalse(Role.objects.exists())
        self.assertFalse(AppUser.objects.filter(django_user__in=[first, conflicted]).exists())

    def test_existing_mapping_conflicting_with_one_group_reports_error_without_overwrite(self):
        Role.objects.all().delete()
        cliente = Role.objects.create(code='CLIENTE', name='Existing client')
        first = self.legacy_user('first')
        conflicted = self.legacy_user('conflicted')
        existing = AppUser.objects.create(django_user=conflicted, role=cliente)
        conflicted.groups.add(Group.objects.create(name='ADMIN'))

        with self.assertRaisesRegex(RuntimeError, 'AppUser role.*conflicts with legacy Group'):
            self.run_backfill()

        self.assertEqual(set(Role.objects.values_list('code', flat=True)), {'CLIENTE'})
        self.assertFalse(AppUser.objects.filter(django_user=first).exists())
        existing.refresh_from_db()
        self.assertEqual(existing.role_id, cliente.pk)

    def test_multiple_groups_abort_even_for_user_with_an_existing_mapping(self):
        mapped = self.legacy_user('mapped')
        AppUser.objects.create(django_user=mapped, role=Role.objects.get(code='CLIENTE'))
        mapped.groups.add(Group.objects.create(name='ADMIN'))
        mapped.groups.add(Group.objects.create(name='ANALISTA'))

        with self.assertRaisesRegex(RuntimeError, 'multiple recognized role Groups'):
            self.run_backfill()
        self.assertEqual(AppUser.objects.get(django_user=mapped).role.code, 'CLIENTE')


class NewUserRoleAssignmentTests(TestCase):
    def test_raw_created_user_does_not_query_role_or_app_user(self):
        with patch('accounts.signals.Role.objects.using') as role_using, \
                patch('accounts.signals.AppUser.objects.using') as mapping_using:
            role_using.return_value.get_or_create.return_value = (object(), True)
            assign_new_user_client_role(
                sender=User, instance=User(pk=1234, username='fixture-user'),
                created=True, raw=True, using='default',
            )
            role_using.assert_not_called()
            mapping_using.assert_not_called()

    def test_user_creation_paths_default_to_cliente_regardless_of_flags_or_group(self):
        group = Group.objects.create(name='ADMIN')
        ordinary = User.objects.create_user(username='registered')
        staff = User.objects.create(username='django-admin', is_staff=True)
        superuser = User.objects.create_superuser(username='django-superuser', password='test-only')
        superuser.groups.add(group)
        superuser.save(update_fields=['is_staff'])

        for user in (ordinary, staff, superuser):
            self.assertEqual(AppUser.objects.get(django_user=user).role.code, 'CLIENTE')
            self.assertEqual(AppUser.objects.filter(django_user=user).count(), 1)

    def test_missing_client_role_is_recreated_and_save_does_not_override_explicit_role(self):
        Role.objects.filter(code='CLIENTE').delete()
        user = User.objects.create_user(username='needs-client-role')
        self.assertEqual(user.app_user.role.code, 'CLIENTE')
        self.assertEqual(Role.objects.filter(code='CLIENTE').count(), 1)
        mapping_id = user.app_user.pk
        user.app_user.role = Role.objects.get(code='ADMIN')
        user.app_user.save(update_fields=['role'])

        user.is_staff = True
        user.save(update_fields=['is_staff'])

        self.assertEqual(AppUser.objects.get(django_user=user).pk, mapping_id)
        self.assertEqual(AppUser.objects.get(django_user=user).role.code, 'ADMIN')


class AppUserMappingTests(TestCase):
    """Additive domain accounts: Django User remains the authentication source."""

    def models(self):
        return apps.get_model('accounts', 'Role'), apps.get_model('accounts', 'AppUser')

    def test_schema_tables_uuid_keys_and_separate_django_user_link(self):
        Role, AppUser = self.models()
        self.assertEqual(Role._meta.db_table, 'role')
        self.assertEqual(AppUser._meta.db_table, 'app_user')
        self.assertEqual(Role._meta.pk.name, 'role_id')
        self.assertEqual(AppUser._meta.pk.name, 'user_id')
        self.assertEqual(AppUser._meta.get_field('django_user').remote_field.model, get_user_model())
        self.assertEqual(AppUser._meta.get_field('django_user').one_to_one, True)
        self.assertEqual(
            {field.name for field in AppUser._meta.local_fields},
            {'user_id', 'django_user', 'role', 'oidc_issuer', 'oidc_subject'},
        )
        with connection.cursor() as cursor:
            tables = connection.introspection.table_names(cursor)
            self.assertIn('role', tables)
            self.assertIn('app_user', tables)
            constraints = connection.introspection.get_constraints(cursor, 'app_user')
        self.assertTrue(any(
            details['primary_key'] and details['columns'] == ['user_id']
            for details in constraints.values()
        ))

    def test_local_users_receive_exactly_one_default_mapping(self):
        _, AppUser = self.models()
        user = get_user_model().objects.create_user(username='mapped')
        self.assertEqual(AppUser.objects.get(django_user=user).role.code, 'CLIENTE')
        self.assertEqual(AppUser.objects.filter(django_user=user).count(), 1)

    def test_two_local_users_can_share_one_role_without_oidc(self):
        Role, AppUser = self.models()
        role = Role.objects.get(code='CLIENTE')
        first = get_user_model().objects.create_user(username='local-1')
        second = get_user_model().objects.create_user(username='local-2')

        mappings = [user.app_user for user in (first, second)]

        for user, mapping in zip((first, second), mappings):
            self.assertIsInstance(mapping.pk, uuid.UUID)
            self.assertEqual(mapping.pk, mapping.user_id)
            self.assertIsInstance(mapping.django_user_id, int)
            self.assertEqual(user.app_user, mapping)
            self.assertEqual(mapping.role, role)
            self.assertIsNone(mapping.oidc_issuer)
            self.assertIsNone(mapping.oidc_subject)
        self.assertNotEqual(mappings[0].pk, mappings[1].pk)

    def test_role_codes_are_unique_and_restricted_to_functional_roles(self):
        Role, _ = self.models()
        self.assertEqual(
            set(Role.Code.values), {'CLIENTE', 'ADMIN', 'ANALISTA', 'RECEPCION'},
        )
        role = Role.objects.get(code='CLIENTE')
        self.assertIsInstance(role.pk, uuid.UUID)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Role.objects.create(code='CLIENTE', name='Another client')
        invalid = Role(code='ROOT', name='Unrecognized')
        with self.assertRaises(ValidationError):
            invalid.full_clean()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Role.objects.create(code='ROOT', name='Unrecognized')

    def test_user_link_and_role_are_required_and_one_to_one(self):
        Role, AppUser = self.models()
        role = Role.objects.get(code='CLIENTE')
        user = get_user_model().objects.create_user(username='local-1')
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                AppUser.objects.create(django_user=user, role=role)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                AppUser.objects.create(role=role)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                AppUser.objects.create(django_user=get_user_model().objects.bulk_create([
                    get_user_model()(username='local-2')
                ])[0])

    def test_oidc_identity_rejects_partial_or_empty_values_on_insert_and_update(self):
        Role, AppUser = self.models()
        role = Role.objects.get(code='CLIENTE')
        incomplete = [
            (None, 'subject'), ('https://issuer.example', None),
            ('', ''), ('', 'subject'), ('https://issuer.example', ''),
        ]
        for index, (issuer, subject) in enumerate(incomplete):
            with self.subTest(issuer=issuer, subject=subject):
                user = get_user_model().objects.bulk_create([
                    get_user_model()(username=f'partial-{index}')
                ])[0]
                with self.assertRaises(IntegrityError):
                    with transaction.atomic():
                        AppUser.objects.create(
                            django_user=user, role=role,
                            oidc_issuer=issuer, oidc_subject=subject,
                        )
        user = get_user_model().objects.create_user(username='local-update')
        mapping = user.app_user
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                AppUser.objects.filter(pk=mapping.pk).update(oidc_subject='subject')

    def test_oidc_identity_is_unique_per_issuer_when_present(self):
        Role, AppUser = self.models()
        role = Role.objects.get(code='CLIENTE')
        users = get_user_model().objects.bulk_create([
            get_user_model()(username=f'oidc-{index}') for index in range(3)
        ])
        AppUser.objects.create(
            django_user=users[0], role=role,
            oidc_issuer='https://issuer.example', oidc_subject='subject',
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                AppUser.objects.create(
                    django_user=users[1], role=role,
                    oidc_issuer='https://issuer.example', oidc_subject='subject',
                )
        other = AppUser.objects.create(
            django_user=users[2], role=role,
            oidc_issuer='https://other.example', oidc_subject='subject',
        )
        self.assertEqual(other.oidc_subject, 'subject')
