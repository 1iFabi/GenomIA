from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from django.contrib.auth.signals import user_logged_in
from allauth.account.signals import email_confirmed
from allauth.account.models import EmailAddress
from .models import AppUser, Role, WelcomeStatus
from .email_utils import send_welcome_email


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def assign_new_user_client_role(sender, instance, created, using, raw=False, **kwargs):
    if raw or not created:
        return
    role, _ = Role.objects.using(using).get_or_create(
        code=Role.Code.CLIENTE, defaults={'name': 'Client'}
    )
    AppUser.objects.using(using).get_or_create(
        django_user_id=instance.pk, defaults={'role': role}
    )


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
