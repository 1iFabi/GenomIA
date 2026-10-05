import json
from importlib import import_module
from types import SimpleNamespace
from unittest.mock import patch

from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, User
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.migrations.loader import MigrationLoader
from django.test import TestCase, override_settings
import uuid
from rest_framework.test import APIClient

from .jwt_utils import encode_jwt, decode_jwt
from .models import AppUser, RevokedToken, Role
from .signals import assign_new_user_client_role


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
