from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.utils.decorators import method_decorator
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.conf import settings
from django.utils import timezone
from datetime import datetime, timedelta, timezone as dt_timezone
from allauth.account.models import EmailAddress
from .email_utils import (
    EmailDeliveryError,
    send_welcome_email,
    send_password_reset_email,
    send_email,
    build_branded_html,
)
from .jwt_utils import encode_jwt, decode_jwt
from .authentication import JWTAuthentication
from profiles.models import Profile, ServiceStatus
from genetics.models import SNP
from .models import RevokedToken, WelcomeStatus
from .email_validation import is_valid_registration_name, validate_registration_email
from .username_validation import normalize_registration_username
from .csrf import CSRFDoubleSubmitMixin
from .roles import (
    ensure_default_groups,
    is_admin,
    is_analyst,
    is_reception,
    is_admin_or_analyst,
    is_admin_or_reception,
    grant_analyst_role,
    revoke_analyst_role,
    grant_reception_role,
    revoke_reception_role,
)
import json
import re
import logging
from html import escape

logger = logging.getLogger(__name__)


class UserServiceStatusAPIView(CSRFDoubleSubmitMixin, APIView):
    """Permite consultar tu estado y a admin/staff actualizar el estado de otro usuario."""
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Devuelve el estado del usuario autenticado."""
        u = request.user
        from profiles.models import Profile, ServiceStatus
        try:
            status_value = u.profile.service_status
            updated_at = u.profile.service_updated_at
        except Profile.DoesNotExist:
            status_value = ServiceStatus.NO_PURCHASED
            updated_at = None
        return Response({
            "user_id": u.id,
            "service_status": status_value,
            "can_view_results": status_value == ServiceStatus.COMPLETED,
            "updated_at": updated_at,
        })

    def post(self, request):
        """Actualiza el estado de servicio de un usuario (solo staff). Body: {userId, status} """
        if not is_admin_or_analyst(request.user):
            return Response({"error": "No tienes permisos"}, status=status.HTTP_403_FORBIDDEN)
        try:
            data = json.loads(request.body or '{}')
        except json.JSONDecodeError:
            data = request.data or {}
        user_id = data.get('userId')
        status_str = data.get('status')
        if not user_id or not status_str:
            return Response({"error": "userId y status son obligatorios"}, status=status.HTTP_400_BAD_REQUEST)
        if status_str not in {s.value for s in ServiceStatus}:
            return Response({"error": f"status inválido. Usa uno de: {[s.value for s in ServiceStatus]}"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            target = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({"error": "Usuario no encontrado"}, status=status.HTTP_404_NOT_FOUND)
        # Asegurar que el profile exista
        from profiles.models import Profile
        profile, _ = Profile.objects.get_or_create(user=target)
        profile.service_status = status_str
        profile.save(update_fields=["service_status", "service_updated_at"])
        return Response({
            "user_id": target.id,
            "service_status": profile.service_status,
            "updated_at": profile.service_updated_at,
        })


def normalize_cl_phone(raw: str):
    """Normaliza teléfonos móviles de Chile a formato +569XXXXXXXX.
    Acepta variantes comunes: +569XXXXXXXX, 569XXXXXXXX, 09XXXXXXXX, 9XXXXXXXX.
    Retorna el número normalizado o None si no es válido.
    """
    if not raw:
        return None
    s = raw.strip().replace(" ", "").replace("-", "")
    # +569XXXXXXXX
    if re.fullmatch(r"\+569\d{8}", s):
        return s
    # 569XXXXXXXX
    if re.fullmatch(r"569\d{8}", s):
        return "+" + s
    # 09XXXXXXXX
    if re.fullmatch(r"09\d{8}", s):
        return "+569" + s[2:]
    # 9XXXXXXXX
    if re.fullmatch(r"9\d{8}", s):
        return "+569" + s
    return None


class CsrfCookieAPIView(APIView):
    """Establece la cookie `csrftoken` (no HttpOnly) para el uso del frontend.

    Es el patrón double-submit: el SPA lee la cookie y la envía como
    `X-CSRFToken` en las peticiones mutables (POST/DELETE).
    """
    authentication_classes = []
    permission_classes = []

    @method_decorator(ensure_csrf_cookie)
    def get(self, request):
        return Response({"success": True})


@method_decorator(csrf_exempt, name='dispatch')
class LoginAPIView(APIView):
    authentication_classes = []
    permission_classes = []
    throttle_scope = 'login'

    def post(self, request):
        try:
            # Obtiene el cuerpo de la petición y lo decodifica de JSON
            data = json.loads(request.body)
            username = data.get('username')
            password = data.get('password')
            identifier = username.strip() if isinstance(username, str) else username

            # Resolve both public usernames and legacy email identifiers before
            # authenticating so the backend receives the stored username.
            resolved_user = None
            if isinstance(identifier, str) and identifier:
                resolved_user = User.objects.filter(username__iexact=identifier).first()
                if not resolved_user:
                    resolved_user = User.objects.filter(email__iexact=identifier).first()
            auth_username = resolved_user.username if resolved_user else identifier

            # Autentica al usuario usando las credenciales
            user = authenticate(request, username=auth_username, password=password)

            if user is not None:
                # Verificar email confirmado con allauth
                if getattr(settings, 'REQUIRE_EMAIL_VERIFICATION', False):
                    is_verified = EmailAddress.objects.filter(user=user, email=user.email, verified=True).exists()
                    if not is_verified:
                        return Response({
                            "error": "Tu cuenta aún no ha sido verificada. Revisa tu correo para completar la verificación.",
                            "requires_verification": True
                        }, status=400)

                # Generar JWT (stateless) para Vercel/Render
                token = encode_jwt({
                    "sub": str(user.id),
                    "email": user.email,
                })
                remember = bool(data.get('remember', False))
                cookie_name = getattr(settings, 'AUTH_COOKIE_NAME', 'access_token')
                samesite = getattr(settings, 'AUTH_COOKIE_SAMESITE', 'Lax')
                secure = bool(getattr(settings, 'AUTH_COOKIE_SECURE', False))
                resp = Response({"mensaje": "Inicio de sesión exitoso", "success": True})
                if remember:
                    # Cookie persistente: sobrevive al reinicio, acotada al TTL del token (8h).
                    max_age = int(getattr(settings, 'JWT_EXPIRATION_HOURS', 8)) * 3600
                    resp.set_cookie(cookie_name, token, httponly=True, samesite=samesite, secure=secure, path='/', max_age=max_age)
                else:
                    # Cookie de sesión: muere al cerrar el navegador (acotada al TTL del token).
                    resp.set_cookie(cookie_name, token, httponly=True, samesite=samesite, secure=secure, path='/')
                resp["Cache-Control"] = "no-store"
                return resp
            else:
                # Detectar caso de usuario pendiente de verificación (is_active=False)
                try:
                    possible_user = resolved_user
                    if possible_user and getattr(settings, 'REQUIRE_EMAIL_VERIFICATION', False):
                        if not EmailAddress.objects.filter(user=possible_user, email=possible_user.email, verified=True).exists():
                            return Response({
                                "error": "Tu cuenta está pendiente de verificación. Revisa tu correo para activar tu cuenta.",
                                "requires_verification": True
                            }, status=400)
                except Exception as e:
                    logger.warning("LoginAPIView.check_email_verified failed: %s", repr(e))
                
                # Respuesta genérica: no revela si el correo existe ni si la contraseña es correcta
                return Response({"success": False, "error": "Credenciales inválidas"}, status=400)
        except json.JSONDecodeError:
            # Maneja el error si el formato JSON es incorrecto
            return Response({"error": "Formato de solicitud inválido"}, status=400)
        except Exception:
            logger.exception("Error inesperado en LoginAPIView")
            return Response({"error": "Error interno del servidor"}, status=500)


class MeAPIView(APIView):
    """Retorna datos básicos del usuario autenticado (JWT)."""
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        u = request.user
        # Asegurar que los grupos base existan
        ensure_default_groups()

        # Cargar estado de servicio desde Profile
        from profiles.models import Profile, ServiceStatus
        try:
            p = u.profile
            service_status = p.service_status
        except Profile.DoesNotExist:
            service_status = ServiceStatus.NO_PURCHASED

        roles = list(u.groups.values_list("name", flat=True))
        admin_flag = is_admin(u)
        analyst_flag = is_analyst(u)
        reception_flag = is_reception(u)
        if admin_flag and "ADMIN" not in roles:
            roles.append("ADMIN")
        if reception_flag and "RECEPCION" not in roles:
            roles.append("RECEPCION")
        data_roles = sorted(set(roles))
        if admin_flag:
            user_type = "admin"
        elif analyst_flag:
            user_type = "analyst"
        elif reception_flag:
            user_type = "reception"
        else:
            user_type = "user"
        data = {
            "id": u.id,
            "username": u.username,
            "email": u.email,
            "first_name": u.first_name,
            "last_name": u.last_name,
            "is_staff": u.is_staff,
            "is_superuser": u.is_superuser,
            "is_admin": admin_flag,
            "is_analyst": analyst_flag,
            "is_reception": reception_flag,
            "roles": data_roles,
            "user_type": user_type,
            "service_status": service_status,
            "can_view_results": service_status == ServiceStatus.COMPLETED,
        }
        # Evitar cacheo del perfil actual
        resp = Response({"user": data})
        resp["Cache-Control"] = "no-store"
        return resp


class ChangePasswordAPIView(CSRFDoubleSubmitMixin, APIView):
    """Permite a un usuario autenticado cambiar su contraseña."""
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            data = json.loads(request.body or '{}')
            current_password = data.get('current_password', '')
            new_password = data.get('new_password', '')
            confirm_password = data.get('confirm_password', '')

            # Validaciones básicas
            if not all([current_password, new_password, confirm_password]):
                return Response(
                    {"error": "Todos los campos son obligatorios"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Verificar que las contraseñas nuevas coincidan
            if new_password != confirm_password:
                return Response(
                    {"error": "Las contraseñas nuevas no coinciden"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Verificar que la contraseña actual sea correcta
            user = request.user
            if not user.check_password(current_password):
                return Response(
                    {"error": "La contraseña actual es incorrecta"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Validar la nueva contraseña con las mismas reglas del registro
            password_errors = RegisterAPIView().validate_password(new_password)
            if password_errors:
                return Response(
                    {"error": password_errors},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Verificar que la nueva contraseña no sea igual a la actual
            if current_password == new_password:
                return Response(
                    {"error": "La nueva contraseña debe ser diferente a la actual"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Cambiar la contraseña
            user.set_password(new_password)
            user.save()

            return Response(
                {"success": True, "message": "Contraseña actualizada exitosamente"},
                status=status.HTTP_200_OK
            )

        except json.JSONDecodeError:
            return Response(
                {"error": "Formato de solicitud inválido"},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return Response(
                {"error": "Error interno del servidor"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class DeleteAccountAPIView(CSRFDoubleSubmitMixin, APIView):
    """Permite a un usuario eliminar su cuenta tras confirmarlo."""
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def delete(self, request):
        try:
            data = json.loads(request.body or '{}')
        except json.JSONDecodeError:
            return Response(
                {"error": "Formato de solicitud invalido"},
                status=status.HTTP_400_BAD_REQUEST
            )

        password = data.get('password', '')
        confirmation = (data.get('confirmation') or '').strip().lower()

        if not password:
            return Response(
                {"error": "Debes ingresar tu contrasena actual"},
                status=status.HTTP_400_BAD_REQUEST
            )

        if confirmation != 'eliminar':
            return Response(
                {"error": 'Debes escribir "ELIMINAR" para confirmar'},
                status=status.HTTP_400_BAD_REQUEST
            )

        user = request.user
        if not user.check_password(password):
            return Response(
                {"error": "Contrasena incorrecta"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            user.delete()
        except Exception:
            return Response(
                {"error": "No se pudo eliminar la cuenta"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        return Response(
            {"success": True, "message": "Cuenta eliminada correctamente"},
            status=status.HTTP_200_OK
        )


class LogoutAPIView(CSRFDoubleSubmitMixin, APIView):
    """Logout con revocación real: marca el jti del token en la blacklist y limpia la cookie."""
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        cookie_name = getattr(settings, 'AUTH_COOKIE_NAME', 'access_token')
        token = request.COOKIES.get(cookie_name)
        if token:
            try:
                payload = decode_jwt(token)
                jti = payload.get('jti')
                if jti:
                    exp_dt = datetime.fromtimestamp(payload['exp'], tz=dt_timezone.utc)
                    RevokedToken.objects.get_or_create(jti=jti, defaults={'expires_at': exp_dt, 'user_id': payload.get('sub')})
            except Exception as e:
                logger.warning("LogoutAPIView.decode_jwt failed: %s", repr(e))
        resp = Response({"success": True})
        resp.delete_cookie(cookie_name, path='/', samesite=getattr(settings, 'AUTH_COOKIE_SAMESITE', 'Lax'))
        resp["Cache-Control"] = "no-store"
        return resp


class DashboardAPIView(APIView):
    """Ejemplo de endpoint de dashboard por usuario (JWT)."""
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from profiles.models import Profile, ServiceStatus
        u = request.user
        profile = getattr(u, 'profile', None)
        service_status = getattr(profile, 'service_status', ServiceStatus.NO_PURCHASED)
        payload = {
            "user": {
                "id": u.id,
                "email": u.email,
                "first_name": u.first_name,
                "last_name": u.last_name,
            },
            "profile": {
                "phone": getattr(profile, 'phone', None),
                "service_status": service_status,
                "can_view_results": service_status == ServiceStatus.COMPLETED,
            },
        }
        # Métricas globales solo para staff/analista (evita fuga de datos de negocio)
        if is_admin_or_analyst(u):
            payload.update({
                "total_users": User.objects.filter(is_active=True).count(),
                "processed_reports": UserSNP.objects.values('user').distinct().count() if UserSNP.objects.exists() else 0,
                "variants_count": SNP.objects.count() if SNP.objects.exists() else 0,
                "analysis_count": User.objects.filter(profile__service_status=ServiceStatus.COMPLETED).count(),
                "user_growth": "+12%",
                "report_growth": "+8%",
                "analysis_growth": "+18%",
                "last_update": timezone.now().strftime("%d/%m/%Y"),
            })
        resp = Response(payload)
        resp["Cache-Control"] = "no-store"
        return resp


@method_decorator(csrf_exempt, name='dispatch')
class ContactAPIView(APIView):
    """Recibe mensajes del formulario de contacto y los envía por correo."""
    authentication_classes = []
    permission_classes = []
    throttle_scope = 'contact'

    def post(self, request):
        # Intentar leer JSON, si falla, usar form-encoded
        try:
            data = json.loads(request.body or '{}')
        except json.JSONDecodeError:
            data = request.POST or {}

        nombre = (data.get('nombre') or '').strip()
        email = (data.get('email') or '').strip().lower()
        mensaje = (data.get('mensaje') or '').strip()

        # Validaciones básicas
        errors = {}
        if not nombre:
            errors['nombre'] = 'El nombre es obligatorio.'
        if not email or not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
            errors['email'] = 'El correo electrónico no es válido.'
        if not mensaje or len(mensaje) < 5:
            errors['mensaje'] = 'El mensaje es demasiado corto.'

        if errors:
            return Response({"ok": False, "errors": errors}, status=status.HTTP_400_BAD_REQUEST)

        # Construir contenidos
        subject = f"Nuevo mensaje de contacto de {nombre}"
        text_body = (
            f"Nombre: {nombre}\n"
            f"Email: {email}\n\n"
            f"Mensaje:\n{mensaje}\n"
        )

        safe_nombre = escape(nombre)
        safe_email = escape(email, quote=True)
        safe_mensaje = escape(mensaje)
        inner_html = f"""
          <p><strong>Nombre:</strong> {safe_nombre}</p>
          <p><strong>Email:</strong> {safe_email}</p>
          <div style=\"margin-top:16px; padding:12px; background:#f9fafb; border:1px solid #e5e7eb; border-radius:8px;\">
            <div style=\"font-weight:600; color:#374151; margin-bottom:8px;\">Mensaje</div>
            <div style=\"white-space:pre-wrap; color:#111827;\">{safe_mensaje}</div>
          </div>
        """
        html_body = build_branded_html(inner_html=inner_html, title_text="Nuevo mensaje de contacto")

        # Enviar el correo al buzón de GenomIA
        recipient = 'seqgenomia@gmail.com'
        ok = False
        try:
            ok = send_email(to_email=recipient, subject=subject, html_body=html_body, text_body=text_body)
        except Exception as e:
            ok = False

        if not ok:
            return Response({"ok": False, "error": "No se pudo enviar el mensaje en este momento."}, status=status.HTTP_502_BAD_GATEWAY)

        return Response({"ok": True, "message": "Mensaje enviado correctamente."}, status=status.HTTP_200_OK)


def _email_validation_response(result):
    return Response(result.as_api_error(), status=status.HTTP_400_BAD_REQUEST)


class RegistrationEmailValidationAPIView(APIView):
    """Validate a registration email without exposing server-side blocklist details."""

    authentication_classes = []
    permission_classes = []
    throttle_scope = 'register_email_validation'

    def post(self, request):
        try:
            data = json.loads(request.body or '{}')
        except (TypeError, json.JSONDecodeError):
            return Response({"error": "El correo no es válido."}, status=status.HTTP_400_BAD_REQUEST)

        raw_email = (data.get('email') or data.get('correo')) if isinstance(data, dict) else None
        validation = validate_registration_email(raw_email)
        if not validation.valid:
            return _email_validation_response(validation)

        return Response(
            {
                "valid": True,
                "normalized_email": validation.normalized_email,
            },
            status=status.HTTP_200_OK,
        )


@method_decorator(csrf_exempt, name='dispatch')
class RegisterAPIView(APIView):
    throttle_scope = 'register'

    def post(self, request):
        try:
            data = json.loads(request.body)
            if not isinstance(data, dict):
                return Response({"error": "Formato de solicitud inválido"}, status=status.HTTP_400_BAD_REQUEST)

            try:
                normalized_username = normalize_registration_username(data.get('username'))
            except ValueError as exc:
                return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

            nombre = data.get('nombre') if isinstance(data.get('nombre'), str) else ''
            apellido = data.get('apellido') if isinstance(data.get('apellido'), str) else ''
            correo = data.get('correo') if isinstance(data.get('correo'), str) else ''
            telefono = data.get('telefono') if isinstance(data.get('telefono'), str) else ''
            rut = data.get('rut') if isinstance(data.get('rut'), str) else ''
            contraseña = data.get('contraseña', '')
            repetir_contraseña = data.get('repetirContraseña', '')
            terminos = data.get('terminos', False)

            nombre = nombre.strip()
            apellido = apellido.strip()
            correo = correo.strip().lower()
            telefono = telefono.strip()
            rut = rut.strip().upper()  # Normalizar a mayúsculas para la K
            
            # Validaciones básicas
            if not correo:
                return Response({"error": "El correo no es válido."}, status=status.HTTP_400_BAD_REQUEST)
            if (
                not telefono
                or not isinstance(contraseña, str)
                or not contraseña
                or not isinstance(repetir_contraseña, str)
                or not repetir_contraseña
            ):
                return Response({"error": "Todos los campos son obligatorios"}, status=status.HTTP_400_BAD_REQUEST)

            if nombre and not is_valid_registration_name(nombre):
                return Response({"error": "El nombre no es válido"}, status=status.HTTP_400_BAD_REQUEST)
            if apellido and not is_valid_registration_name(apellido):
                return Response({"error": "El apellido no es válido"}, status=status.HTTP_400_BAD_REQUEST)
            
            if not terminos:
                return Response({"error": "Debes aceptar los términos y condiciones"}, status=status.HTTP_400_BAD_REQUEST)
            
            if contraseña != repetir_contraseña:
                return Response({"error": "Las contraseñas no coinciden"}, status=status.HTTP_400_BAD_REQUEST)
            
            # Validación de contraseña
            password_errors = self.validate_password(contraseña)
            if password_errors:
                return Response({"error": password_errors}, status=status.HTTP_400_BAD_REQUEST)
            
            # Validación/normalización de teléfono (Chile: +569XXXXXXXX)
            telefono_norm = normalize_cl_phone(telefono)
            if not telefono_norm:
                return Response({"error": "El teléfono debe tener formato +569XXXXXXXX"}, status=status.HTTP_400_BAD_REQUEST)
            
            # Validate email syntax and MX records again before creating a user.
            email_validation = validate_registration_email(correo)
            if not email_validation.valid:
                return _email_validation_response(email_validation)
            correo = email_validation.normalized_email

            require_email_verification = bool(getattr(settings, 'REQUIRE_EMAIL_VERIFICATION', False))
            
            # Validación de RUT legacy, only when supplied.
            rut_pattern = r'^\d{7,8}-[0-9K]$'
            if rut and not re.fullmatch(rut_pattern, rut):
                return Response({"error": "El RUT debe tener el formato XXXXXXX-R (ejemplo: 12345678-9 o 1234567-K)"}, status=status.HTTP_400_BAD_REQUEST)
            
            # Verificar si el RUT ya existe, only when a legacy RUT was supplied.
            from profiles.models import Profile
            if rut and Profile.objects.filter(rut=rut).exists():
                return Response({
                    "error": "Este RUT ya está registrado",
                    "rut_exists": True
                }, status=status.HTTP_400_BAD_REQUEST)

            # Verificar identificadores existentes con comparación insensible a mayúsculas.
            if User.objects.filter(username__iexact=normalized_username).exists():
                return Response({
                    "error": "Este nombre de usuario ya está registrado",
                    "username_exists": True
                }, status=status.HTTP_400_BAD_REQUEST)

            if User.objects.filter(email__iexact=correo).exists():
                return Response({
                    "error": "Este correo ya está registrado",
                    "email_exists": True
                }, status=status.HTTP_400_BAD_REQUEST)

            # Crear el usuario y su perfil como una sola operación.
            try:
                with transaction.atomic():
                    user = User.objects.create_user(
                        username=normalized_username,
                        email=correo,
                        password=contraseña,
                        first_name=nombre,
                        last_name=apellido,
                    )
                    Profile.objects.create(
                        user=user,
                        phone=telefono_norm,
                        rut=rut or None,
                    )
                    if require_email_verification:
                        # Keep the allauth confirmation record in the same transaction
                        # as the user/profile so delivery failures roll everything back.
                        email_address = EmailAddress.objects.add_email(
                            request,
                            user,
                            correo,
                            confirm=True,
                            signup=True,
                        )
                        # The direct manager API does not mark a new address primary.
                        if not email_address.primary:
                            EmailAddress.objects.filter(user=user, primary=True).exclude(
                                pk=email_address.pk
                            ).update(primary=False)
                            email_address.primary = True
                            email_address.save(update_fields=['primary'])
            except IntegrityError:
                if User.objects.filter(username__iexact=normalized_username).exists():
                    return Response({
                        "error": "Este nombre de usuario ya está registrado",
                        "username_exists": True
                    }, status=status.HTTP_400_BAD_REQUEST)
                if User.objects.filter(email__iexact=correo).exists():
                    return Response({
                        "error": "Este correo ya está registrado",
                        "email_exists": True
                    }, status=status.HTTP_400_BAD_REQUEST)
                if rut and Profile.objects.filter(rut=rut).exists():
                    return Response({
                        "error": "Este RUT ya está registrado",
                        "rut_exists": True
                    }, status=status.HTTP_400_BAD_REQUEST)
                return Response(
                    {"error": "No se pudo completar el registro. Inténtalo nuevamente."},
                    status=status.HTTP_400_BAD_REQUEST,
                )


            if not require_email_verification:
                try:
                    welcome_sent = bool(send_welcome_email(user))
                except Exception as e:
                    welcome_sent = False
                    print(f"Error enviando email de bienvenida: {e}")
                if welcome_sent:
                    try:
                        WelcomeStatus.objects.update_or_create(
                            user=user,
                            defaults={"welcome_sent": True, "sent_at": timezone.now()},
                        )
                    except Exception as e:
                        logger.warning("RegisterAPIView.mark_welcome_sent failed: %s", repr(e))

            requires_verif = require_email_verification
            mensaje = "Usuario registrado exitosamente"
            if requires_verif:
                mensaje = "Usuario registrado exitosamente. Debes verificar tu cuenta desde tu correo para poder continuar."

            return Response({
                "mensaje": mensaje, 
                "success": True,
                "user_id": user.id,
                "username": user.username,
                "requires_verification": requires_verif
            }, status=status.HTTP_201_CREATED)
            
        except EmailDeliveryError:
            logger.exception("RegisterAPIView verification email delivery failed")
            return Response(
                {
                    "error": "No pudimos enviar el correo de verificación. Inténtalo nuevamente.",
                    "email_delivery_failed": True,
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except json.JSONDecodeError:
            return Response({"error": "Formato de solicitud inválido"}, status=status.HTTP_400_BAD_REQUEST)
        except IntegrityError:
            # Do not attribute an unrelated race or storage failure to the email.
            return Response(
                {"error": "No se pudo completar el registro. Inténtalo nuevamente."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            return Response({"error": "Error interno del servidor"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def validate_password(self, password):
        """Valida que la contraseña cumpla con los requisitos"""
        errors = []
        
        if len(password) < 10:
            errors.append("La contraseña debe tener al menos 10 caracteres")
        
        if not re.search(r'[A-Z]', password):
            errors.append("La contraseña debe contener al menos una letra mayúscula")
        
        if not re.search(r'[0-9]', password):
            errors.append("La contraseña debe contener al menos un número")
        
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
            errors.append("La contraseña debe contener al menos un símbolo especial")
        
        return ". ".join(errors) if errors else None


@method_decorator(csrf_exempt, name='dispatch')
class ResendVerificationAPIView(APIView):
    """Reenvía el correo de verificación usando allauth. Responde éxito sin filtrar información."""
    throttle_scope = 'resend'

    def post(self, request):
        try:
            try:
                data = json.loads(request.body or '{}')
            except Exception:
                data = getattr(request, 'data', {}) or {}
            email = (data.get('email') or '').strip().lower()
            if not email:
                return Response({"error": "Email es obligatorio"}, status=status.HTTP_400_BAD_REQUEST)

            # Buscar usuario
            user = User.objects.filter(email=email).first()
            if not user:
                # No revelar si existe o no
                return Response({"success": True})

            # Si ya está verificado, responder éxito
            if EmailAddress.objects.filter(user=user, email=email, verified=True).exists():
                return Response({"success": True})

            # Reenviar confirmación
            EmailAddress.objects.add_email(
                request,
                user,
                email,
                confirm=True,
                signup=False,
            )
            return Response({"success": True})
        except EmailDeliveryError:
            logger.exception("ResendVerificationAPIView email delivery failed")
            # Preserve anti-enumeration behavior for known users as well.
            return Response({"success": True})
        except Exception:
            logger.exception("ResendVerificationAPIView failed")
            # Por seguridad, responder éxito igualmente
            return Response({"success": True})


@method_decorator(csrf_exempt, name='dispatch')
class PasswordResetRequestAPIView(APIView):
    throttle_scope = 'reset'

    def post(self, request):
        try:
            data = json.loads(request.body or '{}')
            email = (data.get('email') or '').strip().lower()
            if not email:
                return Response({"error": "Email es obligatorio"}, status=status.HTTP_400_BAD_REQUEST)

            # Mensaje genérico para no revelar existencia del correo
            generic_ok = {"message": "Si el correo está registrado, te enviaremos un enlace para restablecer tu contraseña."}

            user = User.objects.filter(email=email).first()
            if not user:
                return Response(generic_ok)

            # Crear token de restablecimiento
            from .models import PasswordResetToken
            expire_hours = int(getattr(settings, 'PASSWORD_RESET_EXPIRE_HOURS', getattr(settings, 'EMAIL_VERIFICATION_EXPIRE_HOURS', 24)))
            expires_at = timezone.now() + timedelta(hours=expire_hours)
            prt = PasswordResetToken.objects.create(user=user, expires_at=expires_at)

            # Link al frontend que abre el modal de reset
            frontend_base = getattr(settings, 'FRONTEND_DOMAIN', 'http://localhost:5173').rstrip('/')
            reset_url = f"{frontend_base}/login?token={prt.token}"

            # Enviar email
            send_password_reset_email(user_email=user.email, user_name=user.first_name or user.username, reset_url=reset_url)

            return Response(generic_ok)
        except Exception as e:
            return Response({"error": "Error interno del servidor"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@method_decorator(csrf_exempt, name='dispatch')
class PasswordResetConfirmAPIView(APIView):
    def post(self, request):
        try:
            data = json.loads(request.body or '{}')
            token = (data.get('token') or '').strip()
            password = data.get('password') or ''
            confirm = data.get('confirmPassword') or ''

            if not token or not password or not confirm:
                return Response({"error": "Datos incompletos"}, status=status.HTTP_400_BAD_REQUEST)
            if password != confirm:
                return Response({"error": "Las contraseñas no coinciden"}, status=status.HTTP_400_BAD_REQUEST)

            # Validar políticas de password similares al registro
            errors = RegisterAPIView().validate_password(password)
            if errors:
                return Response({"error": errors}, status=status.HTTP_400_BAD_REQUEST)

            from .models import PasswordResetToken
            prt = PasswordResetToken.objects.select_related('user').filter(token=token).first()
            if not prt:
                return Response({"error": "Token inválido"}, status=status.HTTP_400_BAD_REQUEST)
            if prt.is_expired:
                return Response({"error": "El enlace ha expirado"}, status=status.HTTP_400_BAD_REQUEST)

            user = prt.user
            user.set_password(password)
            user.save()
            prt.used = True
            prt.save(update_fields=['used'])

            return Response({"success": True})
        except Exception as e:
            return Response({"error": "Error interno del servidor"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ManageAnalystRoleAPIView(CSRFDoubleSubmitMixin, APIView):
    """
    Permite a un ADMIN otorgar o revocar roles privilegiados (ANALISTA o RECEPCION).
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not is_admin(request.user):
            return Response({"error": "No tienes permisos"}, status=status.HTTP_403_FORBIDDEN)
        try:
            data = json.loads(request.body or '{}')
        except json.JSONDecodeError:
            data = request.data or {}

        user_id = data.get("userId") or data.get("user_id")
        grant = data.get("grant")
        if user_id is None or grant is None:
            return Response(
                {"error": "userId y grant (true/false) son obligatorios"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            target = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({"error": "Usuario no encontrado"}, status=status.HTTP_404_NOT_FOUND)

        role_raw = (data.get("role") or data.get("rol") or "analyst")
        role_value = str(role_raw).strip().lower()
        if role_value in ("analyst", "analista"):
            target_role = "analyst"
        elif role_value in ("reception", "recepcion", "recepcionista"):
            target_role = "reception"
        else:
            return Response(
                {"error": "Rol invalido. Usa 'analyst' o 'reception'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        ensure_default_groups()
        if target_role == "analyst":
            if grant:
                revoke_reception_role(target)
                grant_analyst_role(target)
            else:
                revoke_analyst_role(target)
        else:
            if grant:
                revoke_analyst_role(target)
                grant_reception_role(target)
            else:
                revoke_reception_role(target)
        return Response({
            "user_id": target.id,
            "is_analyst": is_analyst(target),
            "is_reception": is_reception(target),
            "role": target_role,
            "roles": list(target.groups.values_list("name", flat=True)),
        })


class GetUsersAPIView(APIView):
    """Endpoint para obtener lista de usuarios (solo staff)."""
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not is_admin_or_analyst(request.user):
            return Response({"error": "No tienes permisos"}, status=status.HTTP_403_FORBIDDEN)

        user_is_analyst = is_analyst(request.user)

        if user_is_analyst:
            # Analistas: ver muestras de usuarios finales (sin admin/analista/recepción)
            profiles = (
                Profile.objects.select_related("user")
                .filter(user__is_active=True, user__is_superuser=False, user__is_staff=False)
                .exclude(user__groups__name__in=["ADMIN", "ANALISTA", "RECEPCION"])
            )
            from profiles.utils import ensure_sample_code
            users_list = []
            for profile in profiles:
                if not profile.sample_code:
                    ensure_sample_code(profile)
                if not profile.sample_code:
                    continue
                users_list.append({
                    "id": profile.user.id,
                    "sample_code": profile.sample_code,
                    "service_status": profile.service_status,
                })
            return Response(users_list)

        # Admin: información completa
        users = User.objects.filter(is_active=True).values(
            "id", "username", "email", "first_name", "last_name", "is_staff", "is_superuser"
        )
        users_list = []
        for user in users:
            user_dict = dict(user)
            try:
                profile = Profile.objects.get(user_id=user["id"])
                user_dict["rut"] = getattr(profile, "rut", None)
                user_dict["sample_code"] = getattr(profile, "sample_code", None)
                user_dict["service_status"] = getattr(profile, "service_status", None)
            except Profile.DoesNotExist:
                user_dict["rut"] = None
                user_dict["sample_code"] = None
                user_dict["service_status"] = None

            try:
                target = User.objects.get(id=user["id"])
                user_dict["roles"] = list(target.groups.values_list("name", flat=True))
                user_dict["is_admin"] = is_admin(target)
                user_dict["is_analyst"] = is_analyst(target)
                user_dict["is_reception"] = is_reception(target)
            except User.DoesNotExist:
                user_dict["roles"] = []
                user_dict["is_admin"] = False
                user_dict["is_analyst"] = False
                user_dict["is_reception"] = False

            users_list.append(user_dict)

        return Response(users_list)

class AdminStatsAPIView(APIView):
    """Endpoint para obtener estadísticas del sistema (solo staff)."""
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # Verificar que sea staff
        if not is_admin_or_analyst(request.user):
            return Response({"error": "No tienes permisos"}, status=status.HTTP_403_FORBIDDEN)
        
        from django.db import connection
        from profiles.models import Profile, ServiceStatus
        
        try:
            # Contar usuarios activos (excluyendo staff y superusers)
            total_users = User.objects.filter(
                is_active=True,
                is_superuser=False,
            ).exclude(groups__name__in=["ADMIN", "ANALISTA"]).filter(is_staff=False).count()
            
            # Análisis completados (solo usuarios regulares)
            analysis_count = User.objects.filter(
                is_active=True,
                is_staff=False,
                is_superuser=False,
                profile__service_status=ServiceStatus.COMPLETED
            ).exclude(groups__name__in=["ADMIN", "ANALISTA"]).count()
            
            # Contar reportes pendientes
            pending_reports = Profile.objects.filter(service_status=ServiceStatus.PENDING).exclude(user__groups__name__in=["ADMIN", "ANALISTA"]).count()
            
            # Contar variantes en la BD
            variants_count = SNP.objects.count()
            
            payload = {
                "total_users": total_users,
                "pending_reports": pending_reports,
                "variants_count": variants_count,
                "analysis_count": analysis_count,
                "user_growth": "+12%",
                "report_growth": "+8%",
                "analysis_growth": "+18%",
                "last_update": timezone.now().strftime("%d/%m/%Y"),
            }
            resp = Response(payload)
            resp["Cache-Control"] = "no-store"
            return resp
        except Exception as e:
            print(f"Error en AdminStatsAPIView: {e}")
            # Devolver al menos los usuarios que podemos contar
            return Response({
                "total_users": User.objects.filter(is_active=True, is_superuser=False).exclude(groups__name__in=["ADMIN", "ANALISTA"]).filter(is_staff=False).count(),
                "processed_reports": 0,
                "variants_count": 0,
                "analysis_count": 0,
                "user_growth": "+0%",
                "report_growth": "+0%",
                "analysis_growth": "+0%",
                "last_update": timezone.now().strftime("%d/%m/%Y"),
            })
