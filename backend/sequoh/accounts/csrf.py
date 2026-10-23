import hmac

from rest_framework.exceptions import PermissionDenied

SAFE_METHODS = frozenset(("GET", "HEAD", "OPTIONS", "TRACE"))


def enforce_csrf_double_submit(request):
    """Exige una cookie CSRF y un encabezado ``X-CSRFToken`` coincidentes en solicitudes inseguras."""
    if request.method.upper() in SAFE_METHODS:
        return
    cookie_token = request.COOKIES.get("csrftoken")
    header_token = request.headers.get("X-CSRFToken")
    if (
        not cookie_token
        or not header_token
        or not hmac.compare_digest(cookie_token.encode("utf-8"), header_token.encode("utf-8"))
    ):
        raise PermissionDenied("CSRF check failed")


class CSRFDoubleSubmitMixin:
    """Same check for views that do not authenticate through ``JWTAuthentication`` (which enforces it itself)."""

    SAFE_METHODS = SAFE_METHODS

    def initial(self, request, *args, **kwargs):
        enforce_csrf_double_submit(request)
        return super().initial(request, *args, **kwargs)
