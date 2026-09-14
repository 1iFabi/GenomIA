"""
Utilidades para el manejo de emails en la aplicación SeqUOH (Genomia) usando la API de Gmail.
Incluye:
- Branding accesible (paleta nueva + tokens)
- Preheader
- Botones consistentes
- Card con sombra y radios
- Soporte dark mode básico (Apple Mail / algunos clientes)
- Fallback de logo a /cNormal.png (no usa SeqUOHLogo.png)
"""

import base64
from html import escape
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from email.utils import parseaddr, formataddr
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from django.conf import settings
import os
import json
import logging
import tempfile

logger = logging.getLogger(__name__)


class EmailDeliveryError(RuntimeError):
    """Raised when a requested email could not be handed to the provider."""



def _recipient_domain(email: str) -> str:
    """Return a low-sensitivity recipient context for operational logs."""
    return str(email).rsplit('@', 1)[-1] or 'unknown'


SAFE_DEFAULT_FROM_EMAIL = 'GenomIA <seqgenomia@gmail.com>'


def _safe_sender(from_email: str | None = None) -> str:
    """Return the configured sender, never an empty value."""
    configured_sender = getattr(settings, 'DEFAULT_FROM_EMAIL', None)
    candidate = from_email or configured_sender
    if isinstance(candidate, str) and candidate.strip():
        return candidate.strip()
    return SAFE_DEFAULT_FROM_EMAIL

# =========================
#   Configuración Gmail
# =========================
SCOPES = ['https://www.googleapis.com/auth/gmail.send']

# =========================
#   Branding & UI tokens
# =========================
BRAND = {
    "name": "Genomia",
    "colors": {
        # petróleo accesible (AA sobre blanco y en botón)
        "primary": "#0E7490",   # teal-700
        "primary_dark": "#0B5C70",
        "accent": "#14B8A6",    # teal-500
        "ink": "#111827",       # gray-900
        "body": "#374151",      # gray-700
        "muted": "#6B7280",     # gray-500
        "border": "#E5E7EB",    # gray-200
        "card_bg": "#FFFFFF",
        "bg": "#F8FAFC"         # slate-50
    },
    "radius": 14,
    "shadow": "0 2px 6px rgba(0,0,0,0.08), 0 1px 2px rgba(0,0,0,0.06)"
}


# =========================
#   Helpers de assets/UI
# =========================
def _asset_url(path: str) -> str:
    base = getattr(settings, 'FRONTEND_DOMAIN', 'http://localhost:5173').rstrip('/')
    if not path.startswith('/'):
        path = '/' + path
    return f"{base}{path}"

def load_logo_bytes() -> bytes | None:
    """
    Busca *primero* cNormal.png en distintas ubicaciones (backend y frontend).
    No usa SeqUOHLogo.png.
    """
    candidates = [
        # backend/static
        settings.BASE_DIR / 'static' / 'branding' / 'cNormal.png',
        settings.BASE_DIR / 'sequoh' / 'static' / 'branding' / 'cNormal.png',
        # frontend
        settings.BASE_DIR.parent.parent / 'frontend' / 'public' / 'cNormal.png',
        settings.BASE_DIR.parent.parent / 'frontend' / 'dist' / 'cNormal.png',
        # fallback a Logo.png si no existe cNormal.png
        settings.BASE_DIR / 'static' / 'branding' / 'Logo.png',
        settings.BASE_DIR.parent.parent / 'frontend' / 'public' / 'Logo.png',
        settings.BASE_DIR.parent.parent / 'frontend' / 'dist' / 'Logo.png',
    ]
    for p in candidates:
        try:
            if p.exists():
                with open(p, 'rb') as f:
                    return f.read()
        except Exception:
            continue
    return None


def email_button(url: str, label: str, *, kind: str = "primary") -> str:
    """
    Botón bulletproof para email (anchor con estilos inline).
    kind: "primary" | "neutral"
    """
    c = BRAND["colors"]
    if kind == "neutral":
        bg = c["ink"]
        # ojo: :hover no siempre aplica en clientes de correo, lo dejamos informativo
    else:
        bg = c["primary"]
    safe_url = escape(url or "", quote=True)
    safe_label = escape(label or "")
    return (
        f'<a href="{safe_url}" '
        f'style="background:{bg}; color:#FFFFFF; text-decoration:none; '
        f'display:inline-block; line-height:1; font-weight:700; '
        f'padding:12px 22px; border-radius:{BRAND["radius"]}px; '
        f'box-shadow: {BRAND["shadow"]};">'
        f'{safe_label}</a>'
    )


def build_branded_html(inner_html: str,
                       title_text: str | None = None,
                       logo_src: str | None = None,
                       preheader: str | None = None) -> str:
    """
    Plantilla base con:
    - preheader (oculto visual, visible en inbox preview)
    - banner con logo cNormal.png (CID si viene)
    - card central prolija y accesible
    - light/dark tweaks donde aplica
    """
    c = BRAND["colors"]
    _default_logo = _asset_url('cNormal.png')
    _logo_src = escape(logo_src or 'cid:logo_cid', quote=True)
    _pre = escape(preheader or "")
    _safe_title = escape(title_text or "")

    title_html = (
        f'<h2 style="color:{c["ink"]}; margin:0 0 16px 0; '
        f'font-size:24px; font-weight:800; line-height:1.25;">{_safe_title}</h2>'
        if title_text else ""
    )

    return f"""
<!DOCTYPE html>
<html lang="es">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width,initial-scale=1.0">
    <title>{(_safe_title or escape(BRAND["name"]))}</title>
    <!-- Preheader: mostrado en la bandeja, oculto en el cuerpo -->
    <span style="display:none!important;visibility:hidden;opacity:0;color:transparent;
      height:0;width:0;overflow:hidden;mso-hide:all;">
      {_pre}
    </span>
    <style>
      /* Dark mode (Apple Mail / algunos clientes) */
      @media (prefers-color-scheme: dark) {{
        :root {{
          color-scheme: dark;
          supported-color-schemes: dark;
        }}
        .bg {{
          background: #0B1220 !important;
        }}
        .card {{
          background: #0F172A !important;
          border-color: #1F2937 !important;
        }}
        .text {{
          color: #E5E7EB !important;
        }}
        .muted {{
          color: #9CA3AF !important;
        }}
      }}
    </style>
  </head>
  <body style="margin:0; padding:0; background:{c["bg"]}; 
               font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" class="bg"
           style="background:{c["bg"]}; padding:32px 16px;">
      <tr>
        <td align="center">
          <table role="presentation" width="600" cellspacing="0" cellpadding="0"
                 style="max-width:600px; width:100%;">
            <!-- Logo -->
            <tr>
              <td align="center" style="padding:0 0 16px 0;">
                <img src="{_logo_src if _logo_src.startswith('cid:') else (_logo_src or _default_logo)}"
                  alt="{BRAND["name"]}"
                  style="display:block; border:0; border-radius:12px;
                          max-width:100px; height:auto; aspect-ratio:1/1; object-fit:contain;" />

              </td>
            </tr>

            <!-- Card -->
            <tr>
              <td>
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0"
                       class="card"
                       style="background:{c["card_bg"]}; border-radius:{BRAND["radius"]}px; 
                              box-shadow:{BRAND["shadow"]}; border:1px solid {c["border"]};">
                  <tr>
                    <td style="padding:36px 28px;">
                      {title_html}
                      <div class="text" style="color:{c["body"]}; font-size:15px; line-height:1.65;">
                        {inner_html}
                      </div>
                    </td>
                  </tr>
                </table>
              </td>
            </tr>

            <!-- Footer -->
            <tr>
              <td align="center" style="padding:18px 0 0 0;">
                <p class="muted" style="margin:0; color:{c["muted"]}; font-size:12px; line-height:1.5;">
                  {BRAND["name"]}
                </p>
              </td>
            </tr>

          </table>
        </td>
      </tr>
    </table>
  </body>
</html>
"""


def text_block(*lines: str) -> str:
    """Crea un bloque de texto plano coherente para multipart/alternative."""
    return "\n".join(lines).strip() + "\n"


# =========================
#   Gmail Service & Send
# =========================
def get_gmail_service():
    creds = None
    cred_path = getattr(settings, 'GMAIL_CREDENTIALS_FILE', os.path.join(settings.BASE_DIR, 'config', 'credentials.json'))
    token_path = getattr(settings, 'GMAIL_TOKEN_FILE', os.path.join(settings.BASE_DIR, 'config', 'token.json'))

    # Permitir credenciales desde variables de entorno (más cómodo en producción)
    token_json_env = os.environ.get('GMAIL_TOKEN_JSON') or getattr(settings, 'GMAIL_TOKEN_JSON', None)
    cred_json_env = os.environ.get('GMAIL_CREDENTIALS_JSON') or getattr(settings, 'GMAIL_CREDENTIALS_JSON', None)

    # No loguear rutas de credenciales/token (solo el origen)
    logger.info("Gmail: token_env=%s", 'yes' if token_json_env or cred_json_env else 'no')

    # 1) Cargar token desde ENV si está presente
    if token_json_env and not creds:
        try:
            token_dict = json.loads(token_json_env)
            creds = Credentials.from_authorized_user_info(token_dict, SCOPES)
            logger.info("Gmail: token cargado desde variable de entorno")
        except Exception as e:
            logger.error(f"Gmail: error leyendo token desde ENV: {e}")
            creds = None

    # 2) Si no vino por ENV, intentar desde archivo
    if not creds:
        if os.path.exists(token_path):
            try:
                creds = Credentials.from_authorized_user_file(token_path, SCOPES)
                logger.info("Gmail: token cargado desde archivo")
            except Exception as e:
                logger.error(f"Gmail: error leyendo token: {e}")
                creds = None
        else:
            logger.warning("Gmail: token.json no existe en la ruta indicada")

    # 3) Si está expirado pero tiene refresh_token, intentar refrescar
    if creds and not creds.valid:
        if creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                logger.info("Gmail: token refrescado correctamente")
                # Guardar token refrescado solo si estamos trabajando con archivo (no sobreescribimos ENV)
                if not token_json_env:
                    try:
                        os.makedirs(os.path.dirname(token_path), exist_ok=True)
                        with open(token_path, 'w', encoding='utf-8') as f:
                            f.write(creds.to_json())
                        logger.info("Gmail: token refrescado guardado en archivo")
                    except Exception as e:
                        logger.warning(f"Gmail: no se pudo guardar el token refrescado: {e}")
            except Exception as e:
                logger.error(f"Gmail: error refrescando token: {e}")

    # 4) Si sigue inválido, decidir según entorno
    if not creds or not creds.valid:
        if getattr(settings, 'DEBUG', False):
            # Solo en desarrollo intentamos flujo interactivo (abre navegador)
            logger.info("Gmail: iniciando flujo OAuth local (solo DEBUG)")
            # Preferir credenciales desde ENV si se proporcionaron
            if cred_json_env:
                try:
                    temp_path = None
                    try:
                        with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False, encoding='utf-8') as f:
                            f.write(cred_json_env)
                            temp_path = f.name
                        flow = InstalledAppFlow.from_client_secrets_file(temp_path, SCOPES)
                    finally:
                        if temp_path and os.path.exists(temp_path):
                            try:
                                os.unlink(temp_path)
                            except OSError as e:
                                logger.warning("GmailAuth.unlink_temp_file failed: %s", repr(e))
                except Exception:
                    flow = InstalledAppFlow.from_client_secrets_file(cred_path, SCOPES)
            else:
                flow = InstalledAppFlow.from_client_secrets_file(cred_path, SCOPES)

            creds = flow.run_local_server(port=0)
            try:
                os.makedirs(os.path.dirname(token_path), exist_ok=True)
                with open(token_path, 'w', encoding='utf-8') as f:
                    f.write(creds.to_json())
                logger.info("Gmail: nuevo token guardado")
            except Exception as e:
                logger.warning(f"Gmail: no se pudo guardar el token: {e}")
        else:
            # En producción, fallar con mensaje claro (no se puede abrir navegador)
            raise RuntimeError(
                "Gmail API: token inválido o ausente en producción. "
                "Provee GMAIL_TOKEN_JSON (ENV) con refresh_token válido o GMAIL_TOKEN_FILE apuntando a token.json."
            )

    return build('gmail', 'v1', credentials=creds)


def send_email(to_email: str,
               subject: str,
               html_body: str | None = None,
               text_body: str = "",
               inline_images: dict[str, bytes] | None = None,
               *,
               from_email: str | None = None,
               from_name: str | None = None,
               reply_to: str | None = None) -> bool:
    """Envía un email genérico usando la API de Gmail (texto y/o HTML).

    Parámetros extra:
    - from_email: dirección de remitente a usar (por defecto DEFAULT_FROM_EMAIL)
    - from_name: nombre visible del remitente (se formatea como "Nombre <email>")
    - reply_to: dirección para responder (Reply-To)
    """
    try:
        service = get_gmail_service()

        if inline_images:
            msg = MIMEMultipart('related')
            alt = MIMEMultipart('alternative')
            if text_body:
                alt.attach(MIMEText(text_body, 'plain', 'utf-8'))
            if html_body:
                alt.attach(MIMEText(html_body, 'html', 'utf-8'))
            msg.attach(alt)
            for cid, content in (inline_images or {}).items():
                try:
                    img = MIMEImage(content)
                except Exception:
                    img = MIMEImage(content, _subtype='png')
                img.add_header('Content-ID', f'<{cid}>')
                img.add_header('Content-Disposition', 'inline', filename=f'{cid}.png')
                img.add_header('X-Attachment-Id', cid)
                msg.attach(img)
        elif html_body:
            msg = MIMEMultipart('alternative')
            if text_body:
                msg.attach(MIMEText(text_body, 'plain', 'utf-8'))
            msg.attach(MIMEText(html_body, 'html', 'utf-8'))
        else:
            msg = MIMEText(text_body or "", 'plain', 'utf-8')

        # Construir encabezados usando parseaddr/formataddr para evitar duplicados
        raw_from = _safe_sender(from_email)
        name_in_default, email_in_default = parseaddr(raw_from)
        if not email_in_default or '@' not in email_in_default:
            raise ValueError('Configured sender is not a valid email address')
        # Si se pasó from_name, tiene prioridad para el nombre visible
        display_name = (from_name or name_in_default or '')
        from_header = formataddr((display_name, email_in_default))

        msg['Subject'] = subject
        msg['From'] = from_header
        msg['To'] = to_email
        if reply_to:
            msg['Reply-To'] = reply_to

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode('utf-8')
        result = service.users().messages().send(userId='me', body={'raw': raw}).execute()
        # No loguear el email del destinatario (PII) a nivel INFO
        logger.debug("Email enviado (asunto=%s, id=%s)", subject, result.get('id'))
        return True
    except Exception as e:
        logger.error(
            "Error enviando email (dominio=%s; error=%s)",
            _recipient_domain(to_email),
            type(e).__name__,
        )
        return False


# =========================
#   Mails específicos
# =========================
def send_verification_email(user_email: str, user_name: str, verification_url: str) -> bool:
    """
    Envía email con enlace de verificación de cuenta.
    """
    try:
        subject = 'Verifica tu correo'
        safe_user_name = escape(user_name or '')

        # Preparar logo inline (CID) si hay archivo disponible
        inline_images = {}
        logo_bytes = load_logo_bytes()
        logo_src = None
        if logo_bytes:
            inline_images['logo_cid'] = logo_bytes
            logo_src = 'cid:logo_cid'
        else:
            logo_src = _asset_url('cNormal.png')

        btn_html = email_button(verification_url, "Verificar mi cuenta", kind="primary")
        inner = f"""
          <p>Hola {safe_user_name},</p>
          <p>Gracias por registrarte en {BRAND["name"]}. Para activar tu cuenta, haz clic en el botón:</p>
          <div style="text-align:center; margin: 22px 0;">
            {btn_html}
          </div>
          <p style="background:#FFF8E1; border:1px solid #FFE08A; border-radius:10px; padding:12px; color:#7C5A00;">
            <strong>Importante:</strong> Este enlace caduca en {getattr(settings, 'EMAIL_VERIFICATION_EXPIRE_HOURS', 24)} horas.
          </p>
          <p style="color:#6B7280; font-size:13px;">Si no solicitaste esta cuenta, puedes ignorar este correo.</p>
        """
        html_content = build_branded_html(
            inner_html=inner,
            title_text='Verifica tu correo',
            logo_src=logo_src,
            preheader="Activa tu cuenta con un clic."
        )

        text_content = text_block(
            f"Hola {user_name},",
            f"Gracias por registrarte en {BRAND['name']}. Para activar tu cuenta, visita:",
            verification_url,
            "",
            f"Este enlace caduca en {getattr(settings, 'EMAIL_VERIFICATION_EXPIRE_HOURS', 24)} horas.",
            "",
            f"Equipo {BRAND['name']}"
        )

        ok = send_email(
            to_email=user_email,
            subject=subject,
            html_body=html_content,
            text_body=text_content,
            inline_images=inline_images or None,
            from_name="Genomia",
            from_email=_safe_sender(),
        )
        if ok:
            logger.info(
                "Email de verificación enviado (dominio=%s)",
                _recipient_domain(user_email),
            )
        return ok
    except Exception as e:
        logger.error(
            "Error enviando email de verificación (dominio=%s; error=%s)",
            _recipient_domain(user_email),
            type(e).__name__,
        )
        return False


def send_welcome_email(user) -> bool:
    """Envía email de bienvenida tras verificación."""
    from profiles.utils import ensure_sample_code
    from profiles.models import Profile

    try:
        profile, _ = Profile.objects.get_or_create(user=user)
        sample_code = ensure_sample_code(profile)

        subject = f'¡Bienvenido a GenomIA! Tu SampleCode es {sample_code}'
        login_url = getattr(
            settings,
            'FRONTEND_LOGIN_REDIRECT',
            f"{getattr(settings, 'FRONTEND_DOMAIN', 'http://localhost:5173').rstrip('/')}/login"
        )

        inline_images = {}
        logo_bytes = load_logo_bytes()
        logo_src = None
        if logo_bytes:
            inline_images['logo_cid'] = logo_bytes
            logo_src = 'cid:logo_cid'
        else:
            logo_src = _asset_url('cNormal.png')

        safe_first_name = escape(user.first_name or '')
        btn_html = email_button(login_url, "Acceder a mi cuenta", kind="primary")
        inner = f"""
          <p>Hola {safe_first_name},</p>
          <p>¡Bienvenido a GenomIA! Tu registro ha sido exitoso y tu cuenta ha sido verificada.</p>
          
          <div style="background:#F0F9FF; border-left:4px solid #0EA5E9; padding:20px; border-radius:12px; margin:24px 0;">
            <h3 style="color:#0369A1; margin:0 0 12px 0; font-size:18px;">Tu SampleCode</h3>
            <p style="margin:8px 0; color:#1E40AF;">Guarda este código, lo necesitarás para tu examen genético:</p>
            <p style="font-size: 20px; font-weight: 700; letter-spacing: 0.8px;">{sample_code}</p>
          </div>
          
          <div style="text-align:center; margin: 28px 0;">
            {btn_html}
          </div>
        """
        html_content = build_branded_html(
            inner_html=inner,
            title_text='¡Bienvenido a GenomIA!',
            logo_src=logo_src,
            preheader=f"Tu SampleCode es {sample_code}"
        )

        text_content = text_block(
            f"¡Bienvenido a GenomIA, {user.first_name}!",
            "",
            "Tu registro ha sido exitoso y tu cuenta ha sido verificada.",
            "",
            "Tu SampleCode es:",
            sample_code,
            "",
            f"Accede a tu cuenta: {login_url}",
            "",
            f"Equipo {BRAND['name']}"
        )

        ok = send_email(
            to_email=user.email,
            subject=subject,
            html_body=html_content,
            text_body=text_content,
            inline_images=inline_images or None,
            from_name="Genomia",
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'seqgenomia@gmail.com'),
        )
        if ok:
            logger.info(
                "Email de bienvenida enviado (dominio=%s)",
                _recipient_domain(user.email),
            )
        return ok
    except Exception as e:
        logger.error(
            "Error enviando email de bienvenida (dominio=%s; error=%s)",
            _recipient_domain(user.email),
            type(e).__name__,
        )
        return False

def send_password_reset_email(user_email: str, user_name: str, reset_url: str) -> bool:
    try:
        subject = 'Restablece tu contraseña'
        safe_user_name = escape(user_name or '')
        inline_images = {}
        logo_bytes = load_logo_bytes()
        logo_src = None
        if logo_bytes:
            inline_images['logo_cid'] = logo_bytes
            logo_src = 'cid:logo_cid'
        else:
            logo_src = _asset_url('cNormal.png')

        expire_hours = getattr(settings, 'PASSWORD_RESET_EXPIRE_HOURS',
                               getattr(settings, 'EMAIL_VERIFICATION_EXPIRE_HOURS', 24))

        btn_html = email_button(reset_url, "Restablecer contraseña", kind="neutral")
        inner = f"""
          <p>Hola {safe_user_name},</p>
          <p>Recibimos una solicitud para restablecer tu contraseña. Continúa aquí:</p>
          <div style="text-align:center; margin: 22px 0;">
            {btn_html}
          </div>
          <p style="background:#FFF8E1; border:1px solid #FFE08A; border-radius:10px; padding:12px; color:#7C5A00;">
            <strong>Importante:</strong> Este enlace caduca en {expire_hours} horas.
          </p>
          <p style="color:#6B7280; font-size:13px;">Si no solicitaste este cambio, ignora este correo.</p>
        """
        html_content = build_branded_html(
            inner_html=inner,
            title_text='Recuperación de contraseña',
            logo_src=logo_src,
            preheader="Tu link de recuperación está listo."
        )

        text_content = text_block(
            "Restablece tu contraseña",
            f"Enlace: {reset_url}",
            f"Este link caduca en {expire_hours} horas.",
            "",
            f"Equipo {BRAND['name']}"
        )

        ok = send_email(
            to_email=user_email,
            subject=subject,
            html_body=html_content,
            text_body=text_content,
            inline_images=inline_images or None
        )
        if ok:
            logger.info(
                "Email de reset enviado (dominio=%s)",
                _recipient_domain(user_email),
            )
        return ok
    except Exception as e:
        logger.error(
            "Error enviando email de reset (dominio=%s; error=%s)",
            _recipient_domain(user_email),
            type(e).__name__,
        )
        return False

def send_results_ready_email(user_email: str, user_name: str) -> bool:
    """
    Envía email notificando que los resultados genéticos están listos para ver.
    """
    try:
        subject = '¡Tus resultados están listos!'
        safe_user_name = escape(user_name or '')
        dashboard_url = getattr(
            settings,
            'FRONTEND_DASHBOARD_URL',
            f"{getattr(settings, 'FRONTEND_DOMAIN', 'http://localhost:5173').rstrip('/')}/postlogin"
        )

        inline_images = {}
        logo_bytes = load_logo_bytes()
        logo_src = None
        if logo_bytes:
            inline_images['logo_cid'] = logo_bytes
            logo_src = 'cid:logo_cid'
        else:
            logo_src = _asset_url('cNormal.png')

        btn_html = email_button(dashboard_url, "Ver mis resultados", kind="primary")
        inner = f"""
          <p>Hola {safe_user_name},</p>
          <p>¡Tenemos excelentes noticias! Tu análisis genético ha sido completado y tus resultados ya están disponibles.</p>
          <p>Ahora puedes explorar:</p>
          <ul style="color:#374151; line-height:1.8; margin:16px 0;">
            <li>Tu perfil de ancestría</li>
            <li>Rasgos genéticos</li>
            <li>Información sobre farmacogenética</li>
            <li>Biomarcadores y biométricas</li>
            <li>Predisposición a enfermedades</li>
          </ul>
          <div style="text-align:center; margin: 24px 0;">
            {btn_html}
          </div>
          <p style="background:#DBEAFE; border:1px solid #93C5FD; border-radius:10px; padding:12px; color:#1E40AF;">
            <strong>¡Importante!</strong> Recuerda que esta información es confidencial. Puedes descargar un PDF completo desde tu dashboard.
          </p>
        """
        html_content = build_branded_html(
            inner_html=inner,
            title_text='¡Tus resultados están listos!',
            logo_src=logo_src,
            preheader="Tu análisis genético ha sido completado."
        )

        text_content = text_block(
            f"Hola {user_name},",
            "",
            "¡Tu análisis genético ha sido completado!",
            "Tus resultados ya están disponibles en tu dashboard.",
            "",
            f"Accede aquí: {dashboard_url}",
            "",
            f"Equipo {BRAND['name']}"
        )

        ok = send_email(
            to_email=user_email,
            subject=subject,
            html_body=html_content,
            text_body=text_content,
            inline_images=inline_images or None,
            from_name="Genomia",
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'seqgenomia@gmail.com'),
        )
        if ok:
            logger.info(
                "Email de resultados listos enviado (dominio=%s)",
                _recipient_domain(user_email),
            )
        return ok
    except Exception as e:
        logger.error(
            "Error enviando email de resultados listos (dominio=%s; error=%s)",
            _recipient_domain(user_email),
            type(e).__name__,
        )
        return False


def send_contact_form_email(nombre: str, email: str, mensaje: str) -> bool:
    """
    Envía un email de contacto desde el formulario web a seqgenomia@gmail.com.
    - From visible: "Genomia · Contacto <seqgenomia@gmail.com>"
    - Reply-To: email del usuario (para responder directo a la persona)
    """
    try:
        contact_email = getattr(settings, 'CONTACT_EMAIL', 'seqgenomia@gmail.com')
        subject = f'Nuevo mensaje de contacto de {nombre}'
        safe_nombre = escape(nombre or '')
        safe_email = escape(email or '', quote=True)
        safe_mensaje = escape(mensaje or '')

        inline_images = {}
        logo_bytes = load_logo_bytes()
        logo_src = None
        if logo_bytes:
            inline_images['logo_cid'] = logo_bytes
            logo_src = 'cid:logo_cid'

        html_content = build_modern_email(
            title_text="Contacto",
            preheader="Nuevo mensaje desde el sitio de GenomIA.",
            logo_src=logo_src,
            inner_html=f"""
              <div style="background:#F3F4F6;border-left:4px solid {BRAND_PRIMARY};padding:16px;border-radius:8px;margin-bottom:20px;">
                <p style="margin:0 0 8px 0;color:#6B7280;font-size:12px;font-weight:700;letter-spacing:0.5px;text-transform:uppercase">Nuevo Mensaje de Contacto</p>
                <h2 style="margin:0;color:{BRAND_DARK};font-size:18px">De: {safe_nombre}</h2>
              </div>

              <div style="display:inline-block;background:#F9FAFB;border:1px solid #E5E7EB;border-radius:8px;padding:10px 12px;margin-bottom:16px;">
                <span style="color:#6B7280;font-size:12px;font-weight:700;letter-spacing:0.5px">Email:</span>
                <a href="mailto:{safe_email}" style="color:{BRAND_PRIMARY};font-weight:700;margin-left:8px">{safe_email}</a>
              </div>

              <div style="background:#FFFFFF;border:1px solid #E5E7EB;border-radius:12px;padding:18px 16px;">
                <p style="margin:0 0 10px 0;color:#6B7280;font-size:12px;font-weight:700;letter-spacing:0.5px;text-transform:uppercase">Mensaje</p>
                <div style="color:#111827;font-size:15px;line-height:1.7;white-space:pre-wrap">{safe_mensaje}</div>
              </div>

              <p class="muted" style="color:#6B7280;font-size:12px;line-height:1.6;margin-top:18px">
                Puedes responder directamente a <a href="mailto:{safe_email}" style="color:{BRAND_PRIMARY};font-weight:700">{safe_email}</a>.
              </p>
            """,
        )

        text_content = f"""Nuevo mensaje de contacto

De: {nombre}
Email: {email}

Mensaje:
{mensaje}

---
Puedes responder directamente a {email}
"""

        return send_email(
            to_email=contact_email,
            subject=subject,
            html_body=html_content,
            text_body=text_content,
            inline_images=inline_images or None,
            from_name="Genomia · Contacto",  # <- evita "me"
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'seqgenomia@gmail.com'),
            reply_to=email,  # <- responde directo al usuario
        )
    except Exception as e:
        logger.error(f"Error enviando email de contacto: {str(e)}")
        return False
