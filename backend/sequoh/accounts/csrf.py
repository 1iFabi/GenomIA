import hmac

from rest_framework.exceptions import PermissionDenied


class CSRFDoubleSubmitMixin:
    """Exige una cookie CSRF y un encabezado ``X-CSRFToken`` coincidentes en solicitudes inseguras."""

    SAFE_METHODS = frozenset(("GET", "HEAD", "OPTIONS", "TRACE"))

    def initial(self, request, *args, **kwargs):
        if request.method.upper() not in self.SAFE_METHODS:
            cookie_token = request.COOKIES.get("csrftoken")
            header_token = request.headers.get("X-CSRFToken")
            if (
                not cookie_token
                or not header_token
                or not hmac.compare_digest(
                    cookie_token.encode("utf-8"), header_token.encode("utf-8")
                )
            ):
                raise PermissionDenied("CSRF check failed")

        return super().initial(request, *args, **kwargs)
