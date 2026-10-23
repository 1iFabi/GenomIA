import hmac
import secrets

import jwt
from django.conf import settings
from django.utils.crypto import salted_hmac
from rest_framework.exceptions import PermissionDenied

from .audit import audit
from .jwt_utils import decode_jwt

SAFE_METHODS = frozenset(("GET", "HEAD", "OPTIONS", "TRACE"))
# Readable by the SPA, which echoes it as X-CSRFToken. Django's own `csrftoken` stays with the admin.
CSRF_COOKIE_NAME = "genomia_csrf"


def _mac(jti, nonce):
    message = f"{len(jti)}!{jti}!{nonce}"
    return salted_hmac("accounts.csrf", message, secret=settings.JWT_SECRET_KEY, algorithm="sha256").hexdigest()


def session_csrf_token(jti):
    """OWASP signed double submit: an HMAC bound to the session (the token's jti) plus a random nonce."""
    nonce = secrets.token_urlsafe(16)
    return f"{_mac(jti, nonce)}.{nonce}"


def csrf_token_for(jwt_token):
    """Signed CSRF token for an already encoded session JWT (tests and tools that build their own sessions)."""
    return session_csrf_token(decode_jwt(jwt_token)["jti"])


def set_csrf_cookie(response, jti):
    response.set_cookie(
        CSRF_COOKIE_NAME, session_csrf_token(jti), path="/",
        samesite=getattr(settings, "AUTH_COOKIE_SAMESITE", "Lax"),
        secure=bool(getattr(settings, "AUTH_COOKIE_SECURE", False)),
    )
    return response


def cookie_session_jti(request):
    """jti of a valid session cookie, or None when the request carries no usable cookie session."""
    token = request.COOKIES.get(getattr(settings, "AUTH_COOKIE_NAME", "access_token"))
    if not token:
        return None
    try:
        return decode_jwt(token).get("jti")
    except jwt.PyJWTError:
        return None


def enforce_csrf_double_submit(request, jti):
    """Unsafe requests of a cookie session must send ``X-CSRFToken`` signed for that same session."""
    if request.method.upper() in SAFE_METHODS:
        return
    mac, _, nonce = (request.headers.get("X-CSRFToken") or "").partition(".")
    if not jti or not nonce or not hmac.compare_digest(mac, _mac(jti, nonce)):
        audit("csrf_rejected", request, method=request.method.upper(), path=request.path)
        raise PermissionDenied("CSRF check failed")


class CSRFDoubleSubmitMixin:
    """Same check for views that may run without ``JWTAuthentication`` (logout); it also enforces it itself.

    Without a valid cookie session there is no ambient credential to abuse, so there is nothing to check.
    """

    SAFE_METHODS = SAFE_METHODS

    def initial(self, request, *args, **kwargs):
        jti = cookie_session_jti(request)
        if jti:
            enforce_csrf_double_submit(request, jti)
        return super().initial(request, *args, **kwargs)
