from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
import re


def validate_rut_format(value):
    """
    Valida que el RUT tenga el formato XXXXXXX-R donde:
    - X son números (7-8 dígitos)
    - R puede ser un dígito (0-9) o la letra K
    """
    if value is None or value == '':
        return value

    # Formato: 7-8 dígitos, guión, y luego 0-9 o K
    pattern = r'^\d{7,8}-[0-9Kk]$'
    if not re.match(pattern, value):
        raise ValidationError('El RUT debe tener el formato XXXXXXX-R (ejemplo: 12345678-9 o 1234567-K)')

    return value


def normalize_rut(raw):
    """Return the RUT as 12345678-K when format and check digit are valid, else None."""
    rut = re.sub(r'[.\s]', '', str(raw or '')).upper()
    match = re.fullmatch(r'(\d{7,8})-([\dK])', rut)
    if not match:
        return None
    total = sum(int(d) * f for d, f in zip(reversed(match[1]), [2, 3, 4, 5, 6, 7] * 2))
    check = {11: '0', 10: 'K'}.get(11 - total % 11, str(11 - total % 11))
    return rut if check == match[2] else None


class Profile(models.Model):
    """Purchase identity (RUT, phone). Created only when the client starts a purchase, never at signup."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profile')
    phone = models.CharField(max_length=20, blank=True)
    rut = models.CharField(
        max_length=12,
        unique=True,
        null=True,
        blank=True,
        validators=[validate_rut_format],
        help_text='RUT en formato XXXXXXX-R (ejemplo: 12345678-9 o 1234567-K)',
        verbose_name='RUT'
    )

    def __str__(self):
        return f"Profile(user={self.user_id}, rut={self.rut}, phone={self.phone})"
