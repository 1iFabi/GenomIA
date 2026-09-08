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