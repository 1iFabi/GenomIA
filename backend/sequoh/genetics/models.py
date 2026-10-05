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


class PostgreSQLIndex(models.Index):
    """Allow exact PostgreSQL identifiers beyond Django's portable 30-character limit."""

    max_name_length = 63


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


class ReleaseVariant(models.Model):
    """Variant membership with optional placement and inclusion provenance."""

    pk = models.CompositePrimaryKey('release_id', 'variant_id')
    release = models.ForeignKey(
        'genetics.DataRelease', on_delete=models.CASCADE, db_column='release_id',
        db_index=False, related_name='variant_memberships',
    )
    variant = models.ForeignKey(
        'genetics.Variant', on_delete=models.RESTRICT, db_column='variant_id',
        db_index=False, related_name='release_memberships',
    )
    placement = models.ForeignKey(
        'genetics.VariantPlacement', on_delete=models.RESTRICT, db_column='placement_id',
        null=True, blank=True, db_index=False, related_name='release_memberships',
    )
    included_by_analysis = models.ForeignKey(
        'genetics.Analysis', on_delete=models.SET_NULL, db_column='included_by_analysis_id',
        null=True, blank=True, db_index=False, related_name='included_variant_memberships',
    )
    inclusion_status = models.CharField(max_length=32, default='included', db_default='included')
    created_at = models.DateTimeField(default=timezone.now, db_default=TransactionNow())

    class Meta:
        db_table = 'release_variant'
        indexes = [models.Index(fields=['variant'], name='idx_release_variant_variant')]


class ReleaseEpigeneticFeature(models.Model):
    """Epigenetic feature membership with optional inclusion provenance."""

    pk = models.CompositePrimaryKey('release_id', 'epigenetic_feature_id')
    release = models.ForeignKey(
        'genetics.DataRelease', on_delete=models.CASCADE, db_column='release_id',
        db_index=False, related_name='epigenetic_feature_memberships',
    )
    epigenetic_feature = models.ForeignKey(
        'genetics.EpigeneticFeature', on_delete=models.RESTRICT, db_column='epigenetic_feature_id',
        db_index=False, related_name='release_memberships',
    )
    included_by_analysis = models.ForeignKey(
        'genetics.Analysis', on_delete=models.SET_NULL, db_column='included_by_analysis_id',
        null=True, blank=True, db_index=False, related_name='included_epigenetic_feature_memberships',
    )
    created_at = models.DateTimeField(default=timezone.now, db_default=TransactionNow())

    class Meta:
        db_table = 'release_epigenetic_feature'
        indexes = [models.Index(fields=['epigenetic_feature'], name='idx_release_epi_feature')]


class Genotype(models.Model):
    """Materialized genotype calls without inferred biological or ownership rules."""

    genotype_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    release = models.ForeignKey(
        'genetics.DataRelease', on_delete=models.CASCADE, db_column='release_id',
        db_index=False, related_name='genotypes',
    )
    variant = models.ForeignKey(
        'genetics.Variant', on_delete=models.PROTECT, db_column='variant_id',
        db_index=False, related_name='genotypes',
    )
    participant = models.ForeignKey(
        'participants.Participant', on_delete=models.PROTECT, db_column='participant_id',
        db_index=False, related_name='genotypes',
    )
    sample = models.ForeignKey(
        'services.Sample', on_delete=models.SET_NULL, db_column='sample_id',
        null=True, blank=True, db_index=False, related_name='genotypes',
    )
    analysis = models.ForeignKey(
        'genetics.Analysis', on_delete=models.PROTECT, db_column='analysis_id',
        db_index=False, related_name='genotypes',
    )
    genotype = models.CharField(max_length=32)
    phased = models.BooleanField(default=False, db_default=False)
    phase_set = models.CharField(max_length=64, null=True, blank=True)
    dosage = models.DecimalField(max_digits=6, decimal_places=3, null=True, blank=True)
    genotype_quality = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    read_depth = models.IntegerField(null=True, blank=True)
    allele_depths = models.JSONField(null=True, blank=True)
    filters = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_default=TransactionNow())

    class Meta:
        db_table = 'genotype'
        indexes = [
            PostgreSQLIndex(fields=['participant', 'release'], name='idx_genotype_participant_release'),
            models.Index(fields=['variant', 'release'], name='idx_genotype_variant_release'),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['analysis', 'participant', 'sample', 'variant'], name='uq_genotype_analysis_sample_variant',
            ),
            models.CheckConstraint(condition=models.Q(genotype_quality__gte=0), name='genotype_quality_gte_0'),
            models.CheckConstraint(condition=models.Q(read_depth__gte=0), name='genotype_read_depth_gte_0'),
        ]


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


class VariantPlacement(models.Model):
    """Assembly-specific placement and representation of a stable variant."""

    placement_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    variant = models.ForeignKey(
        'genetics.Variant', on_delete=models.CASCADE, db_column='variant_id',
        db_index=False, related_name='placements',
    )
    reference_assembly = models.CharField(max_length=32)
    contig = models.CharField(max_length=64)
    start_pos = models.BigIntegerField()
    end_pos = models.BigIntegerField()
    coordinate_system = models.CharField(max_length=32, default='1-based-inclusive', db_default='1-based-inclusive')
    reference_allele = models.TextField(null=True, blank=True)
    alternate_allele = models.TextField(null=True, blank=True)
    strand = FixedCharField(max_length=1, null=True, blank=True)
    sv_length = models.BigIntegerField(null=True, blank=True)
    breakend = models.JSONField(null=True, blank=True)
    is_canonical = models.BooleanField(default=False, db_default=False)
    normalized = models.BooleanField(default=False, db_default=False)
    metadata = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_default=TransactionNow())

    class Meta:
        db_table = 'variant_placement'
        indexes = [
            models.Index(fields=['reference_assembly', 'contig', 'start_pos', 'end_pos'], name='idx_variant_placement_region'),
            models.Index(fields=['variant'], name='idx_variant_placement_variant'),
        ]
        constraints = [
            models.CheckConstraint(condition=models.Q(start_pos__gte=1), name='variant_placement_start_gte_1'),
            models.CheckConstraint(condition=models.Q(end_pos__gte=models.F('start_pos')), name='variant_placement_end_gte_start'),
        ]


class ExternalIdentifier(models.Model):
    """External accessions and lifecycle links, not variant identity resolution."""

    external_identifier_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    variant = models.ForeignKey(
        'genetics.Variant', on_delete=models.CASCADE, db_column='variant_id',
        db_index=False, related_name='external_identifiers',
    )
    replaced_by_identifier = models.ForeignKey(
        'self', on_delete=models.SET_NULL, db_column='replaced_by_identifier_id',
        null=True, blank=True, db_index=False, related_name='replaced_identifiers',
    )
    namespace = models.CharField(max_length=64)
    accession = models.CharField(max_length=255)
    version = models.CharField(max_length=64, null=True, blank=True)
    status = models.CharField(max_length=32, default='active', db_default='active')
    source_release = models.CharField(max_length=128, null=True, blank=True)
    is_primary = models.BooleanField(default=False, db_default=False)
    created_at = models.DateTimeField(default=timezone.now, db_default=TransactionNow())

    class Meta:
        db_table = 'external_identifier'
        indexes = [models.Index(fields=['namespace', 'accession'], name='idx_external_identifier_lookup')]
        constraints = [models.UniqueConstraint(fields=['namespace', 'accession', 'version'], name='uq_external_identifier')]


class VariantAnnotation(models.Model):
    """Versioned source annotations without inferred clinical or biological rules."""

    annotation_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    variant = models.ForeignKey(
        'genetics.Variant', on_delete=models.CASCADE, db_column='variant_id',
        db_index=False, related_name='annotations',
    )
    placement = models.ForeignKey(
        'genetics.VariantPlacement', on_delete=models.SET_NULL, db_column='placement_id',
        null=True, blank=True, db_index=False, related_name='annotations',
    )
    analysis = models.ForeignKey(
        'genetics.Analysis', on_delete=models.SET_NULL, db_column='analysis_id',
        null=True, blank=True, db_index=False, related_name='annotations',
    )
    source_name = models.CharField(max_length=128)
    source_version = models.CharField(max_length=64)
    annotation_type = models.CharField(max_length=96)
    gene_symbol = models.CharField(max_length=64, null=True, blank=True)
    transcript_id = models.CharField(max_length=128, null=True, blank=True)
    consequence = models.CharField(max_length=128, null=True, blank=True)
    clinical_significance = models.CharField(max_length=128, null=True, blank=True)
    evidence_level = models.CharField(max_length=64, null=True, blank=True)
    score = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True)
    citation_id = models.CharField(max_length=128, null=True, blank=True)
    payload = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_default=TransactionNow())

    class Meta:
        db_table = 'variant_annotation'
        indexes = [
            models.Index(fields=['variant'], name='idx_variant_annotation_variant'),
            models.Index(fields=['source_name', 'source_version'], name='idx_variant_annotation_source'),
            models.Index(fields=['gene_symbol'], name='idx_variant_annotation_gene'),
        ]


class AlleleFrequency(models.Model):
    """Source-reported allele frequencies without inferred count consistency."""

    frequency_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    release = models.ForeignKey(
        'genetics.DataRelease', on_delete=models.SET_NULL, db_column='release_id',
        null=True, blank=True, db_index=False, related_name='allele_frequencies',
    )
    variant = models.ForeignKey(
        'genetics.Variant', on_delete=models.PROTECT, db_column='variant_id',
        db_index=False, related_name='allele_frequencies',
    )
    population = models.ForeignKey(
        'genetics.Population', on_delete=models.PROTECT, db_column='population_id',
        db_index=False, related_name='allele_frequencies',
    )
    analysis = models.ForeignKey(
        'genetics.Analysis', on_delete=models.SET_NULL, db_column='analysis_id',
        null=True, blank=True, db_index=False, related_name='allele_frequencies',
    )
    source_name = models.CharField(max_length=128)
    source_version = models.CharField(max_length=64)
    allele = models.TextField()
    allele_count = models.BigIntegerField(null=True, blank=True)
    allele_number = models.BigIntegerField(null=True, blank=True)
    allele_frequency = models.DecimalField(max_digits=12, decimal_places=10, null=True, blank=True)
    homozygote_count = models.BigIntegerField(null=True, blank=True)
    heterozygote_count = models.BigIntegerField(null=True, blank=True)
    sample_count = models.BigIntegerField(null=True, blank=True)
    quality_flags = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_default=TransactionNow())

    class Meta:
        db_table = 'allele_frequency'
        indexes = [
            PostgreSQLIndex(fields=['variant', 'population'], name='idx_frequency_variant_population'),
            models.Index(fields=['source_name', 'source_version'], name='idx_frequency_source'),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['release', 'variant', 'population', 'source_name', 'source_version', 'allele'],
                name='uq_allele_frequency_record',
            ),
            models.CheckConstraint(condition=models.Q(allele_count__gte=0), name='allele_frequency_allele_count_gte_0'),
            models.CheckConstraint(condition=models.Q(allele_number__gte=0), name='allele_frequency_allele_number_gte_0'),
            models.CheckConstraint(condition=models.Q(homozygote_count__gte=0), name='allele_frequency_homozygote_count_gte_0'),
            models.CheckConstraint(condition=models.Q(heterozygote_count__gte=0), name='allele_frequency_heterozygote_count_gte_0'),
            models.CheckConstraint(condition=models.Q(sample_count__gte=0), name='allele_frequency_sample_count_gte_0'),
            models.CheckConstraint(
                condition=models.Q(allele_frequency__gte=0, allele_frequency__lte=1),
                name='allele_frequency_value_range',
            ),
        ]


class Population(models.Model):
    """Hierarchical population reference without inferred biological semantics."""

    population_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    parent_population = models.ForeignKey(
        'self', on_delete=models.SET_NULL, db_column='parent_population_id',
        null=True, blank=True, db_index=False, related_name='child_populations',
    )
    code = models.CharField(max_length=64)
    name = models.CharField(max_length=128)
    description = models.TextField(null=True, blank=True)
    geographic_region = models.CharField(max_length=128, null=True, blank=True)
    is_internal = models.BooleanField(default=False, db_default=False)
    is_masked = models.BooleanField(default=False, db_default=False)
    metadata = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_default=TransactionNow())

    class Meta:
        db_table = 'population'
        # A constraint avoids Django's extra VARCHAR pattern index from unique=True.
        constraints = [models.UniqueConstraint(fields=['code'], name='uq_population_code')]


class EpigeneticFeature(models.Model):
    """Stable epigenetic site or region without biological interpretation."""

    epigenetic_feature_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    feature_type = models.CharField(max_length=64)
    reference_assembly = models.CharField(max_length=32)
    contig = models.CharField(max_length=64)
    start_pos = models.BigIntegerField()
    end_pos = models.BigIntegerField()
    coordinate_system = models.CharField(max_length=32, default='1-based-inclusive', db_default='1-based-inclusive')
    strand = FixedCharField(max_length=1, null=True, blank=True)
    modification_code = models.CharField(max_length=32, null=True, blank=True)
    name = models.CharField(max_length=255, null=True, blank=True)
    metadata = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_default=TransactionNow())

    class Meta:
        db_table = 'epigenetic_feature'
        indexes = [
            models.Index(fields=['reference_assembly', 'contig', 'start_pos', 'end_pos'], name='idx_epigenetic_feature_region'),
        ]
        constraints = [
            models.CheckConstraint(condition=models.Q(start_pos__gte=1), name='epigenetic_feature_start_gte_1'),
            models.CheckConstraint(condition=models.Q(end_pos__gte=models.F('start_pos')), name='epigenetic_feature_end_gte_start'),
        ]


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
