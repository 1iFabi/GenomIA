from typing import Optional, Tuple
from django.contrib.auth.models import User
from django.conf import settings
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework import exceptions
from .jwt_utils import decode_jwt
from .models import RevokedToken


class JWTAuthentication(BaseAuthentication):
    """Simple DRF authentication class that reads a Bearer JWT from Authorization header.
    """

    def authenticate(self, request) -> Optional[Tuple[User, str]]:
        # Soporta tanto `Authorization: Bearer <token>` (legacy) como cookie HttpOnly.
        auth = get_authorization_header(request).decode("utf-8")
        token = ""
        if auth and auth.lower().startswith("bearer "):
            token = auth[7:].strip()
        if not token:
            # Fallback: token en cookie HttpOnly (flujo cookie-based, cross-site).
            token = request.COOKIES.get(getattr(settings, "AUTH_COOKIE_NAME", "access_token"), "")
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
            user = User.objects.get(id=user_id, is_active=True)
        except User.DoesNotExist:
            raise exceptions.AuthenticationFailed("User not found")
        return (user, token)
