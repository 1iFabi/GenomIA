import json
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from .jwt_utils import encode_jwt, decode_jwt
from .models import RevokedToken


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

    def _login(self, remember=False):
        return self.client.post(
            "/api/auth/login/",
            data=json.dumps({"username": self.username, "password": self.password, "remember": remember}),
            content_type="application/json",
        )

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
