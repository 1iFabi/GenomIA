from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import RevokedToken


class Command(BaseCommand):
    help = "Delete revoked JWT rows whose tokens have expired anyway (schedule it, e.g. daily)."

    def handle(self, *args, **options):
        # An expired token fails its signature check, so its blacklist row is dead weight.
        deleted, _ = RevokedToken.objects.filter(expires_at__lt=timezone.now()).delete()
        self.stdout.write(f"Deleted {deleted} expired revoked token(s).")
