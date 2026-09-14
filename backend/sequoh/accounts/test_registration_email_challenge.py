import base64
import json
from email import policy
from email.parser import BytesParser
from email.utils import parseaddr
from types import SimpleNamespace
from unittest.mock import Mock, patch

import dns.exception
import dns.resolver
from allauth.account.models import EmailAddress
from django.contrib.auth.models import User
from django.contrib.sites.models import Site
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from profiles.models import Profile, validate_rut_format
from . import email_utils
from .email_validation import (
    configured_allowed_email_domains,
    is_valid_registration_name,
    validate_registration_email,
)


class RegistrationEmailValidationTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.client.defaults['REMOTE_ADDR'] = '10.0.0.1'
        Site.objects.get_or_create(pk=1, defaults={'domain': 'example.com', 'name': 'example'})

    @staticmethod
    def _mx_answer():
        return [SimpleNamespace(exchange=SimpleNamespace(to_text=lambda: 'mx.example.'))]

    def _post_validation(self, email):
        return self.client.post(
            '/api/auth/register/email-validation/',
            data=json.dumps({'email': email}),
            content_type='application/json',
        )

    def _registration_payload(self, email='person@example.com', username='person_handle'):
        return {
            'username': username,
            'correo': email,
            'telefono': '+56912345678',
            'contraseña': 'SecurePassword1!',
            'repetirContraseña': 'SecurePassword1!',
            'terminos': True,
        }

    @override_settings(
        BLOCKED_EMAIL_DOMAINS='Blocked.COM',
        ALLOWED_EMAIL_DOMAINS='',
    )
    def test_blocked_domains_match_exact_normalized_domain_only(self):
        blocked = validate_registration_email(' Person@BLOCKED.com. ', check_mx=False)
        subdomain = validate_registration_email('person@mail.blocked.com', check_mx=False)

        self.assertFalse(blocked.valid)
        self.assertEqual(blocked.error_code, 'blocked_domain')
        self.assertTrue(subdomain.valid)
        self.assertEqual(subdomain.domain, 'mail.blocked.com')

    @override_settings(
        ALLOWED_EMAIL_DOMAINS='pregrado.uoh.cl',
        EMAIL_VALIDATION_DNS_FALLBACK_NAMESERVERS='1.1.1.1,8.8.8.8',
        EMAIL_VALIDATION_DNS_TIMEOUT_SECONDS=1.25,
    )
    def test_mx_fallback_accepts_uoh_domain_after_system_no_answer(self):
        fallback_resolver = Mock()
        fallback_resolver.resolve.return_value = self._mx_answer()
        with patch(
            'accounts.email_validation.dns.resolver.resolve',
            side_effect=dns.resolver.NoAnswer,
        ) as system_resolve, patch(
            'accounts.email_validation.dns.resolver.Resolver',
            return_value=fallback_resolver,
        ) as resolver_factory:
            result = validate_registration_email('person@pregrado.uoh.cl')

        self.assertTrue(result.valid)
        system_resolve.assert_called_once_with(
            'pregrado.uoh.cl',
            'MX',
            lifetime=1.25,
        )
        resolver_factory.assert_called_once_with(configure=False)
        self.assertEqual(fallback_resolver.nameservers, ['1.1.1.1', '8.8.8.8'])
        fallback_resolver.resolve.assert_called_once_with(
            'pregrado.uoh.cl',
            'MX',
            lifetime=1.25,
        )

    @override_settings(
        ALLOWED_EMAIL_DOMAINS='pregrado.uoh.cl',
        EMAIL_VALIDATION_DNS_FALLBACK_NAMESERVERS='',
        EMAIL_VALIDATION_DNS_TIMEOUT_SECONDS=999,
    )
    def test_mx_fallback_is_disabled_and_timeout_remains_bounded(self):
        with patch(
            'accounts.email_validation.dns.resolver.resolve',
            side_effect=dns.resolver.NoAnswer,
        ) as system_resolve, patch(
            'accounts.email_validation.dns.resolver.Resolver',
        ) as resolver_factory:
            result = validate_registration_email('person@pregrado.uoh.cl')

        self.assertFalse(result.valid)
        self.assertEqual(result.error_code, 'no_mx')
        system_resolve.assert_called_once_with(
            'pregrado.uoh.cl',
            'MX',
            lifetime=10.0,
        )
        resolver_factory.assert_not_called()

    @override_settings(ALLOWED_EMAIL_DOMAINS='')
    def test_email_normalization_trims_lowercases_and_applies_idna(self):
        result = validate_registration_email('  USER@BÜCHER.Example.  ', check_mx=False)

        self.assertTrue(result.valid)
        self.assertEqual(result.normalized_email, 'user@xn--bcher-kva.example')
        self.assertEqual(result.domain, 'xn--bcher-kva.example')

    @override_settings(
        ALLOWED_EMAIL_DOMAINS=('GMAIL.COM', 'BÜCHER.Example', None, '', 'bad domain', '@bad')
    )
    def test_configured_allowed_domains_normalize_iterables_and_ignore_malformed_entries(self):
        self.assertEqual(
            configured_allowed_email_domains(),
            frozenset({'gmail.com', 'xn--bcher-kva.example'}),
        )

    @override_settings(ALLOWED_EMAIL_DOMAINS='allowed.example')
    def test_allowed_domains_match_exactly_without_suffix_matching(self):
        allowed = validate_registration_email('person@allowed.example', check_mx=False)
        subdomain = validate_registration_email('person@mail.allowed.example', check_mx=False)

        self.assertTrue(allowed.valid)
        self.assertFalse(subdomain.valid)
        self.assertEqual(subdomain.error_code, 'domain_not_allowed')

    @override_settings(ALLOWED_EMAIL_DOMAINS='BÜCHER.Example')
    def test_allowed_domains_apply_idna_normalization(self):
        result = validate_registration_email('USER@BÜCHER.Example.', check_mx=False)

        self.assertTrue(result.valid)
        self.assertEqual(result.normalized_email, 'user@xn--bcher-kva.example')

    @override_settings(BLOCKED_EMAIL_DOMAINS='blocked.com', ALLOWED_EMAIL_DOMAINS='allowed.com')
    def test_blocklist_is_checked_before_allowlist_and_mx(self):
        with patch('accounts.email_validation._has_usable_mx') as has_mx:
            result = validate_registration_email('person@blocked.com')

        self.assertFalse(result.valid)
        self.assertEqual(result.error_code, 'blocked_domain')
        has_mx.assert_not_called()

    @override_settings(ALLOWED_EMAIL_DOMAINS='')
    def test_empty_allowlist_allows_custom_domains(self):
        result = validate_registration_email('person@example.com', check_mx=False)

        self.assertTrue(result.valid)

    def test_registration_names_accept_unicode_words_and_allowed_separators(self):
        valid_names = ('Ana', 'María', 'Ana María', 'Ana-María', "O'Connor", 'D’Angelo')
        invalid_names = ('Ana2', 'Ana!', 'Ana_María', '-Ana', 'Ana-', 'Ana  María', 'Ana/Maria')

        for name in valid_names:
            with self.subTest(name=name):
                self.assertTrue(is_valid_registration_name(name))
        for name in invalid_names:
            with self.subTest(name=name):
                self.assertFalse(is_valid_registration_name(name))

    def test_profile_rut_validator_accepts_optional_values(self):
        self.assertIsNone(validate_rut_format(None))
        self.assertEqual(validate_rut_format(''), '')
        validate_rut_format('12345678-9')
        with self.assertRaises(ValidationError):
            validate_rut_format('invalid-rut')

    @override_settings(
        BLOCKED_EMAIL_DOMAINS='blocked.com',
        ALLOWED_EMAIL_DOMAINS='mail.blocked.com',
    )
    def test_validation_endpoint_returns_normalized_allowed_subdomain(self):
        with patch('accounts.email_validation.dns.resolver.resolve', return_value=self._mx_answer()):
            response = self._post_validation('  USER@mail.BLOCKED.com  ')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {
            'valid': True,
            'normalized_email': 'user@mail.blocked.com',
        })

    @override_settings(
        BLOCKED_EMAIL_DOMAINS='blocked.com',
        ALLOWED_EMAIL_DOMAINS='',
    )
    def test_validation_endpoint_uses_generic_message_for_malformed_and_blocked_email(self):
        for email in ('not-an-email', 'user@blocked.com'):
            with self.subTest(email=email):
                response = self._post_validation(email)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.data, {'error': 'El correo no es válido.'})

    @override_settings(ALLOWED_EMAIL_DOMAINS='gmail.com')
    def test_validation_endpoint_rejects_non_allowlisted_domain_with_generic_error(self):
        with patch('accounts.email_validation.dns.resolver.resolve') as resolve:
            response = self._post_validation('user@example.com')

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data, {'error': 'El correo no es válido.'})
        resolve.assert_not_called()

    @override_settings(ALLOWED_EMAIL_DOMAINS='')
    def test_validation_endpoint_uses_generic_message_when_domain_check_is_unavailable(self):
        with patch(
            'accounts.email_validation.dns.resolver.resolve',
            side_effect=dns.exception.Timeout,
        ):
            response = self._post_validation('user@example.com')

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data, {'error': 'El correo no es válido.'})

    @override_settings(
        BLOCKED_EMAIL_DOMAINS='blocked.com',
        ALLOWED_EMAIL_DOMAINS='',
        REQUIRE_EMAIL_VERIFICATION=False,
    )
    def test_final_registration_rejects_blocked_domain_server_side(self):
        response = self.client.post(
            '/api/auth/register/',
            data=json.dumps(self._registration_payload('user@blocked.com')),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data, {'error': 'El correo no es válido.'})
        self.assertEqual(User.objects.count(), 0)

    @override_settings(ALLOWED_EMAIL_DOMAINS='gmail.com', REQUIRE_EMAIL_VERIFICATION=False)
    def test_final_registration_revalidates_allowlist_server_side(self):
        with patch('accounts.email_validation.dns.resolver.resolve') as resolve:
            response = self.client.post(
                '/api/auth/register/',
                data=json.dumps(self._registration_payload('user@example.com')),
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data, {'error': 'El correo no es válido.'})
        self.assertEqual(User.objects.count(), 0)
        resolve.assert_not_called()

    @override_settings(
        ALLOWED_EMAIL_DOMAINS='pregrado.uoh.cl',
        REQUIRE_EMAIL_VERIFICATION=True,
    )
    @patch('accounts.adapters.send_verification_email', return_value=True)
    def test_final_registration_with_uoh_mx_returns_201_with_verification_enabled(self, _send_verification):
        with patch('accounts.email_validation.dns.resolver.resolve', return_value=self._mx_answer()):
            response = self.client.post(
                '/api/auth/register/',
                data=json.dumps(self._registration_payload('fabian.ayala@pregrado.uoh.cl')),
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.data['requires_verification'])
        self.assertTrue(
            EmailAddress.objects.filter(
                email='fabian.ayala@pregrado.uoh.cl',
                verified=False,
                primary=True,
            ).exists()
        )
        _send_verification.assert_called_once()

    @override_settings(
        ALLOWED_EMAIL_DOMAINS='pregrado.uoh.cl',
        REQUIRE_EMAIL_VERIFICATION=True,
    )
    @patch('accounts.adapters.send_verification_email', return_value=False)
    def test_registration_rolls_back_user_and_profile_when_verification_delivery_fails(
        self, _send_verification
    ):
        with patch('accounts.email_validation.dns.resolver.resolve', return_value=self._mx_answer()):
            response = self.client.post(
                '/api/auth/register/',
                data=json.dumps(self._registration_payload('fabian.ayala@pregrado.uoh.cl')),
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data, {
            'error': 'No pudimos enviar el correo de verificación. Inténtalo nuevamente.',
            'email_delivery_failed': True,
        })
        self.assertEqual(User.objects.count(), 0)
        self.assertEqual(Profile.objects.count(), 0)
        self.assertEqual(EmailAddress.objects.count(), 0)
        self.assertNotIn('provider', response.content.decode().lower())
        self.assertNotIn('gmail', response.content.decode().lower())
        _send_verification.assert_called_once()

    @override_settings(
        ALLOWED_EMAIL_DOMAINS='',
        REQUIRE_EMAIL_VERIFICATION=True,
    )
    @patch('accounts.adapters.GmailAPIAccountAdapter.send_mail')
    def test_final_registration_keeps_allauth_confirmation_without_numeric_proof(self, _send_mail):
        with patch('accounts.email_validation.dns.resolver.resolve', return_value=self._mx_answer()):
            response = self.client.post(
                '/api/auth/register/',
                data=json.dumps(self._registration_payload('  USER@example.com  ')),
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.data['requires_verification'])
        user = User.objects.get(email='user@example.com')
        email_address = EmailAddress.objects.get(user=user, email='user@example.com')
        self.assertFalse(email_address.verified)
        self.assertTrue(email_address.primary)

    @override_settings(
        ALLOWED_EMAIL_DOMAINS='',
        REQUIRE_EMAIL_VERIFICATION=False,
    )
    @patch('accounts.views.send_welcome_email', return_value=True)
    def test_final_registration_rejects_invalid_name_format(self, _send_welcome):
        payload = self._registration_payload()
        payload['nombre'] = 'Ana2'
        with patch('accounts.email_validation.dns.resolver.resolve', return_value=self._mx_answer()):
            response = self.client.post(
                '/api/auth/register/',
                data=json.dumps(payload),
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['error'], 'El nombre no es válido')
        self.assertEqual(User.objects.count(), 0)

    @override_settings(REQUIRE_EMAIL_VERIFICATION=False)
    def test_final_registration_returns_generic_email_error_when_email_is_missing(self):
        payload = self._registration_payload(email='')
        response = self.client.post(
            '/api/auth/register/',
            data=json.dumps(payload),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['error'], 'El correo no es válido.')
        self.assertEqual(User.objects.count(), 0)

    @override_settings(ALLOWED_EMAIL_DOMAINS='', REQUIRE_EMAIL_VERIFICATION=False)
    @patch('accounts.views.send_welcome_email', return_value=True)
    def test_final_registration_accepts_frontend_payload_without_legacy_fields(self, _send_welcome):
        payload = self._registration_payload(
            email='  USER@example.com  ',
            username='  Ana.User-1  ',
        )
        with patch('accounts.email_validation.dns.resolver.resolve', return_value=self._mx_answer()):
            response = self.client.post(
                '/api/auth/register/',
                data=json.dumps(payload),
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 201)
        user = User.objects.get(email='user@example.com')
        self.assertEqual(user.username, 'ana.user-1')
        self.assertEqual(user.first_name, '')
        self.assertEqual(user.last_name, '')
        profile = Profile.objects.get(user=user)
        self.assertEqual(profile.phone, '+56912345678')
        self.assertIsNone(profile.rut)
        self.assertEqual(response.data['username'], 'ana.user-1')

    @override_settings(REQUIRE_EMAIL_VERIFICATION=False)
    def test_final_registration_requires_username(self):
        payload = self._registration_payload()
        payload.pop('username')

        response = self.client.post(
            '/api/auth/register/',
            data=json.dumps(payload),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('nombre de usuario', response.data['error'].lower())
        self.assertEqual(User.objects.count(), 0)

    @override_settings(REQUIRE_EMAIL_VERIFICATION=False)
    def test_final_registration_rejects_invalid_username(self):
        payload = self._registration_payload(username='ab!')

        response = self.client.post(
            '/api/auth/register/',
            data=json.dumps(payload),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('nombre de usuario', response.data['error'].lower())
        self.assertEqual(User.objects.count(), 0)

    @override_settings(ALLOWED_EMAIL_DOMAINS='', REQUIRE_EMAIL_VERIFICATION=False)
    def test_final_registration_rejects_duplicate_username_case_insensitively(self):
        User.objects.create_user(
            username='existing_handle',
            email='existing@example.com',
            password='SecurePassword1!',
        )
        payload = self._registration_payload(
            email='new@example.com',
            username=' EXISTING_HANDLE ',
        )
        with patch('accounts.email_validation.dns.resolver.resolve', return_value=self._mx_answer()):
            response = self.client.post(
                '/api/auth/register/',
                data=json.dumps(payload),
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data, {
            'error': 'Este nombre de usuario ya está registrado',
            'username_exists': True,
        })

    @override_settings(ALLOWED_EMAIL_DOMAINS='', REQUIRE_EMAIL_VERIFICATION=False)
    def test_final_registration_rejects_duplicate_email_case_insensitively(self):
        User.objects.create_user(
            username='another_handle',
            email='existing@example.com',
            password='SecurePassword1!',
        )
        payload = self._registration_payload(
            email=' EXISTING@EXAMPLE.COM ',
            username='new_handle',
        )
        with patch('accounts.email_validation.dns.resolver.resolve', return_value=self._mx_answer()):
            response = self.client.post(
                '/api/auth/register/',
                data=json.dumps(payload),
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data, {
            'error': 'Este correo ya está registrado',
            'email_exists': True,
        })

    @override_settings(ALLOWED_EMAIL_DOMAINS='', REQUIRE_EMAIL_VERIFICATION=False)
    @patch('accounts.views.send_welcome_email', return_value=True)
    def test_final_registration_stores_optional_legacy_fields_when_valid(self, _send_welcome):
        payload = self._registration_payload()
        payload.update({
            'nombre': '  Ana María  ',
            'apellido': "  O'Connor  ",
            'rut': '12345678-k',
        })
        with patch('accounts.email_validation.dns.resolver.resolve', return_value=self._mx_answer()):
            response = self.client.post(
                '/api/auth/register/',
                data=json.dumps(payload),
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 201)
        user = User.objects.get(username='person_handle')
        self.assertEqual(user.first_name, 'Ana María')
        self.assertEqual(user.last_name, "O'Connor")
        self.assertEqual(Profile.objects.get(user=user).rut, '12345678-K')

    @override_settings(ALLOWED_EMAIL_DOMAINS='', REQUIRE_EMAIL_VERIFICATION=False)
    @patch('accounts.views.send_welcome_email', return_value=True)
    def test_final_registration_rejects_invalid_legacy_rut_when_supplied(self, _send_welcome):
        payload = self._registration_payload()
        payload['rut'] = 'invalid-rut'
        with patch('accounts.email_validation.dns.resolver.resolve', return_value=self._mx_answer()):
            response = self.client.post(
                '/api/auth/register/',
                data=json.dumps(payload),
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn('RUT', response.data['error'])
        self.assertEqual(User.objects.count(), 0)


class GmailVerificationDeliveryTests(TestCase):
    @staticmethod
    def _message_from_service(service):
        send_call = service.users.return_value.messages.return_value.send.call_args
        raw = send_call.kwargs['body']['raw']
        return BytesParser(policy=policy.default).parsebytes(base64.urlsafe_b64decode(raw))

    @staticmethod
    def _successful_gmail_service():
        service = Mock()
        service.users.return_value.messages.return_value.send.return_value.execute.return_value = {
            'id': 'message-id',
        }
        return service

    @override_settings(DEFAULT_FROM_EMAIL='')
    def test_send_email_uses_non_empty_sender_fallback_when_default_is_blank(self):
        service = self._successful_gmail_service()
        with patch('accounts.email_utils.get_gmail_service', return_value=service):
            result = email_utils.send_email(
                to_email='recipient@example.com',
                subject='Verification',
                text_body='Verify your account.',
                from_email='',
            )

        self.assertTrue(result)
        message = self._message_from_service(service)
        sender_name, sender_address = parseaddr(message['From'])
        self.assertTrue(message['From'])
        self.assertEqual(sender_name, 'GenomIA')
        self.assertEqual(sender_address, 'seqgenomia@gmail.com')

    @override_settings(DEFAULT_FROM_EMAIL='')
    def test_send_verification_email_uses_sender_fallback(self):
        service = self._successful_gmail_service()
        with patch('accounts.email_utils.get_gmail_service', return_value=service), patch(
            'accounts.email_utils.load_logo_bytes', return_value=None
        ):
            result = email_utils.send_verification_email(
                'recipient@example.com',
                'Recipient',
                'https://example.com/verify',
            )

        self.assertTrue(result)
        message = self._message_from_service(service)
        sender_name, sender_address = parseaddr(message['From'])
        self.assertEqual(sender_name, 'Genomia')
        self.assertEqual(sender_address, 'seqgenomia@gmail.com')

    @override_settings(DEFAULT_FROM_EMAIL='')
    def test_provider_failure_returns_false_without_logging_credentials(self):
        service = Mock()
        service.users.return_value.messages.return_value.send.return_value.execute.side_effect = RuntimeError(
            'refresh_token=do-not-log'
        )

        with patch('accounts.email_utils.get_gmail_service', return_value=service), self.assertLogs(
            'accounts.email_utils', level='ERROR'
        ) as captured:
            result = email_utils.send_email(
                to_email='recipient@example.com',
                subject='Verification',
                text_body='Verify your account.',
                from_email='',
            )

        self.assertFalse(result)
        logs = '\n'.join(captured.output)
        self.assertNotIn('do-not-log', logs)
        self.assertNotIn('refresh_token', logs)
