import uuid

from django.db import models, router
from django.conf import settings
from django.core.exceptions import ValidationError
from django.contrib.postgres.functions import TransactionNow
from django.utils import timezone


class FixedCharField(models.CharField):
    """Keep fixed-width SQL CHAR instead of Django's default VARCHAR."""

    def db_type(self, connection):
        return f'char({self.max_length})'


class DataRelease(models.Model):
    """Versioned release provenance without ingest or publication behavior."""

    release_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=128)
    version = models.CharField(max_length=64)
    status = models.CharField(max_length=32)
    reference_assembly = models.CharField(max_length=32)
    description = models.TextField(null=True, blank=True)
    manifest_checksum = FixedCharField(max_length=64, null=True, blank=True)
    frozen_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_default=TransactionNow())

    class Meta:
        db_table = 'data_release'
        constraints = [models.UniqueConstraint(fields=['name', 'version'], name='uq_data_release_name_version')]


class Variant(models.Model):
    """Stable variant concept independent of genomic placements."""

    variant_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    variant_type = models.CharField(max_length=32)
    canonical_name = models.CharField(max_length=255, null=True, blank=True)
    vrs_id = models.CharField(max_length=255, null=True, blank=True, unique=True)
    status = models.CharField(max_length=32, default='active', db_default='active')
    metadata = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_default=TransactionNow())

    class Meta:
        db_table = 'variant'
        indexes = [models.Index(fields=['variant_type'], name='idx_variant_type')]


class Analysis(models.Model):
    """Pipeline provenance with optional participant, sample, request and release links."""

    analysis_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    participant = models.ForeignKey(
        'participants.Participant', on_delete=models.PROTECT, db_column='participant_id',
        null=True, blank=True, db_index=False, related_name='analyses',
    )
    sample = models.ForeignKey(
        'services.Sample', on_delete=models.PROTECT, db_column='sample_id',
        null=True, blank=True, db_index=False, related_name='analyses',
    )
    release = models.ForeignKey(
        'genetics.DataRelease', on_delete=models.PROTECT, db_column='release_id',
        null=True, blank=True, db_index=False, related_name='analyses',
    )
    service_request = models.ForeignKey(
        'services.ServiceRequest', on_delete=models.PROTECT, db_column='service_request_id',
        null=True, blank=True, db_index=False, related_name='analyses',
    )
    module = models.CharField(max_length=64)
    pipeline_name = models.CharField(max_length=128)
    pipeline_version = models.CharField(max_length=64)
    container_digest = models.CharField(max_length=255, null=True, blank=True)
    reference_assembly = models.CharField(max_length=32, null=True, blank=True)
    parameters = models.JSONField(null=True, blank=True)
    status = models.CharField(max_length=32)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_default=TransactionNow())

    class Meta:
        db_table = 'analysis'
        indexes = [
            models.Index(fields=['sample'], name='idx_analysis_sample'),
            models.Index(fields=['release', 'module'], name='idx_analysis_release_module'),
        ]

    def _validate_relationships(self, using, update_fields=None):
        from participants.models import Participant
        from services.models import Sample, ServiceRequest

        fields = ('participant', 'sample', 'service_request')
        ids = {f'{field}_id': getattr(self, f'{field}_id') for field in fields}
        # Validate the combined row actually written by a partial save.
        if update_fields is not None:
            persisted = type(self).objects.using(using).filter(pk=self.pk).values(*ids).first()
            if persisted:
                for field in fields:
                    if {field, f'{field}_id'}.isdisjoint(update_fields):
                        ids[f'{field}_id'] = persisted[f'{field}_id']
        identity = None
        if ids['participant_id'] is not None:
            user_id = Participant.objects.using(using).filter(pk=ids['participant_id']).values_list(
                'user_id', flat=True,
            ).first()
            if user_id is None:
                raise ValidationError({'participant': 'An existing participant is required.'})
            identity = (ids['participant_id'], user_id)
        if ids['sample_id'] is not None:
            sample = Sample.objects.using(using).filter(pk=ids['sample_id']).values(
                'participant_id', 'participant__user_id', 'service_request__participant_id',
                'service_request__purchase__owner__django_user_id',
            ).first()
            if sample is None or (
                sample['participant_id'] != sample['service_request__participant_id']
                or sample['participant__user_id'] != sample['service_request__purchase__owner__django_user_id']
                or identity is not None and identity != (sample['participant_id'], sample['participant__user_id'])
            ):
                raise ValidationError({'sample': 'Sample, service participant and purchase owner must match.'})
            identity = (sample['participant_id'], sample['participant__user_id'])
        if ids['service_request_id'] is not None:
            request = ServiceRequest.objects.using(using).filter(pk=ids['service_request_id']).values(
                'participant_id', 'participant__user_id', 'purchase__owner__django_user_id',
            ).first()
            if request is None or (
                request['participant_id'] is None
                or request['participant__user_id'] != request['purchase__owner__django_user_id']
                or identity is not None and identity != (request['participant_id'], request['participant__user_id'])
            ):
                raise ValidationError({'service_request': 'Service participant and purchase owner must match.'})

    def clean(self):
        super().clean()
        self._validate_relationships(router.db_for_write(type(self), instance=self))

    def save(self, *args, **kwargs):
        # PROTECT intentionally differs from SQL SET NULL to retain provenance.
        # bulk_create/QuerySet.update bypass the cross-table ownership checks.
        using = kwargs.get('using') or router.db_for_write(type(self), instance=self)
        update_fields = kwargs.get('update_fields')
        if update_fields is not None:
            update_fields = kwargs['update_fields'] = frozenset(update_fields)
        self._validate_relationships(using, update_fields)
        return super().save(*args, **kwargs)


class SNP(models.Model):
    """
    Modelo para almacenar información de SNPs (Single Nucleotide Polymorphisms)
    """
    pharmacogenetic_system = models.ForeignKey(
        'PharmacogeneticSystem',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='snps',
        verbose_name="Sistema Farmacogenetico"
    )
    # Campos básicos
    rsid = models.CharField(max_length=20, verbose_name="rsID")
    genotipo = models.CharField(max_length=10, verbose_name="Genotipo")
    fenotipo = models.TextField(verbose_name="Fenotipo")
    categoria = models.CharField(max_length=50, blank=True, null=True, verbose_name="Categoría")
    grupo = models.CharField(max_length=100, blank=True, null=True, verbose_name="Grupo del Rasgo")

    # Campos genómicos
    cromosoma = models.CharField(max_length=5, blank=True, null=True, verbose_name="Cromosoma")
    posicion = models.BigIntegerField(blank=True, null=True, verbose_name="Posición genómica")
    alelo_referencia = models.CharField(max_length=50, blank=True, null=True, verbose_name="Alelo de referencia")
    alelo_alternativo = models.CharField(max_length=50, blank=True, null=True, verbose_name="Alelo alternativo")

    # Campos clínicos
    nivel_riesgo = models.CharField(max_length=50, blank=True, null=True, verbose_name="Nivel de riesgo")
    magnitud_efecto = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True, verbose_name="Magnitud del efecto")

    # Metadata
    fuente_base_datos = models.CharField(max_length=100, blank=True, null=True, verbose_name="Fuente de base de datos")
    tipo_evidencia = models.CharField(max_length=50, blank=True, null=True, verbose_name="Tipo de evidencia")
    fecha_actualizacion = models.CharField(max_length=10, blank=True, null=True, verbose_name="Fecha de actualización")

    # Datos de Ancestría - Continente
    continente = models.CharField(max_length=50, blank=True, null=True, verbose_name="Continente")
    af_continente = models.DecimalField(max_digits=5, decimal_places=4, blank=True, null=True, verbose_name="Frecuencia Alélica - Continente")
    fuente_continente = models.CharField(max_length=100, blank=True, null=True, verbose_name="Fuente - Continente")
    poblacion_continente = models.CharField(max_length=50, blank=True, null=True, verbose_name="Población - Continente")

    # Datos de Ancestría - País
    pais = models.CharField(max_length=50, blank=True, null=True, verbose_name="País")
    af_pais = models.DecimalField(max_digits=5, decimal_places=4, blank=True, null=True, verbose_name="Frecuencia Alélica - País")
    fuente_pais = models.CharField(max_length=100, blank=True, null=True, verbose_name="Fuente - País")
    poblacion_pais = models.CharField(max_length=50, blank=True, null=True, verbose_name="Población - País")

    class Meta:
        db_table = 'snps'
        verbose_name = 'SNP'
        verbose_name_plural = 'SNPs'
        unique_together = [('rsid', 'genotipo', 'fenotipo', 'categoria')]
        indexes = [
            models.Index(fields=['rsid']),
            models.Index(fields=['categoria']),
            models.Index(fields=['cromosoma']),
            models.Index(fields=['nivel_riesgo']),
        ]

    def __str__(self):
        return f"SNP({self.rsid}, {self.genotipo})"


class RsidExtraInfo(models.Model):
    """
    Extra info for rsid/genotype/phenotype combos used in reports.
    """
    rs_id = models.CharField(max_length=20, verbose_name="rsID")
    genotype = models.CharField(max_length=10, verbose_name="Genotype")
    phenotype_name = models.TextField(verbose_name="Phenotype name")
    freq_chile_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        verbose_name="Chile frequency percent",
    )
    phenotype_description = models.TextField(verbose_name="Phenotype description")

    class Meta:
        db_table = 'rsid_extra_info'
        verbose_name = 'RSID extra info'
        verbose_name_plural = 'RSID extra info'
        unique_together = [('rs_id', 'genotype', 'phenotype_name')]
        indexes = [
            models.Index(fields=['rs_id'], name='rsid_extra_rsid_idx'),
            models.Index(fields=['phenotype_name'], name='rsid_extra_pheno_idx'),
        ]

    def __str__(self):
        return f"RsidExtraInfo({self.rs_id}, {self.genotype})"


class UserSNP(models.Model):
    """
    Modelo de relación entre usuarios y sus SNPs
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='user_snps',
        verbose_name="Usuario"
    )
    snp = models.ForeignKey(
        SNP,
        on_delete=models.CASCADE,
        related_name='user_associations',
        verbose_name="SNP"
    )

    class Meta:
        db_table = 'user_snps'
        verbose_name = 'SNP de Usuario'
        verbose_name_plural = 'SNPs de Usuarios'
        unique_together = [('user', 'snp')]
        indexes = [
            models.Index(fields=['user']),
            models.Index(fields=['snp']),
        ]

    def __str__(self):
        return f"UserSNP(user={self.user_id}, snp={self.snp_id})"


class PharmacogeneticSystem(models.Model):
    """Sistema o grupo para clasificar SNPs farmacogenéticos."""
    name = models.CharField(max_length=100, unique=True, verbose_name='Nombre del Sistema')
    description = models.TextField(blank=True, null=True, verbose_name='Descripción')

    class Meta:
        verbose_name = 'Sistema Farmacogenético'
        verbose_name_plural = 'Sistemas Farmacogenéticos'

    def __str__(self):
        return self.name
