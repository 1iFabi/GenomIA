class NoCacheMiddleware:
    """Evita que el navegador almacene en caché páginas protegidas.

    Esto ayuda a que, tras cerrar sesión, el usuario no pueda ver contenido al
    retroceder con el botón "atrás" del navegador.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        # Aplica encabezados no-cache para todo. Si quieres limitar solo a rutas
        # autenticadas, podrías chequear request.user.is_authenticated.
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response


class SecurityHeadersMiddleware:
    """Browser policies for what the backend serves: the JSON API and the admin (/ciff/).

    The SPA gets its own CSP from the frontend build (frontend/vite.config.js).
    """
    PERMISSIONS_POLICY = "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
    # The admin only loads its own static files; JSON responses load nothing at all.
    CONTENT_SECURITY_POLICY = (
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
        "object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response.headers.setdefault("Permissions-Policy", self.PERMISSIONS_POLICY)
        response.headers.setdefault("Content-Security-Policy", self.CONTENT_SECURITY_POLICY)
        return response
