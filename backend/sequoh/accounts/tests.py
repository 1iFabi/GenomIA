import json
import os
import subprocess
import sys
import time
from datetime import timedelta
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace
from django.utils import timezone
from unittest.mock import patch

from allauth.account.models import EmailAddress, EmailConfirmationHMAC
from django.apps import apps
from django.core.cache import cache
from django.core.management import call_command
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, User
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.test.utils import CaptureQueriesContext
from django.db.migrations.loader import MigrationLoader
from django.test import SimpleTestCase, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
import uuid
from io import StringIO
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.test import APIClient, APIRequestFactory
from rest_framework.views import APIView

from .authentication import JWTAuthentication
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
        cache.clear()  # The login throttle counts across tests otherwise.
        self.client = APIClient()
        self.username = "user@example.com"
        self.password = "SuperSecret123!"
        self.user = User.objects.create_user(
            username=self.username, email=self.username, password=self.password, is_active=True
        )
        self.cookie_name = getattr(settings, 'AUTH_COOKIE_NAME', 'access_token')

    def _login(self, username=None, password=None):
        return self.client.post(
            "/api/auth/login/",
            data=json.dumps({
                "username": self.username if username is None else username,
                "password": self.password if password is None else password,
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

    def test_login_cookie_is_a_session_cookie_even_if_a_client_asks_to_be_remembered(self):
        self.client.cookies.clear()
        resp = self.client.post(
            "/api/auth/login/",
            data=json.dumps({"username": self.username, "password": self.password, "remember": True}),
            content_type="application/json",
        )
        cookie = resp.cookies.get(self.cookie_name)
        self.assertIsNotNone(cookie)
        self.assertIn(cookie.get('max-age'), (None, ''), "sin 'recordar cuenta': la cookie muere al cerrar el navegador")

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

    def test_token_ttl_is_two_hours(self):
        token = encode_jwt({"sub": str(self.user.id), "email": self.username})
        payload = decode_jwt(token)
        delta = payload['exp'] - payload['iat']  # segundos (timestamps int)
        self.assertAlmostEqual(delta, 2 * 3600, delta=120)

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

    def test_password_change_ends_other_sessions_but_keeps_the_current_one(self):
        other = APIClient()
        other.cookies[self.cookie_name] = self._login().cookies[self.cookie_name].value
        self.client.cookies[self.cookie_name] = self._login().cookies[self.cookie_name].value
        self.client.get("/api/auth/csrf/")
        changed = self.client.post(
            "/api/auth/me/change-password/",
            data=json.dumps({
                "current_password": self.password,
                "new_password": "NewPassword456!",
                "confirm_password": "NewPassword456!",
            }),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=self.client.cookies['csrftoken'].value,
        )
        self.assertEqual(changed.status_code, 200)
        self.assertIn(other.get("/api/auth/me/").status_code, (401, 403))
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 200)

    def test_password_reset_token_works_once_and_ends_sessions(self):
        from .models import PasswordResetToken
        old_session = self._login().cookies[self.cookie_name].value
        prt = PasswordResetToken.objects.create(user=self.user, expires_at=timezone.now() + timedelta(hours=1))
        expired = PasswordResetToken.objects.create(user=self.user, expires_at=timezone.now() - timedelta(seconds=1))

        def confirm(token):
            return self.client.post("/api/auth/password-reset-confirm/", data=json.dumps({
                "token": str(token), "password": "ResetPassword789!", "confirmPassword": "ResetPassword789!",
            }), content_type="application/json")

        older = PasswordResetToken.objects.create(user=self.user, expires_at=timezone.now() + timedelta(hours=1))
        self.assertEqual(confirm("not-a-uuid").data, {"error": "Token inválido"})
        self.assertEqual(confirm(expired.token).status_code, 400)
        self.assertEqual(confirm(prt.token).status_code, 200)
        self.assertEqual(confirm(prt.token).status_code, 400)
        self.assertEqual(confirm(older.token).status_code, 400)  # Every other pending link dies with the reset.
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("ResetPassword789!"))
        self.client.cookies[self.cookie_name] = old_session
        self.assertIn(self.client.get("/api/auth/me/").status_code, (401, 403))

    @override_settings(REQUIRE_EMAIL_VERIFICATION=True)
    def test_wrong_password_on_unverified_account_gives_the_generic_error(self):
        resp = self._login(password="WrongPassword1!")
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data, {"success": False, "error": "Credenciales inválidas"})

    def test_logout_purges_expired_revoked_tokens(self):
        RevokedToken.objects.create(jti='expired-jti', expires_at=timezone.now() - timedelta(seconds=1))
        self.client.cookies[self.cookie_name] = self._login().cookies[self.cookie_name].value
        self.client.get("/api/auth/csrf/")
        self.client.post("/api/auth/logout/", HTTP_X_CSRFTOKEN=self.client.cookies['csrftoken'].value)
        self.assertFalse(RevokedToken.objects.filter(jti='expired-jti').exists())
        self.assertEqual(RevokedToken.objects.count(), 1)

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
            ("POST", "/api/services/payments/", {"userId": self.user.id}),
            ("POST", f"/api/services/requests/{uuid.uuid4()}/advance/", {}),
            ("POST", "/api/auth/logout/", {}),
            ("POST", "/api/admin/analysts/", {"userId": self.user.id, "grant": True}),
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
            "/api/services/payments/",
            data=json.dumps({"userId": self.user.id}),
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
            ('POST', '/api/admin/analysts/',
             {'userId': self.target.pk, 'grant': False}, {'ADMIN'}, 200),
            ('GET', '/api/reception/search/?sample_code=GX-TARGET',
             None, {'ADMIN', 'RECEPCION'}, 200),
            # Unknown targets: permitted roles pass the role gate and then get 404.
            ('POST', '/api/services/payments/', {'userId': 2**31 - 1}, {'ADMIN', 'RECEPCION'}, 404),
            ('POST', f'/api/services/requests/{uuid.uuid4()}/advance/', {}, {'ADMIN', 'ANALISTA'}, 404),
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
        response = self.request_as(admin, 'GET', '/api/reception/search/?sample_code=GX-TARGET', None)
        self.assertEqual(response.status_code, 200)

    def test_manage_role_never_overwrites_an_admin(self):
        admin = User.objects.create_user(username='acting-admin')
        grant_admin_role(admin)
        grant_admin_role(self.target)
        for actor_target in (self.target, admin):
            for role in ('analyst', 'reception'):
                for grant in (True, False):
                    with self.subTest(target=actor_target.username, role=role, grant=grant):
                        response = self.request_as(admin, 'POST', '/api/admin/analysts/', {
                            'userId': actor_target.pk, 'grant': grant, 'role': role,
                        })
                        self.assertEqual(response.status_code, 409, response.data)
                        self.assertEqual(AppUser.objects.get(django_user=actor_target).role.code, 'ADMIN')

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
        for user in (self.client_user, self.super_client, self.admin, self.analyst,
                     self.reception, self.unmapped):
            Profile.objects.create(user=user)
        for user, code in ((self.client_user, 'WAITING_SAMPLE'), (self.super_client, 'COMPLETED')):
            purchase = Purchase.objects.create(
                owner=user.app_user, status=PurchaseStatus.objects.get(code='PAID'), purchased_at=timezone.now(),
            )
            state = RequestStatus.objects.get(code=code)
            service = ServiceRequest.objects.create(
                purchase=purchase, status=state,
                completed_at=timezone.now() + timedelta(seconds=1) if code == 'COMPLETED' else None,
            )
            for offset, log_state in enumerate(dict.fromkeys([RequestStatus.objects.get(code='WAITING_SAMPLE'), state])):
                ServiceStatusLog.objects.create(request=service, status=log_state, actor=self.admin.app_user,
                                                changed_at=timezone.now() + timedelta(seconds=offset))

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
        self.assertTrue(all(set(user) == {'id', 'service_request_id', 'service_status'}
                            for user in listing.data))

    def assert_no_legacy_snp_queries(self, queries):
        for query in queries:
            for table in ('snps', 'user_snps', 'rsid_extra_info', 'genetics_pharmacogeneticsystem'):
                self.assertNotIn(f'"{table}"', query['sql'])

    def test_stats_count_active_functional_clients_without_legacy_snp_metrics(self):
        for actor in (self.admin, self.analyst):
            with self.subTest(actor=actor.username):
                with CaptureQueriesContext(connection) as queries:
                    response = self.get_as(actor, '/api/admin/stats/')
                self.assertEqual(response.status_code, 200, response.data)
                self.assertEqual(response.data['total_users'], 2)
                self.assertEqual(response.data['analysis_count'], 1)
                self.assertEqual(response.data['pending_reports'], 1)
                self.assertNotIn('variants_count', response.data)
                self.assertNotIn('processed_reports', response.data)
                self.assertIn('no-store', response['Cache-Control'])
                self.assert_no_legacy_snp_queries(queries)

    def test_stats_fallback_preserves_client_count_without_legacy_snp_metrics(self):
        for actor in (self.admin, self.analyst):
            with self.subTest(actor=actor.username):
                with patch('accounts.views.get_service_projections',
                           side_effect=RuntimeError('test projection failure')) as projection:
                    with CaptureQueriesContext(connection) as queries:
                        fallback = self.get_as(actor, '/api/admin/stats/')
                projection.assert_called_once()
                self.assertEqual(fallback.status_code, 200, fallback.data)
                self.assertEqual(fallback.data['total_users'], 2)
                self.assertEqual(fallback.data['analysis_count'], 0)
                self.assertEqual(set(fallback.data), {'total_users', 'analysis_count', 'last_update'})
                self.assert_no_legacy_snp_queries(queries)


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

    def test_lists_project_newest_paid_service_and_shape(self):
        client = User.objects.create_user(username='read-client')
        Profile.objects.create(user=client)
        self.paid_service(client, 'COMPLETED', purchased_at=self.now - timedelta(days=1))
        self.paid_service(client, 'WAITING_SAMPLE', purchased_at=self.now)
        no_profile = User.objects.create_user(username='read-no-profile')
        self.paid_service(no_profile)
        unpaid = User.objects.create_user(username='read-unpaid')
        Profile.objects.create(user=unpaid)
        absent = User.objects.create_user(username='read-absent')

        admin = self.read_as(self.admin, '/api/admin/users/')
        analyst = self.read_as(self.analyst, '/api/admin/users/')
        self.assertEqual((admin.status_code, analyst.status_code), (200, 200))
        rows = {row['id']: row for row in admin.data}
        self.assertEqual(set(rows[client.pk]), {
            'id', 'username', 'email', 'first_name', 'last_name', 'is_staff', 'is_superuser',
            'service_status', 'roles', 'is_admin', 'is_analyst', 'is_reception',
        })
        self.assertEqual(rows[client.pk]['service_status'], 'PENDING')
        self.assertEqual(rows[no_profile.pk]['service_status'], 'PENDING')
        self.assertEqual(rows[unpaid.pk]['service_status'], 'NO_PURCHASED')
        self.assertEqual(rows[absent.pk]['service_status'], 'NO_PURCHASED')
        self.assertTrue(all(set(row) == {'id', 'service_request_id', 'service_status'} for row in analyst.data))
        self.assertEqual(sorted((row['id'], row['service_status']) for row in analyst.data), sorted([
            (client.pk, 'COMPLETED'), (client.pk, 'WAITING_SAMPLE'), (no_profile.pk, 'WAITING_SAMPLE'),
        ]))

    def test_stats_count_only_active_clients_with_valid_paid_services(self):
        paid = User.objects.create_user(username='stats-paid')
        self.paid_service(paid, 'COMPLETED')  # No Profile; still an active client.
        waiting = User.objects.create_user(username='stats-waiting')
        Profile.objects.create(user=waiting)
        self.paid_service(waiting)
        broken = User.objects.create_user(username='stats-broken')
        Profile.objects.create(user=broken)
        self.paid_service(broken, 'COMPLETED', purchased_at=self.now - timedelta(days=1))
        Purchase.objects.create(owner=broken.app_user, status=self.paid)  # Missing timestamp/request.
        unpaid = User.objects.create_user(username='stats-unpaid')
        Profile.objects.create(user=unpaid)
        Purchase.objects.create(owner=unpaid.app_user, status=PurchaseStatus.objects.get(code='PENDING'))
        inactive = User.objects.create_user(username='stats-inactive', is_active=False)
        self.paid_service(inactive)
        nonclient = User.objects.create_user(username='stats-reception')
        grant_reception_role(nonclient)
        User.objects.bulk_create([User(username='stats-unmapped')])

        for actor in (self.admin, self.analyst):
            with self.subTest(actor=actor.username):
                response = self.read_as(actor, '/api/admin/stats/')
                self.assertEqual(response.status_code, 200, response.data)
                self.assertEqual(set(response.data), {
                    'total_users', 'pending_reports', 'analysis_count', 'last_update',
                })
                self.assertEqual((response.data['total_users'], response.data['pending_reports'],
                                  response.data['analysis_count']), (4, 1, 1))
                self.assertIn('no-store', response['Cache-Control'])
        rows = {row['id']: row for row in self.read_as(self.admin, '/api/admin/users/').data}
        self.assertEqual(rows[broken.pk]['service_status'], 'NO_PURCHASED')
        self.assertEqual(rows[unpaid.pk]['service_status'], 'NO_PURCHASED')
        analyst_ids = {row['id'] for row in self.read_as(self.analyst, '/api/admin/users/').data}
        self.assertEqual(analyst_ids, {paid.pk, waiting.pk, broken.pk})

    def test_invalid_paid_participant_ownership_fails_closed_across_reads(self):
        owner = User.objects.create_user(username='bad-participant-owner')
        other = User.objects.create_user(username='bad-participant-other')
        Profile.objects.create(user=owner)
        purchase = self.paid_service(owner, 'COMPLETED')
        participant = Participant.objects.create(user=other, participant_code='bad-owner')
        ServiceRequest.objects.filter(purchase=purchase).update(participant=participant)
        admin_rows = {row['id']: row for row in self.read_as(self.admin, '/api/admin/users/').data}
        self.assertEqual(admin_rows[owner.pk]['service_status'], 'NO_PURCHASED')
        self.assertEqual(self.read_as(self.admin, '/api/admin/stats/').data['analysis_count'], 0)

        # Even after ownership is repaired, a missing initial log or a latest
        # history/status disagreement keeps the service hidden.
        service = ServiceRequest.objects.get(purchase=purchase)
        ServiceRequest.objects.filter(pk=service.pk).update(participant=None)
        ServiceStatusLog.objects.filter(request=service, status=self.waiting).delete()
        rows = {row['id']: row for row in self.read_as(self.admin, '/api/admin/users/').data}
        self.assertEqual(rows[owner.pk]['service_status'], 'NO_PURCHASED')
        ServiceStatusLog.objects.create(
            request=service, status=self.waiting, actor=self.admin.app_user,
            changed_at=self.now + timedelta(seconds=3),
        )
        rows = {row['id']: row for row in self.read_as(self.admin, '/api/admin/users/').data}
        self.assertEqual(rows[owner.pk]['service_status'], 'NO_PURCHASED')
        self.assertEqual(self.read_as(self.analyst, '/api/admin/stats/').data['analysis_count'], 0)

    def test_list_and_stats_query_count_does_not_grow_per_paid_client(self):
        for index in range(18):
            user = User.objects.create_user(username=f'bulk-client-{index}')
            Profile.objects.create(user=user)
            self.paid_service(user)
        for actor, path in (
            (self.admin, '/api/admin/users/'),
            (self.analyst, '/api/admin/users/'),
            (self.admin, '/api/admin/stats/'),
        ):
            with self.subTest(path=path):
                with CaptureQueriesContext(connection) as queries:
                    response = self.read_as(actor, path)
                self.assertEqual(response.status_code, 200, response.data)
                self.assertLessEqual(len(queries), 14, [query['sql'] for query in queries])


class SelfServiceProjectionTests(TestCase):
    def me_as(self, user):
        client = APIClient()
        client.cookies[settings.AUTH_COOKIE_NAME] = encode_jwt({'sub': str(user.pk)})
        response = client.get('/api/auth/me/')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIn('no-store', response['Cache-Control'])
        return response.data['user']

    def test_paid_waiting_service_is_pending_without_results(self):
        user = User.objects.create_user(username='self-paid-waiting')
        Profile.objects.create(user=user, phone='1234567')
        purchase = Purchase.objects.create(
            owner=user.app_user, status=PurchaseStatus.objects.get(code='PAID'),
            purchased_at=timezone.now(),
        )
        service = ServiceRequest.objects.create(
            purchase=purchase, status=RequestStatus.objects.get(code='WAITING_SAMPLE'),
        )
        ServiceStatusLog.objects.create(request=service, status=service.status, actor=user.app_user)
        me = self.me_as(user)
        self.assertEqual((me['service_status'], me['can_view_results']), ('PENDING', False))
        self.assertEqual(ServiceStatusLog.objects.filter(request=service).count(), 1)

    def test_users_without_paid_service_are_not_purchased(self):
        with_profile = User.objects.create_user(username='self-unpaid')
        Profile.objects.create(user=with_profile, phone='unpaid-phone')
        Purchase.objects.create(owner=with_profile.app_user, status=PurchaseStatus.objects.get(code='PENDING'))
        absent = User.objects.create_user(username='no-profile')
        for user in (with_profile, absent):
            with self.subTest(user=user.username):
                me = self.me_as(user)
                self.assertEqual(me['roles'], ['CLIENTE'])
                self.assertEqual((me['service_status'], me['can_view_results']), ('NO_PURCHASED', False))

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
        initial = ServiceStatusLog.objects.create(request=service, status=waiting, actor=user.app_user)
        self.assertEqual(self.me_as(user)['service_status'], 'NO_PURCHASED')  # Latest log disagrees.
        ServiceStatusLog.objects.create(
            request=service, status=completed, actor=user.app_user,
            changed_at=initial.changed_at + timedelta(seconds=1),
        )
        me = self.me_as(user)
        self.assertEqual((me['service_status'], me['can_view_results']), ('COMPLETED', True))

    def test_paid_self_reads_preserve_role_boundary_without_exposing_other_account(self):
        user = User.objects.create_user(username='staff-with-client-role', is_staff=True)
        other = User.objects.create_user(username='other-completed')
        Profile.objects.create(user=other)
        purchase = Purchase.objects.create(
            owner=user.app_user, status=PurchaseStatus.objects.get(code='PAID'),
            purchased_at=timezone.now(),
        )
        service = ServiceRequest.objects.create(
            purchase=purchase, status=RequestStatus.objects.get(code='WAITING_SAMPLE'),
        )
        ServiceStatusLog.objects.create(request=service, status=service.status, actor=user.app_user)
        self.assertIn(APIClient().get('/api/auth/me/').status_code, (401, 403))
        me = self.me_as(user)
        self.assertEqual(me['id'], user.pk)
        self.assertEqual(me['roles'], ['CLIENTE'])
        self.assertEqual(me['user_type'], 'user')
        self.assertFalse(me['is_admin'])
        self.assertTrue(me['is_staff'])
        self.assertEqual((me['service_status'], me['can_view_results']), ('PENDING', False))


class UserAdminStatusTests(TestCase):
    def test_list_and_profile_inline_show_newest_paid_status(self):
        operator = User.objects.create_superuser(username='status-super', password='test-only')
        target = User.objects.create_user(username='status-target')
        profile = Profile.objects.create(user=target, phone='old phone')
        waiting = RequestStatus.objects.get(code='WAITING_SAMPLE')
        paid = PurchaseStatus.objects.get(code='PAID')
        older = Purchase.objects.create(
            owner=target.app_user, status=paid, purchased_at=timezone.now() - timedelta(days=1),
        )
        newer = Purchase.objects.create(owner=target.app_user, status=paid, purchased_at=timezone.now())
        completed = RequestStatus.objects.get(code='COMPLETED')
        for purchase, state in ((older, completed), (newer, waiting)):
            started = timezone.now()
            service = ServiceRequest.objects.create(
                purchase=purchase, status=state, started_at=started,
                completed_at=started + timedelta(seconds=1) if state == completed else None,
            )
            ServiceStatusLog.objects.create(request=service, status=waiting, actor=operator.app_user)
            if state == completed:
                ServiceStatusLog.objects.create(request=service, status=completed, actor=operator.app_user)
        Purchase.objects.create(owner=target.app_user, status=PurchaseStatus.objects.get(code='PENDING'))
        self.client.force_login(operator)

        listing = self.client.get(reverse('admin:auth_user_changelist'))
        self.assertEqual(listing.status_code, 200)
        admin = listing.context['cl'].model_admin
        self.assertIn('get_service_status', admin.list_display)
        self.assertEqual(admin.get_service_status(target), 'PENDING')
        detail = self.client.get(reverse('admin:auth_user_change', args=[target.pk]))
        self.assertEqual(detail.status_code, 200)
        inline = next(inline for inline in detail.context['inline_admin_formsets']
                      if inline.formset.model is Profile)
        self.assertIn('projected_service_status', inline.readonly_fields)
        self.assertNotIn('service_status', inline.formset.forms[0].fields)
        self.assertContains(detail, 'PENDING')

        payload = {
            'username': target.username, 'first_name': '', 'last_name': '',
            'email': '', 'is_active': 'on', '_save': 'Save',
            'date_joined_0': target.date_joined.strftime('%Y-%m-%d'),
            'date_joined_1': target.date_joined.strftime('%H:%M:%S'),
        }
        for inline in detail.context['inline_admin_formsets']:
            forms = inline.formset
            for name, value in forms.management_form.initial.items():
                payload[f'{forms.prefix}-{name}'] = value
            for index, form in enumerate(forms.initial_forms):
                prefix = f'{forms.prefix}-{index}'
                payload[f'{prefix}-id'] = str(form.instance.pk)
                if isinstance(form.instance, Profile):
                    payload[f'{prefix}-phone'] = 'new phone'
                if isinstance(form.instance, AppUser):
                    payload[f'{prefix}-user_id'] = str(form.instance.pk)
                    payload[f'{prefix}-role'] = str(Role.objects.get(code='ADMIN').pk)
        saved = self.client.post(reverse('admin:auth_user_change', args=[target.pk]), payload)
        self.assertEqual(saved.status_code, 302, saved.context if saved.status_code != 302 else None)
        profile.refresh_from_db()
        self.assertEqual(profile.phone, 'new phone')
        self.assertEqual(AppUser.objects.get(django_user=target).role.code, 'ADMIN')

    def test_unpaid_and_missing_profile_are_not_purchased_in_list(self):
        operator = User.objects.create_superuser(username='fallback-super', password='test-only')
        unpaid = User.objects.create_user(username='fallback-unpaid')
        Profile.objects.create(user=unpaid)
        absent = User.objects.create_user(username='fallback-absent')
        Purchase.objects.create(owner=unpaid.app_user, status=PurchaseStatus.objects.get(code='PENDING'))
        self.client.force_login(operator)
        listing = self.client.get(reverse('admin:auth_user_changelist'))
        self.assertEqual(listing.status_code, 200)
        admin = listing.context['cl'].model_admin
        self.assertEqual(admin.get_service_status(unpaid), 'NO_PURCHASED')
        self.assertEqual(admin.get_service_status(absent), 'NO_PURCHASED')
        self.assertContains(self.client.get(reverse('admin:auth_user_change', args=[unpaid.pk])),
                            'NO_PURCHASED')


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
            {'user_id', 'django_user', 'role', 'oidc_issuer', 'oidc_subject', 'avatar_color', 'avatar_figure', 'username_changed_at'},
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


class MeUpdateTests(TestCase):
    """PATCH auth/me/: the client renames itself or picks a generated avatar, nothing else."""

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.user = User.objects.create_user(username='ana', email='ana@example.com', password='HandleSecret123!')
        self.client.cookies[getattr(settings, 'AUTH_COOKIE_NAME', 'access_token')] = encode_jwt(
            {'sub': str(self.user.id), 'email': self.user.email})
        self.client.get('/api/auth/csrf/')

    def patch(self, payload):
        return self.client.patch('/api/auth/me/', data=json.dumps(payload), content_type='application/json',
                                 HTTP_X_CSRFTOKEN=self.client.cookies['csrftoken'].value)

    def test_renames_and_sets_avatar_and_keeps_the_session(self):
        self.assertEqual(self.client.get('/api/auth/me/').data['user']['avatar'], {'color': 'traits', 'figure': 'initial'})
        response = self.patch({'username': ' Ana.Perez ', 'avatar': {'color': 'monogenic_risk', 'figure': 'helix'}})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['user']['username'], 'ana.perez')
        self.assertEqual(response.data['user']['avatar'], {'color': 'monogenic_risk', 'figure': 'helix'})
        self.assertEqual(self.client.get('/api/auth/me/').status_code, 200)

    def test_rejects_taken_names_bad_input_and_missing_csrf(self):
        User.objects.create_user(username='luis', email='luis@example.com', password='x')
        self.assertEqual(self.patch({'username': 'LUIS'}).status_code, 409)
        for payload in ({'username': 'a'}, {'email': 'x@example.com'}, {},
                        {'avatar': {'color': 'red', 'figure': 'helix'}}, {'avatar': {'color': 'traits'}}):
            with self.subTest(payload=payload):
                self.assertEqual(self.patch(payload).status_code, 400)
        no_csrf = self.client.patch('/api/auth/me/', data=json.dumps({'username': 'otra'}), content_type='application/json')
        self.assertEqual(no_csrf.status_code, 403)
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, 'ana')

    def test_username_changes_once_every_30_days(self):
        self.assertIsNone(self.client.get('/api/auth/me/').data['user']['username_next_change_at'])
        self.assertEqual(self.patch({'username': 'ana.uno'}).status_code, 200)
        me = self.client.get('/api/auth/me/').data['user']
        self.assertIsNotNone(me['username_next_change_at'])

        blocked = self.patch({'username': 'ana.dos'})
        self.assertEqual(blocked.status_code, 429)
        self.assertEqual(blocked.data['username_next_change_at'], me['username_next_change_at'])
        # Saving the same name or only the avatar is not a rename.
        self.assertEqual(self.patch({'username': 'ana.uno', 'avatar': {'color': 'traits', 'figure': 'helix'}}).status_code, 200)

        AppUser.objects.filter(django_user=self.user).update(username_changed_at=timezone.now() - timedelta(days=30, seconds=1))
        self.assertEqual(self.patch({'username': 'ana.dos'}).status_code, 200)
def _unverified_user(username='pending', email='pending@example.com', password='PendingSecret123!'):
    user = User.objects.create_user(username=username, email=email, password=password)
    address = EmailAddress.objects.create(user=user, email=email, primary=True, verified=False)
    return user, address


@override_settings(REQUIRE_EMAIL_VERIFICATION=True)
class UnverifiedLoginGateTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.user, self.address = _unverified_user()

    def login(self, password='PendingSecret123!'):
        return self.client.post('/api/auth/login/', {'username': 'pending', 'password': password}, format='json')

    def test_correct_password_without_a_verified_email_gets_no_session(self):
        response = self.login()
        self.assertEqual(response.status_code, 400)
        self.assertTrue(response.data['requires_verification'])
        self.assertNotIn(settings.AUTH_COOKIE_NAME, response.cookies)
        self.assertIn(self.client.get('/api/auth/me/').status_code, (401, 403))

    def test_confirming_the_email_opens_the_gate(self):
        EmailAddress.objects.filter(pk=self.address.pk).update(verified=True)
        response = self.login()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.cookies[settings.AUTH_COOKIE_NAME]['httponly'])

    def test_a_verified_address_that_is_not_the_account_email_does_not_open_the_gate(self):
        EmailAddress.objects.create(user=self.user, email='other@example.com', verified=True)
        self.assertEqual(self.login().status_code, 400)

    def test_wrong_password_does_not_reveal_the_verification_state(self):
        response = self.login(password='WrongPassword1!')
        self.assertEqual(response.data, {'success': False, 'error': 'Credenciales inválidas'})
        self.assertNotIn('requires_verification', response.data)


@override_settings(REQUIRE_EMAIL_VERIFICATION=True)
@patch('accounts.adapters.send_verification_email', return_value=True)
class ResendVerificationTests(TestCase):
    URL = '/api/auth/register/resend-verification/'

    def setUp(self):
        cache.clear()  # The 'resend' throttle counts across tests otherwise.
        self.client = APIClient()
        self.user, self.address = _unverified_user()

    def resend(self, email='pending@example.com'):
        return self.client.post(self.URL, {'email': email}, format='json')

    def test_unverified_address_gets_exactly_one_new_link(self, send):
        response = self.resend('  Pending@Example.COM ')
        self.assertEqual((response.status_code, response.data), (200, {'success': True}))
        send.assert_called_once()
        self.assertEqual(send.call_args.args[0], 'pending@example.com')
        self.assertIn('/accounts/confirm-email/', send.call_args.args[2])

    def test_unknown_verified_and_pending_addresses_get_the_same_answer(self, send):
        done = User.objects.create_user(username='done', email='done@example.com', password='DoneSecret123!')
        EmailAddress.objects.create(user=done, email='done@example.com', verified=True, primary=True)

        answers = [self.resend(email) for email in ('nobody@example.com', 'done@example.com', 'pending@example.com')]

        self.assertEqual({(a.status_code, json.dumps(a.data)) for a in answers}, {(200, '{"success": true}')})
        send.assert_called_once()  # Only the pending address got a mail.
        self.assertEqual(send.call_args.args[0], 'pending@example.com')

    def test_malformed_requests_reveal_nothing_and_send_nothing(self, send):
        for body in ({}, {'email': None}, {'email': 123}, {'email': ''}, {'email': 'not-an-email'}, ['pending@example.com']):
            with self.subTest(body=body):
                cache.clear()  # Six bodies would trip the 5/min throttle.
                response = self.client.post(self.URL, body, format='json')
                self.assertEqual((response.status_code, response.data), (200, {'success': True}))
        send.assert_not_called()

    def test_delivery_failure_looks_like_success_and_never_logs_the_address(self, send):
        send.return_value = False
        with self.assertLogs(level='WARNING') as logs:
            response = self.resend()
        self.assertEqual((response.status_code, response.data), (200, {'success': True}))
        self.assertNotIn('pending@example.com', '\n'.join(logs.output))
        self.assertIn('example.com', '\n'.join(logs.output))  # The domain is enough to debug a delivery problem.

    def test_resend_is_throttled(self, send):
        statuses = [self.resend().status_code for _ in range(6)]
        self.assertEqual(statuses, [200] * 5 + [429])

    def test_resend_does_not_open_a_session(self, send):
        self.assertNotIn(settings.AUTH_COOKIE_NAME, self.resend().cookies)


@override_settings(REQUIRE_EMAIL_VERIFICATION=True)
class EmailConfirmationLinkTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user, self.address = _unverified_user()

    def key_issued(self, hours_ago):
        with patch('django.core.signing.time.time', return_value=time.time() - hours_ago * 3600):
            return EmailConfirmationHMAC(self.address).key

    def confirm(self, key):
        return self.client.get(f'/accounts/confirm-email/{key}/')

    def test_link_inside_the_lifetime_verifies_without_opening_a_session(self):
        with patch('accounts.signals.send_welcome_email', return_value=True):
            response = self.confirm(self.key_issued(hours_ago=23))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], f"{settings.FRONTEND_DOMAIN.rstrip('/')}/login?verified=1")
        self.assertNotIn(settings.AUTH_COOKIE_NAME, response.cookies)
        self.address.refresh_from_db()
        self.assertTrue(self.address.verified)

    def test_link_older_than_24_hours_does_not_verify(self):
        response = self.confirm(self.key_issued(hours_ago=25))
        self.assertEqual(response.cookies['verification_status'].value, '0')
        self.address.refresh_from_db()
        self.assertFalse(self.address.verified)

    def test_confirmation_sends_the_welcome_exactly_once(self):
        key = self.key_issued(hours_ago=1)
        with patch('accounts.signals.send_welcome_email', return_value=True) as welcome:
            self.confirm(key)
            self.confirm(key)  # A mail scanner or a second click replays the link.
            login = self.client.post(
                '/api/auth/login/', {'username': 'pending', 'password': 'PendingSecret123!'},
                content_type='application/json',
            )
        self.assertEqual(login.status_code, 200)
        welcome.assert_called_once_with(self.user)


@override_settings(REQUIRE_EMAIL_VERIFICATION=True, ALLOWED_EMAIL_DOMAINS='', ACCOUNT_DEFAULT_HTTP_PROTOCOL='https')
class RegistrationLinkTests(TestCase):
    def setUp(self):
        cache.clear()

    @patch('accounts.adapters.send_verification_email', return_value=True)
    def test_registration_sends_one_https_link_and_no_session(self, send):
        mx = [SimpleNamespace(exchange=SimpleNamespace(to_text=lambda: 'mx.example.'))]
        with patch('accounts.email_validation.dns.resolver.resolve', return_value=mx):
            response = self.client.post('/api/auth/register/', {
                'username': 'new_handle', 'correo': 'new@example.com', 'contraseña': 'SecurePassword1!',
                'repetirContraseña': 'SecurePassword1!', 'terminos': True,
            }, content_type='application/json')

        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.data['requires_verification'])
        self.assertNotIn(settings.AUTH_COOKIE_NAME, response.cookies)
        send.assert_called_once()
        self.assertTrue(send.call_args.args[2].startswith('https://'), send.call_args.args[2])
        self.assertFalse(EmailAddress.objects.get(email='new@example.com').verified)
        self.assertTrue(User.objects.get(username='new_handle').is_active)  # The gate is EmailAddress, not is_active.


