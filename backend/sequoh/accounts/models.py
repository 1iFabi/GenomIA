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
    # Indexed so the scheduled purge (manage.py purge_revoked_tokens) does not scan the table.
    expires_at = models.DateTimeField(db_index=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = 'Token revocado'
        verbose_name_plural = 'Tokens revocados'
        ordering = ['-created_at']

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


AVATAR_COLORS = [(k, k) for k in (
    'global_ancestry', 'pharmacogenetics', 'traits', 'polygenic_risk', 'monogenic_risk',
)]
AVATAR_FIGURES = [('initial', 'initial'), ('helix', 'helix')]


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
    # A generated avatar, never an uploaded photo: one of the five result-module colours and a figure.
    avatar_color = models.CharField(max_length=20, choices=AVATAR_COLORS, default='traits', db_default='traits')
    avatar_figure = models.CharField(max_length=10, choices=AVATAR_FIGURES, default='initial', db_default='initial')
    # Last self-service rename; the client may rename again USERNAME_CHANGE_EVERY after it.
    username_changed_at = models.DateTimeField(null=True, blank=True)
    # Bumped when the functional role changes; login tokens carry it as `tv`, so older sessions end.
    token_version = models.PositiveIntegerField(default=0, db_default=0)

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


class GeneticDataAccessLog(models.Model):
    """Who read whose genetic results and when (Ley 21.719 accountability, OWASP/NIST audit trail).

    Plain user ids, not foreign keys: deleting an account must neither be blocked by its trail nor erase it.
    """

    class Resource(models.TextChoices):
        RESULTS = 'results', 'Results'
        ANCESTRY_COHORT = 'ancestry_cohort', 'Ancestry cohort'

    actor_user_id = models.PositiveBigIntegerField()
    subject_user_id = models.PositiveBigIntegerField()
    resource = models.CharField(max_length=32, choices=Resource.choices)
    outcome = models.CharField(max_length=16)
    ip = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'genetic_data_access_log'
        ordering = ['-created_at', '-pk']
        indexes = [models.Index(fields=['subject_user_id', '-created_at'], name='genetic_log_subject_idx')]
