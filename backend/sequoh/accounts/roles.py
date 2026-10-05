from django.contrib.auth.models import Group
from django.db import transaction

from .models import AppUser, Role

# Legacy group names are retained for compatibility with older readers.
ADMIN_GROUP = "ADMIN"
ANALYST_GROUP = "ANALISTA"
RECEPTION_GROUP = "RECEPCION"


def ensure_default_groups():
    """Keep legacy group records for endpoints that still display them."""
    for name in (ADMIN_GROUP, ANALYST_GROUP, RECEPTION_GROUP):
        Group.objects.get_or_create(name=name)


def _has_role(user, code):
    if not user or not getattr(user, "is_authenticated", False) or not user.pk:
        return False
    return AppUser.objects.filter(django_user_id=user.pk, role__code=code).exists()


def is_admin(user):
    return _has_role(user, Role.Code.ADMIN)


def is_analyst(user):
    return _has_role(user, Role.Code.ANALISTA)


def is_reception(user):
    return _has_role(user, Role.Code.RECEPCION)


def is_admin_or_analyst(user):
    return is_admin(user) or is_analyst(user)


def is_admin_or_reception(user):
    return is_admin(user) or is_reception(user)


def _grant_role(user, code):
    with transaction.atomic():
        mapping = AppUser.objects.select_for_update().get(django_user=user)
        mapping.role = Role.objects.get(code=code)
        mapping.save(update_fields=["role"])


def _revoke_role(user, code):
    with transaction.atomic():
        mapping = AppUser.objects.select_for_update().select_related("role").get(django_user=user)
        if mapping.role.code == code:
            mapping.role = Role.objects.get(code=Role.Code.CLIENTE)
            mapping.save(update_fields=["role"])


def grant_analyst_role(user):
    _grant_role(user, Role.Code.ANALISTA)


def revoke_analyst_role(user):
    _revoke_role(user, Role.Code.ANALISTA)


def grant_reception_role(user):
    _grant_role(user, Role.Code.RECEPCION)


def revoke_reception_role(user):
    _revoke_role(user, Role.Code.RECEPCION)


def grant_admin_role(user):
    """Grant explicit GenomIA ADMIN without changing Django administration flags."""
    _grant_role(user, Role.Code.ADMIN)
