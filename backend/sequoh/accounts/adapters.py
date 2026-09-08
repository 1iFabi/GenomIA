import logging

from allauth.account.adapter import DefaultAccountAdapter
from django.utils.translation import gettext_lazy as _
from .email_utils import send_email

logger = logging.getLogger(__name__)


class GmailAPIAccountAdapter(DefaultAccountAdapter):
    """Adapter de allauth que envía correos vía Gmail API usando email_utils.

    - Para confirmación de correo, genera un correo 100% alineado al branding con
      send_verification_email (evita textos por defecto como [example.com]).
    - Para el resto de plantillas, respeta el render de allauth y lo envuelve
      con el layout de marca.
    """

    def send_mail(self, template_prefix, email, context):
        # Caso especial: confirmación de correo
        try:
            if template_prefix.endswith('account/email/email_confirmation') and 'activate_url' in context:
                from .email_utils import send_verification_email
                user_name = (getattr(getattr(context, 'get', lambda k, d=None: None)('user'), 'first_name', None)
                             or getattr(context.get('user'), 'username', '') if isinstance(context, dict) else '')
                # Fallback robusto si context no es dict
                if not user_name and isinstance(context, dict):
                    u = context.get('user')
                    if u is not None:
                        user_name = getattr(u, 'first_name', '') or getattr(u, 'username', '')
                activate_url = context['activate_url'] if isinstance(context, dict) else ''
                send_verification_email(email, user_name, activate_url)
                return
        except Exception as e:
            # Si algo sale mal, caemos al flujo genérico
            logger.warning("GmailAPIAccountAdapter.send_verification_email failed: %s", repr(e))

        # Flujo genérico: render de allauth, luego envolvemos con branding
        message = self.render_mail(template_prefix, email, context)
        subject = message.subject
        text_body = message.body or ""

        # Busca versión HTML si existe y aplica el branding
        html_body = None
        if hasattr(message, "alternatives") and message.alternatives:
            for content, content_type in message.alternatives:
                if content_type == "text/html":
                    html_body = content
                    break
        
        from .email_utils import build_branded_html, send_email
        if html_body:
            html_body = build_branded_html(html_body, title_text=None)
        else:
            html_body = build_branded_html(f"<pre style=\"white-space:pre-wrap\">{text_body}</pre>")

        send_email(to_email=email, subject=subject, html_body=html_body, text_body=text_body)
        # No llamamos a message.send() para evitar SMTP
