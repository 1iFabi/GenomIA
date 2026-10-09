from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from genoma.client_results import CLIENT_STATES, populate_client_results, set_client_state
from genoma.synthetic_import import _require_local_development


class Command(BaseCommand):
    help = ('Deja a un cliente en cualquier punto del flujo con datos SINTÉTICOS. Solo desarrollo. '
            'Estados: registrado (sin datos de compra), datos_compra (formulario de compra listo, sin pagar), '
            'WAITING_SAMPLE, SAMPLE_RECEIVED, PROCESSING (pagado, resultados pendientes) y COMPLETED '
            '(asigna N variantes ClinVar y genera todos los resultados). Se puede avanzar o retroceder; '
            'reemplaza lo generado antes por este comando y nunca toca un servicio real en curso.')

    def add_arguments(self, parser):
        parser.add_argument('--email', required=True)
        parser.add_argument('--estado', choices=CLIENT_STATES, default='COMPLETED')
        parser.add_argument('--variantes', type=int, default=500,
                            help='Solo para COMPLETED. Por defecto 500.')
        parser.add_argument('--semilla', type=int, help='Misma semilla = mismos resultados.')

    def handle(self, *args, email, estado, variantes, semilla, **options):
        _require_local_development()
        user = get_user_model().objects.filter(email__iexact=email).first()
        if user is None:
            raise CommandError(f'No existe un usuario con correo {email}.')
        try:
            if estado == 'COMPLETED':
                summary = populate_client_results(user, variantes, seed=semilla)
            else:
                summary = set_client_state(user, estado, seed=semilla)
        except ValueError as error:
            raise CommandError(str(error)) from error
        if estado == 'COMPLETED':
            message = (f"{summary['variants']} variantes asignadas, {summary['pathogenic']} patogénicas, "
                       f"{summary['segments']} segmentos de ancestría local. Muestra {summary['sample_code']}.")
        else:
            message = ', '.join(f'{key}={value}' for key, value in summary.items())
        self.stdout.write(self.style.SUCCESS(f'{email} → {estado}: {message}'))
