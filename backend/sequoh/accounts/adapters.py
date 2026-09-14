import logging

from allauth.account.adapter import DefaultAccountAdapter
from django.utils.translation import gettext_lazy as _
from .email_utils import (
    EmailDeliveryError,
    build_branded_html,
    send_email,
    send_verification_email,
)

logger = logging.getLogger(__name__)


class GmailAPIAccountAdapter(DefaultAccountAdapter):
    """Adapter de allauth que envía correos vía Gmail API usando email_utils.

    - Para confirmación de correo, genera un correo 100% alineado al branding con
      send_verification_email (evita textos por defecto como [example.com]).
    - Para el resto de plantillas, respeta el render de allauth y lo envuelve
      con el layout de marca.
    """

    def send_mail(self, template_prefix, email, context):
        # Caso especial: confirmación de correo, incluido el flujo de registro.
        is_verification_template = template_prefix.endswith(
            (
                'account/email/email_confirmation',
                'account/email/email_confirmation_signup',
            )
        )
        if is_verification_template and isinstance(context, dict) and 'activate_url' in context:
            user = context.get('user')
            user_name = (
                getattr(user, 'first_name', '')
                or getattr(user, 'username', '')
            )
            try:
                sent = send_verification_email(email, user_name, context['activate_url'])
            except Exception as exc:
                logger.exception(
                    "GmailAPIAccountAdapter verification delivery failed (domain=%s)",
                    str(email).rsplit('@', 1)[-1],
                )
                raise EmailDeliveryError("Verification email delivery failed") from exc
            if not sent:
                logger.error(
                    "GmailAPIAccountAdapter verification delivery returned false (domain=%s)",
                    str(email).rsplit('@', 1)[-1],
                )
                raise EmailDeliveryError("Verification email delivery failed")
            return

        # Flujo genérico: render de allauth, luego envolvemos con branding.
        message = self.render_mail(template_prefix, email, context)
        subject = message.subject
        text_body = message.body or ""

        # Busca versión HTML si existe y aplica el branding.
        html_body = None
        if hasattr(message, "alternatives") and message.alternatives:
            for content, content_type in message.alternatives:
                if content_type == "text/html":
                    html_body = content
                    break

        if html_body:
            html_body = build_branded_html(html_body, title_text=None)
        else:
            html_body = build_branded_html(f"<pre style=\"white-space:pre-wrap\">{text_body}</pre>")

        try:
            sent = send_email(
                to_email=email,
                subject=subject,
                html_body=html_body,
                text_body=text_body,
            )
        except Exception as exc:
            logger.exception(
                "GmailAPIAccountAdapter generic delivery failed (domain=%s)",
                str(email).rsplit('@', 1)[-1],
            )
            raise EmailDeliveryError("Email delivery failed") from exc
        if not sent:
            logger.error(
                "GmailAPIAccountAdapter generic delivery returned false (domain=%s)",
                str(email).rsplit('@', 1)[-1],
            )
            raise EmailDeliveryError("Email delivery failed")
        # No llamamos a message.send() para evitar SMTP.
