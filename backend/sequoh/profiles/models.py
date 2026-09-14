from django.db import models
from django.conf import settings
from django.utils import timezone
from django.core.exceptions import ValidationError
import re


class ServiceStatus(models.TextChoices):
    NO_PURCHASED = "NO_PURCHASED", "Sin servicio"
    PENDING = "PENDING", "Pendiente"
    COMPLETED = "COMPLETED", "Completado"


class SampleStatus(models.TextChoices):
    PENDING_COLLECTION = "PENDING_COLLECTION", "Pendiente de toma"
    COLLECTED_PENDING_ANALYSIS = "COLLECTED_PENDING_ANALYSIS", "Muestra tomada / Pendiente de análisis"
    SENT_TO_LAB = "SENT_TO_LAB", "Enviada al laboratorio"
    RECEIVED_AT_LAB = "RECEIVED_AT_LAB", "Recibida en laboratorio"


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


class Profile(models.Model):
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
    # Estado del servicio para distinguir 3 tipos de usuario
    service_status = models.CharField(
        max_length=20,
        choices=ServiceStatus.choices,
        default=ServiceStatus.NO_PURCHASED,
        db_index=True,
    )
    service_updated_at = models.DateTimeField(auto_now=True)
    sample_code = models.CharField(
        max_length=30,
        unique=True,
        null=True,
        blank=True,
        db_index=True,
        verbose_name='Código de Muestra'
    )
    sample_code_created_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Fecha de creación del código'
    )
    sample_status = models.CharField(
        max_length=40,
        choices=SampleStatus.choices,
        default=SampleStatus.PENDING_COLLECTION,
        db_index=True,
        verbose_name='Estado de la muestra'
    )
    arrival_confirmed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Llegada confirmada en recepción'
    )
    sample_taken_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Fecha de toma de muestra'
    )
    sample_sent_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Fecha de envío al laboratorio'
    )
    # Nombre del archivo de reporte genético
    report_filename = models.CharField(max_length=255, blank=True, null=True)
    # Fecha de carga del reporte
    report_uploaded_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Profile(user={self.user_id}, rut={self.rut}, phone={self.phone})"
