from django.contrib.auth.models import Group

# Nombre de los grupos del sistema
ADMIN_GROUP = "ADMIN"
ANALYST_GROUP = "ANALISTA"
RECEPTION_GROUP = "RECEPCION"


def ensure_default_groups():
    """
    Asegura que existan los grupos base.
    Se invoca antes de leer/asignar roles para evitar errores si la BD no los tiene.
    """
    for name in (ADMIN_GROUP, ANALYST_GROUP, RECEPTION_GROUP):
        Group.objects.get_or_create(name=name)


def is_admin(user):
    """
    Considera admin si es staff/superuser o pertenece al grupo ADMIN.
    """
    if not user or not getattr(user, "is_authenticated", False):
        return False
    return (
        user.is_staff
        or user.is_superuser
        or user.groups.filter(name=ADMIN_GROUP).exists()
    )


def is_analyst(user):
    """
    Considera analista si pertenece al grupo ANALISTA.
    """
    if not user or not getattr(user, "is_authenticated", False):
        return False
    return user.groups.filter(name=ANALYST_GROUP).exists()


def is_reception(user):
    """
    Considera recepción si pertenece al grupo RECEPCION.
    """
    if not user or not getattr(user, "is_authenticated", False):
        return False
    return user.groups.filter(name=RECEPTION_GROUP).exists()


def is_admin_or_analyst(user):
    return is_admin(user) or is_analyst(user)


def is_admin_or_reception(user):
    return is_admin(user) or is_reception(user)


def grant_analyst_role(user):
    ensure_default_groups()
    group = Group.objects.get(name=ANALYST_GROUP)
    user.groups.add(group)


def revoke_analyst_role(user):
    ensure_default_groups()
    group = Group.objects.get(name=ANALYST_GROUP)
    user.groups.remove(group)


def grant_reception_role(user):
    """Otorga rol de recepción al usuario."""
    ensure_default_groups()
    group = Group.objects.get(name=RECEPTION_GROUP)
    user.groups.add(group)


def revoke_reception_role(user):
    """Revoca rol de recepción al usuario."""
    ensure_default_groups()
    group = Group.objects.get(name=RECEPTION_GROUP)
    user.groups.remove(group)


def grant_admin_role(user):
    """
    Otorga rol ADMIN al usuario y marca is_staff True para conservar compatibilidad.
    """
    ensure_default_groups()
    group = Group.objects.get(name=ADMIN_GROUP)
    user.groups.add(group)
    if not user.is_staff:
        user.is_staff = True
        user.save(update_fields=["is_staff"])
