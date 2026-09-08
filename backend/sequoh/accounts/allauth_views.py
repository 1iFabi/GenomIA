from allauth.account.views import ConfirmEmailView
from django.shortcuts import redirect
from django.conf import settings
from urllib.parse import quote


class CustomConfirmEmailView(ConfirmEmailView):
    """
    View personalizado de allauth para confirmar email.
    Establece cookies para que el frontend React muestre el modal de verificación.
    """
    
    def get(self, *args, **kwargs):
        # Procesar la confirmación normalmente con allauth
        try:
            # Confirmar el email
            self.object = self.get_object()
            self.object.confirm(self.request)
            
            # Preparar la redirección al frontend con cookies Y parámetro URL
            frontend_base = getattr(settings, 'FRONTEND_DOMAIN', 'http://localhost:5173').rstrip('/')
            redirect_url = f"{frontend_base}/login?verified=1"
            
            response = redirect(redirect_url)
            
            # Establecer cookies para el modal de verificación exitosa
            # Nota: las cookies pueden no funcionar cross-origin, pero el parámetro URL sí
            response.set_cookie(
                key='verification_status',
                value='1',
                max_age=300,  # 5 minutos
                path='/',
                secure=not settings.DEBUG,
                samesite='None' if not settings.DEBUG else 'Lax',
                httponly=False  # Necesita ser accesible desde JS
            )
            response.set_cookie(
                key='verification_message',
                value=quote('Tu cuenta fue verificada correctamente. Ya puedes iniciar sesión.'),
                max_age=300,
                path='/',
                secure=not settings.DEBUG,
                samesite='None' if not settings.DEBUG else 'Lax',
                httponly=False
            )
            
            return response
            
        except Exception as e:
            # Si hay error, establecer cookie de error
            frontend_base = getattr(settings, 'FRONTEND_DOMAIN', 'http://localhost:5173').rstrip('/')
            redirect_url = f"{frontend_base}/login"
            
            response = redirect(redirect_url)
            response.set_cookie(
                key='verification_status',
                value='0',
                max_age=300,
                path='/',
                secure=not settings.DEBUG,
                samesite='Lax'
            )
            response.set_cookie(
                key='verification_message',
                value=quote('Ocurrió un error al verificar la cuenta. Por favor intenta de nuevo.'),
                max_age=300,
                path='/',
                secure=not settings.DEBUG,
                samesite='Lax'
            )
            
            return response
