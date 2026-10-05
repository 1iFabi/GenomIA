import argparse
import re

from django.core.management.base import BaseCommand, CommandError

from genetics.synthetic_import import DISCLAIMER, DEMO_NAME, DEMO_VERSION, import_synthetic_genomics, validate_user_id


def _user_id(value):
    if not re.fullmatch(r'[1-9][0-9]{0,18}', value):
        raise argparse.ArgumentTypeError('Specify a positive decimal Django User ID.')
    try:
        return validate_user_id(int(value))
    except CommandError as error:
        raise argparse.ArgumentTypeError(str(error)) from error


class Command(BaseCommand):
    help = (
        'Import the bundled versioned SYNTHETIC non-clinical genomics demo for one existing client. '
        'Local development only; explicit --user-id required. No files, consent, or clinical completion.'
    )
    requires_system_checks = []  # The fail-closed guard must precede any database access.

    def add_arguments(self, parser):
        parser.add_argument('--user-id', required=True, type=_user_id, help='Existing Django User ID (not AppUser UUID).')

    def handle(self, *args, **options):
        receipt = import_synthetic_genomics(user_id=options['user_id'])
        outcome = 'created' if receipt.created else 'already imported (validated; no changes)'
        self.stdout.write(
            f'{DEMO_NAME} v{DEMO_VERSION}: {outcome}; 6 SYNTHETIC placeholders. '
            f'Simulated PAID purchase {receipt.purchase_id}; '
            f'WAITING_SAMPLE request {receipt.service_request_id}; synthetic sample {receipt.sample_id}. '
            f'{DISCLAIMER} No consent was granted or changed.'
        )
