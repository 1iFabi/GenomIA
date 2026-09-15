from django.db import models
from django.conf import settings
from django.utils import timezone
import uuid


class EmailVerification(models.Model):
    """
    Modelo para gestionar tokens de verificación de correo electrónico
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='email_verifications'
    )
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    email = models.EmailField()
    is_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)
    verified_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField()

    class Meta:
        verbose_name = 'Verificación de Email'
        verbose_name_plural = 'Verificaciones de Email'
        ordering = ['-created_at']

    def __str__(self):
        return f"Verificación de {self.email} (usuario={self.user_id})"

    @property
    def is_expired(self) -> bool:
        return timezone.now() > self.expires_at


class RegistrationEmailChallenge(models.Model):
    """Short-lived mailbox-access challenge used before account creation."""

    email = models.EmailField(max_length=254)
    code_hash = models.CharField(max_length=128)
    created_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    attempt_count = models.PositiveIntegerField(default=0)
    verified_at = models.DateTimeField(null=True, blank=True)
    consumed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Desafío de correo de registro'
        verbose_name_plural = 'Desafíos de correo de registro'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['email', '-created_at'], name='accounts_reg_email_created_idx'),
            models.Index(fields=['expires_at'], name='accounts_reg_expiry_idx'),
        ]

    def __str__(self):
        return f"RegistrationEmailChallenge(id={self.pk}, email={self.email})"

    @property
    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at

    @property
    def is_verified(self) -> bool:
        return self.verified_at is not None

    @property
    def is_consumed(self) -> bool:
        return self.consumed_at is not None

    @property
    def attempts_exhausted(self) -> bool:
        max_attempts = int(getattr(settings, 'REGISTRATION_EMAIL_CHALLENGE_MAX_ATTEMPTS', 5))
        return self.attempt_count >= max_attempts


class WelcomeStatus(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='welcome_status')
    welcome_sent = models.BooleanField(default=False)
    sent_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"WelcomeStatus(user={self.user_id}, sent={self.welcome_sent})"


class PasswordResetToken(models.Model):
    """
    Token de restablecimiento de contraseña con expiración
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='password_reset_tokens'
    )
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    created_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    used = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"PasswordResetToken(user={self.user_id}, used={self.used})"

    @property
    def is_expired(self) -> bool:
        return timezone.now() > self.expires_at or self.used


class RevokedToken(models.Model):
    """Blacklist de tokens JWT revocados (por jti).

    Permite revocación real en logout y blocaje de tokens filtrados.
    El jti ya se genera en `jwt_utils.encode_jwt`.
    """
    jti = models.CharField(max_length=64, unique=True, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='revoked_tokens'
    )
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = 'Token revocado'
        verbose_name_plural = 'Tokens revocados'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['jti']),
        ]

    def __str__(self):
        return f"RevokedToken(jti={self.jti[:8]}...)"
