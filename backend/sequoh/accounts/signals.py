from django.dispatch import receiver
from django.utils import timezone
from django.contrib.auth.signals import user_logged_in
from allauth.account.signals import email_confirmed
from allauth.account.models import EmailAddress
from .models import WelcomeStatus
from .email_utils import send_welcome_email

@receiver(email_confirmed)
def send_welcome_on_confirmation(request, email_address, **kwargs):
    user = email_address.user
    ws, _ = WelcomeStatus.objects.get_or_create(user=user)
    if not ws.welcome_sent:
        send_welcome_email(user)
        ws.welcome_sent = True
        ws.sent_at = timezone.now()
        ws.save()

@receiver(user_logged_in)
def send_welcome_on_login(sender, request, user, **kwargs):
    ws, _ = WelcomeStatus.objects.get_or_create(user=user)
    if ws.welcome_sent:
        return
    # Solo enviarlo si el email está verificado
    if EmailAddress.objects.filter(user=user, email=user.email, verified=True).exists():
        send_welcome_email(user)
        ws.welcome_sent = True
        ws.sent_at = timezone.now()
        ws.save()
