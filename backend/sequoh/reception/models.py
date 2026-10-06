from django.conf import settings
from django.db import models
from django.utils import timezone


class ReceptionAccessLog(models.Model):
    """Who looked up which client and when (Ley 21.719 accountability). Never stores the RUT itself."""

    class Action(models.TextChoices):
        SEARCH = 'search', 'Search'
        VERIFY_RUT = 'verify_rut', 'Verify RUT'

    actor = models.ForeignKey('accounts.AppUser', on_delete=models.PROTECT, related_name='reception_access_logs')
    action = models.CharField(max_length=16, choices=Action.choices)
    query = models.CharField(max_length=96, blank=True)
    target_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='+')
    outcome = models.CharField(max_length=32)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'reception_access_log'
        ordering = ['-created_at', '-pk']
        indexes = [models.Index(fields=['target_user', '-created_at'], name='reception_log_target_idx')]
