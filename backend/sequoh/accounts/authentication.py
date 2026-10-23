from typing import Optional, Tuple
from django.contrib.auth.models import User
from django.conf import settings
from django.utils.crypto import constant_time_compare
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework import exceptions
from .csrf import enforce_csrf_double_submit
from .jwt_utils import decode_jwt
from .models import RevokedToken


class JWTAuthentication(BaseAuthentication):
    """Simple DRF authentication class that reads a Bearer JWT from Authorization header.

    A token that arrives in the cookie is an ambient credential, so unsafe methods must also
    pass the CSRF double submit; this covers every view that authenticates with this class.
    """

    def authenticate_header(self, request):
        # With a credential that fails (expired, revoked, ended by a role change) DRF answers 401, which
        # the SPA reads as "session over". Without any credential it keeps answering 403.
        has_credential = request.COOKIES.get(getattr(settings, "AUTH_COOKIE_NAME", "access_token")) or (
            get_authorization_header(request)
        )
        return 'Bearer realm="api"' if has_credential else None

    def authenticate(self, request) -> Optional[Tuple[User, str]]:
        # Soporta tanto `Authorization: Bearer <token>` (legacy) como cookie HttpOnly.
        auth = get_authorization_header(request).decode("utf-8")
        token = ""
        from_cookie = False
        if auth and auth.lower().startswith("bearer "):
            token = auth[7:].strip()
        if not token:
            # Fallback: token en cookie HttpOnly (flujo cookie-based, cross-site).
            token = request.COOKIES.get(getattr(settings, "AUTH_COOKIE_NAME", "access_token"), "")
            from_cookie = bool(token)
        if not token:
            return None
        try:
            payload = decode_jwt(token)
        except Exception as e:
            raise exceptions.AuthenticationFailed("Invalid token")

        sub = payload.get("sub")
        if sub is None:
            raise exceptions.AuthenticationFailed("Invalid token payload")
        # Validar sub como entero positivo antes de consultar la BD.
        try:
            user_id = int(sub)
        except (TypeError, ValueError):
            raise exceptions.AuthenticationFailed("Invalid token payload")
        if user_id <= 0:
            raise exceptions.AuthenticationFailed("Invalid token payload")

        # Revocación: token cuyo jti está en la blacklist.
        jti = payload.get("jti")
        if jti and RevokedToken.objects.filter(jti=jti).exists():
            raise exceptions.AuthenticationFailed("Token revoked")

        try:
            # Filtrar is_active=True: un usuario desactivado pierde acceso de inmediato.
            user = User.objects.select_related("app_user").get(id=user_id, is_active=True)
        except User.DoesNotExist:
            raise exceptions.AuthenticationFailed("User not found")
        # Login cookies carry the password-bound hash; a password change invalidates them.
        sah = payload.get("sah")
        if sah is not None and not constant_time_compare(sah, user.get_session_auth_hash()):
            raise exceptions.AuthenticationFailed("Session ended by password change")
        # A role change bumps the version, which ends the sessions issued before it.
        # shortcut: tokens issued before the claim existed carry no `tv` and skip this check;
        # they all expire within JWT_EXPIRATION_HOURS of the deploy, then require it.
        tv = payload.get("tv")
        if tv is not None and tv != getattr(getattr(user, "app_user", None), "token_version", 0):
            raise exceptions.AuthenticationFailed("Session ended by role change")
        if from_cookie:
            enforce_csrf_double_submit(request, payload.get("jti"))
        return (user, token)
