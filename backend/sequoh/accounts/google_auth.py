"""Google Sign-In (ID token from the GIS button) coexisting with password accounts.

Identity key is Google's `sub` stored in AppUser.oidc_*; the email is never used to match accounts.
New Google users get a short signed token and must pick a username before the account exists.
"""
import logging
import time

from allauth.account.models import EmailAddress
from django.conf import settings
from django.contrib.auth.models import User
from django.core import signing
from django.db import IntegrityError, transaction
from django.utils import timezone
from google.auth.exceptions import GoogleAuthError
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .email_utils import send_welcome_email
from .models import AppUser, WelcomeStatus
from .username_validation import normalize_registration_username
from .views import issue_auth_cookie

logger = logging.getLogger(__name__)

GOOGLE_ISSUER = 'https://accounts.google.com'
SIGNUP_SALT = 'accounts.google-signup'
SIGNUP_MAX_AGE_SECONDS = 600
INVALID_GOOGLE = {"error": "No pudimos validar tu cuenta de Google. Inténtalo nuevamente."}


def verify_google_credential(credential):
    """Return the verified ID-token claims, or None. Checks signature, iss, exp, aud and email_verified."""
    client_id = getattr(settings, 'GOOGLE_CLIENT_ID', '')
    if not client_id:
        logger.error("Google sign-in rejected: GOOGLE_CLIENT_ID is not configured (restart after editing .env)")
        return None
    if not isinstance(credential, str) or not credential:
        logger.warning("Google sign-in rejected: missing credential")
        return None
    try:
        # ponytail: Google certs are fetched per call; wrap the session with cachecontrol if login latency matters.
        claims = google_id_token.verify_oauth2_token(credential, google_requests.Request(), client_id)
    except (ValueError, GoogleAuthError) as exc:
        # The library message names the failed check (audience, expiry, issuer); it never contains the token.
        logger.warning("Google sign-in rejected: %s", exc)
        return None
    if not (claims.get('sub') and claims.get('email') and claims.get('email_verified') is True):
        logger.warning("Google sign-in rejected: email missing or not verified")
        return None
    return claims


REAUTH_MAX_AGE_SECONDS = 300


def is_fresh_google_reauth(user, credential):
    """True when `credential` is a Google ID token for this user's linked account, issued < 5 min ago."""
    claims = verify_google_credential(credential)
    if claims is None or time.time() - int(claims.get('iat', 0)) > REAUTH_MAX_AGE_SECONDS:
        return False
    return AppUser.objects.filter(
        django_user=user, oidc_issuer=GOOGLE_ISSUER, oidc_subject=claims['sub'],
    ).exists()


def _email_taken_response():
    return Response({
        "error": "Ya existe una cuenta con este correo. Inicia sesión para continuar.",
        "email_exists": True,
    }, status=status.HTTP_409_CONFLICT)


class GoogleLoginAPIView(APIView):
    """Login if the Google account is linked; otherwise ask for a username (nothing is stored yet)."""
    authentication_classes = []
    permission_classes = []
    throttle_scope = 'login'

    def post(self, request):
        data = request.data if isinstance(request.data, dict) else {}
        claims = verify_google_credential(data.get('credential'))
        if claims is None:
            return Response(INVALID_GOOGLE, status=status.HTTP_400_BAD_REQUEST)

        mapping = AppUser.objects.select_related('django_user').filter(
            oidc_issuer=GOOGLE_ISSUER, oidc_subject=claims['sub'],
        ).first()
        if mapping:
            # A sign-up from the register page must not open an account that already exists.
            if data.get('intent') == 'signup':
                return _email_taken_response()
            if not mapping.django_user.is_active:
                return Response(INVALID_GOOGLE, status=status.HTTP_400_BAD_REQUEST)
            resp = Response({"mensaje": "Inicio de sesión exitoso", "success": True})
            return issue_auth_cookie(resp, mapping.django_user, remember=bool(data.get('remember', False)))

        email = claims['email'].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            return _email_taken_response()

        pending = signing.dumps({
            'sub': claims['sub'],
            'email': email,
            'given_name': claims.get('given_name', ''),
            'family_name': claims.get('family_name', ''),
        }, salt=SIGNUP_SALT)
        return Response({"needs_username": True, "pending": pending, "email": email})


class GoogleCompleteSignupAPIView(APIView):
    """Create the Google account once the user picks a username and accepts the terms."""
    authentication_classes = []
    permission_classes = []
    throttle_scope = 'register'

    def post(self, request):
        data = request.data if isinstance(request.data, dict) else {}
        try:
            pending = signing.loads(data.get('pending') or '', salt=SIGNUP_SALT, max_age=SIGNUP_MAX_AGE_SECONDS)
        except signing.BadSignature:  # Includes SignatureExpired.
            return Response({"error": "Tu sesión de Google expiró. Vuelve a ingresar con Google."},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            username = normalize_registration_username(data.get('username'))
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        if data.get('terminos') is not True:
            return Response({"error": "Debes aceptar los términos y condiciones"}, status=status.HTTP_400_BAD_REQUEST)

        username_taken = {"error": "Este nombre de usuario ya está registrado", "username_exists": True}
        if User.objects.filter(username__iexact=username).exists():
            return Response(username_taken, status=status.HTTP_400_BAD_REQUEST)
        if User.objects.filter(email__iexact=pending['email']).exists():
            return _email_taken_response()

        try:
            with transaction.atomic():
                # No password: Google accounts get an unusable one (password reset can set one later).
                user = User.objects.create_user(
                    username=username, email=pending['email'],
                    first_name=pending['given_name'][:150], last_name=pending['family_name'][:150],
                )
                # The post_save signal already created the CLIENTE mapping; the role never comes from the request.
                AppUser.objects.filter(django_user=user).update(
                    oidc_issuer=GOOGLE_ISSUER, oidc_subject=pending['sub'],
                )
                EmailAddress.objects.create(user=user, email=pending['email'], verified=True, primary=True)
        except IntegrityError:
            if User.objects.filter(username__iexact=username).exists():
                return Response(username_taken, status=status.HTTP_400_BAD_REQUEST)
            # Same Google sub or email registered concurrently.
            return _email_taken_response()

        if send_welcome_email(user):
            WelcomeStatus.objects.update_or_create(
                user=user, defaults={"welcome_sent": True, "sent_at": timezone.now()},
            )
        else:
            logger.warning("Google signup welcome email not sent (user=%s)", user.pk)

        resp = Response({"mensaje": "Cuenta creada", "success": True, "username": user.username},
                        status=status.HTTP_201_CREATED)
        return issue_auth_cookie(resp, user)
