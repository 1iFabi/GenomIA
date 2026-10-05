from django.conf import settings
from django.db import migrations


ROLE_NAMES = {
    'CLIENTE': 'Client',
    'ADMIN': 'Administrator',
    'ANALISTA': 'Analyst',
    'RECEPCION': 'Reception',
}


def seed_roles_and_backfill(apps, schema_editor):
    """Keep explicit mappings; reject ambiguous legacy roles rather than elevate users."""
    alias = schema_editor.connection.alias
    Role = apps.get_model('accounts', 'Role')
    AppUser = apps.get_model('accounts', 'AppUser')
    User = apps.get_model(settings.AUTH_USER_MODEL)
    roles = {
        code: Role.objects.using(alias).get_or_create(code=code, defaults={'name': name})[0]
        for code, name in ROLE_NAMES.items()
    }

    users = User.objects.using(alias).order_by('pk').prefetch_related('groups')
    for user in users.iterator(chunk_size=1000):
        groups = sorted({group.name for group in user.groups.all() if group.name in roles})
        if len(groups) > 1:
            raise RuntimeError(
                f'Django User id={user.pk} has multiple recognized role Groups: {groups}; '
                'resolve before applying accounts.0004.'
            )

        role = roles[groups[0] if groups else 'CLIENTE']
        existing = AppUser.objects.using(alias).filter(django_user_id=user.pk).first()
        if existing is not None:
            if groups and existing.role_id != role.pk:
                raise RuntimeError(
                    f'Django User id={user.pk} AppUser role conflicts with legacy Group '
                    f'{groups[0]}; resolve before applying accounts.0004.'
                )
            continue
        AppUser.objects.using(alias).create(django_user_id=user.pk, role_id=role.pk)


class Migration(migrations.Migration):
    atomic = True

    dependencies = [
        ('accounts', '0003_role_appuser'),
    ]

    operations = [
        migrations.RunPython(seed_roles_and_backfill, migrations.RunPython.noop),
    ]
