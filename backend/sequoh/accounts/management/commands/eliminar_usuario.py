from collections import Counter, defaultdict

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import ProtectedError, RestrictedError

from genoma.synthetic_import import _require_local_development

MAX_DEPTH = 25


def _delete_with_dependents(instances, counts, depth=0):
    """Delete instances, first removing whatever PROTECT/RESTRICT relations hold them in place."""
    if depth > MAX_DEPTH:
        raise CommandError('Cadena de dependencias demasiado profunda; revisa las relaciones del modelo.')
    by_model = defaultdict(set)
    for instance in instances:
        by_model[type(instance)].add(instance.pk)
    for model, pks in by_model.items():
        while True:
            queryset = model._base_manager.filter(pk__in=list(pks))  # list: composite PKs reject sets
            try:
                _total, per_model = queryset.delete()
            except ProtectedError as error:
                _delete_with_dependents(error.protected_objects, counts, depth + 1)
            except RestrictedError as error:
                _delete_with_dependents(error.restricted_objects, counts, depth + 1)
            else:
                counts.update({label: n for label, n in per_model.items() if n})
                break


def delete_user_completely(user):
    """Remove a user and every row that depends on it. Dev/testing only: production keeps these records."""
    counts = Counter()
    _delete_with_dependents([user], counts)
    return counts


class Command(BaseCommand):
    help = ('Elimina un usuario de prueba y todos sus datos relacionados (compras, servicios, muestras, '
            'análisis, perfil). Solo desarrollo local. Sin --confirmar solo muestra lo que borraría.')

    def add_arguments(self, parser):
        parser.add_argument('--email', required=True)
        parser.add_argument('--confirmar', action='store_true', help='Borra de verdad (por defecto es simulación).')

    def handle(self, *args, email, confirmar, **options):
        _require_local_development()
        user = get_user_model().objects.filter(email__iexact=email).first()
        if user is None:
            raise CommandError(f'No existe un usuario con correo {email}.')
        if user.is_superuser:
            raise CommandError('No se eliminan superusuarios con este comando.')

        with transaction.atomic():
            counts = delete_user_completely(user)
            if not confirmar:
                transaction.set_rollback(True)

        for label, count in sorted(counts.items()):
            self.stdout.write(f'  {label}: {count}')
        if confirmar:
            self.stdout.write(self.style.SUCCESS(f'{email} eliminado junto con {sum(counts.values())} registros.'))
        else:
            self.stdout.write(self.style.WARNING('Simulación: no se borró nada. Agrega --confirmar para eliminar.'))
