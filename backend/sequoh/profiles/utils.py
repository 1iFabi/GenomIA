import uuid

from django.utils import timezone

from .models import Profile


def ensure_sample_code(profile: Profile) -> str:
    """Genera un SampleCode si no existe."""
    if profile.sample_code:
        return profile.sample_code
    code = f"SC-{profile.user_id:05d}-{uuid.uuid4().hex[:5].upper()}"
    profile.sample_code = code
    profile.sample_code_created_at = timezone.now()
    profile.save(update_fields=["sample_code", "sample_code_created_at"])
    return code
