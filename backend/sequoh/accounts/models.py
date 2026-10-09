from django.db import models
from django.conf import settings
from django.utils import timezone
import uuid


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


class Role(models.Model):
    """Functional GenomIA role, distinct from Django staff/admin flags."""

    class Code(models.TextChoices):
        CLIENTE = 'CLIENTE', 'Client'
        ADMIN = 'ADMIN', 'Administrator'
        ANALISTA = 'ANALISTA', 'Analyst'
        RECEPCION = 'RECEPCION', 'Reception'

    role_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=50, choices=Code.choices, unique=True)
    name = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)

    class Meta:
        db_table = 'role'
        constraints = [
            models.CheckConstraint(
                condition=models.Q(code__in=['CLIENTE', 'ADMIN', 'ANALISTA', 'RECEPCION']),
                name='role_functional_code_valid',
            ),
        ]


class AppUser(models.Model):
    """GenomIA role and optional external identity for a Django user.

    Django's User still authenticates (password or Google). Google accounts store
    issuer + `sub` here; the email is never the identity key.
    """

    user_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    django_user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='app_user',
    )
    role = models.ForeignKey(Role, on_delete=models.PROTECT, related_name='app_users')
    oidc_issuer = models.TextField(null=True, blank=True)
    oidc_subject = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        db_table = 'app_user'
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(oidc_issuer__isnull=True, oidc_subject__isnull=True)
                    | (
                        models.Q(oidc_issuer__isnull=False, oidc_subject__isnull=False)
                        & ~models.Q(oidc_issuer='')
                        & ~models.Q(oidc_subject='')
                    )
                ),
                name='app_user_oidc_pair_complete',
            ),
            models.UniqueConstraint(
                fields=['oidc_issuer', 'oidc_subject'],
                name='app_user_oidc_identity_unique',
            ),
        ]
