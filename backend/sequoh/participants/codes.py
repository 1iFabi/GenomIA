import secrets

from accounts.models import AppUser, Role
from participants.models import Participant


def new_client_code():
    return f'GX-{secrets.token_hex(4).upper()}'


def ensure_client_code(user):
    """Give a verified client their Sample ID (stored as the participant code); staff get none."""
    if not AppUser.objects.filter(django_user=user, role__code=Role.Code.CLIENTE).exists():
        return None
    participant, _ = Participant.objects.get_or_create(
        user=user, defaults={'participant_code': new_client_code()},
    )
    return participant.participant_code
