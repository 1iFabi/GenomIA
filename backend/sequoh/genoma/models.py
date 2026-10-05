import uuid

from django.db import models, router
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
        'genoma.DataRelease', on_delete=models.CASCADE, db_column='release_id',
        db_index=False, related_name='variant_memberships',
    )
    variant = models.ForeignKey(
        'genoma.Variant', on_delete=models.RESTRICT, db_column='variant_id',
        db_index=False, related_name='release_memberships',
    )
    placement = models.ForeignKey(
        'genoma.VariantPlacement', on_delete=models.RESTRICT, db_column='placement_id',
        null=True, blank=True, db_index=False, related_name='release_memberships',
    )
    included_by_analysis = models.ForeignKey(
        'genoma.Analysis', on_delete=models.SET_NULL, db_column='included_by_analysis_id',
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
        'genoma.DataRelease', on_delete=models.CASCADE, db_column='release_id',
        db_index=False, related_name='epigenetic_feature_memberships',
    )
    epigenetic_feature = models.ForeignKey(
        'genoma.EpigeneticFeature', on_delete=models.RESTRICT, db_column='epigenetic_feature_id',
        db_index=False, related_name='release_memberships',
    )
    included_by_analysis = models.ForeignKey(
        'genoma.Analysis', on_delete=models.SET_NULL, db_column='included_by_analysis_id',
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
        'genoma.DataRelease', on_delete=models.CASCADE, db_column='release_id',
        db_index=False, related_name='genotypes',
    )
    variant = models.ForeignKey(
        'genoma.Variant', on_delete=models.PROTECT, db_column='variant_id',
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
        'genoma.Analysis', on_delete=models.PROTECT, db_column='analysis_id',
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


class Artifact(models.Model):
    """Provenance metadata for files stored outside PostgreSQL."""

    artifact_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    analysis = models.ForeignKey(
        'genoma.Analysis', on_delete=models.SET_NULL, db_column='analysis_id',
        null=True, blank=True, db_index=False, related_name='artifacts',
    )
    release = models.ForeignKey(
        'genoma.DataRelease', on_delete=models.SET_NULL, db_column='release_id',
        null=True, blank=True, db_index=False, related_name='artifacts',
    )
    sample = models.ForeignKey(
        'services.Sample', on_delete=models.SET_NULL, db_column='sample_id',
        null=True, blank=True, db_index=False, related_name='artifacts',
    )
    role = models.CharField(max_length=32)
    artifact_type = models.CharField(max_length=64)
    format = models.CharField(max_length=64)
    uri = models.TextField()
    checksum_sha256 = FixedCharField(max_length=64)
    size_bytes = models.BigIntegerField(null=True, blank=True)
    reference_assembly = models.CharField(max_length=32, null=True, blank=True)
    metadata = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_default=TransactionNow())

    class Meta:
        db_table = 'artifact'
        indexes = [
            models.Index(fields=['analysis'], name='idx_artifact_analysis'),
            models.Index(fields=['checksum_sha256'], name='idx_artifact_checksum'),
        ]
        constraints = [
            models.CheckConstraint(condition=models.Q(size_bytes__gte=0), name='artifact_size_bytes_gte_0'),
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
        'genoma.Variant', on_delete=models.CASCADE, db_column='variant_id',
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
        'genoma.Variant', on_delete=models.CASCADE, db_column='variant_id',
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
        'genoma.Variant', on_delete=models.CASCADE, db_column='variant_id',
        db_index=False, related_name='annotations',
    )
    placement = models.ForeignKey(
        'genoma.VariantPlacement', on_delete=models.SET_NULL, db_column='placement_id',
        null=True, blank=True, db_index=False, related_name='annotations',
    )
    analysis = models.ForeignKey(
        'genoma.Analysis', on_delete=models.SET_NULL, db_column='analysis_id',
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
        'genoma.DataRelease', on_delete=models.SET_NULL, db_column='release_id',
        null=True, blank=True, db_index=False, related_name='allele_frequencies',
    )
    variant = models.ForeignKey(
        'genoma.Variant', on_delete=models.PROTECT, db_column='variant_id',
        db_index=False, related_name='allele_frequencies',
    )
    population = models.ForeignKey(
        'genoma.Population', on_delete=models.PROTECT, db_column='population_id',
        db_index=False, related_name='allele_frequencies',
    )
    analysis = models.ForeignKey(
        'genoma.Analysis', on_delete=models.SET_NULL, db_column='analysis_id',
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
        'genoma.DataRelease', on_delete=models.PROTECT, db_column='release_id',
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


class AnalysisResult(models.Model):
    """Module-specific result values with nullable links to their source entities."""

    result_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    analysis = models.ForeignKey(
        'genoma.Analysis', on_delete=models.PROTECT, db_column='analysis_id',
        db_index=False, related_name='results',
    )
    participant = models.ForeignKey(
        'participants.Participant', on_delete=models.SET_NULL, db_column='participant_id',
        null=True, blank=True, db_index=False, related_name='analysis_results',
    )
    sample = models.ForeignKey(
        'services.Sample', on_delete=models.SET_NULL, db_column='sample_id',
        null=True, blank=True, db_index=False, related_name='analysis_results',
    )
    release = models.ForeignKey(
        'genoma.DataRelease', on_delete=models.SET_NULL, db_column='release_id',
        null=True, blank=True, db_index=False, related_name='analysis_results',
    )
    variant = models.ForeignKey(
        'genoma.Variant', on_delete=models.SET_NULL, db_column='variant_id',
        null=True, blank=True, db_index=False, related_name='analysis_results',
    )
    epigenetic_feature = models.ForeignKey(
        'genoma.EpigeneticFeature', on_delete=models.SET_NULL, db_column='epigenetic_feature_id',
        null=True, blank=True, db_index=False, related_name='analysis_results',
    )
    population = models.ForeignKey(
        'genoma.Population', on_delete=models.SET_NULL, db_column='population_id',
        null=True, blank=True, db_index=False, related_name='analysis_results',
    )
    module = models.CharField(max_length=64)
    result_type = models.CharField(max_length=96)
    reference_assembly = models.CharField(max_length=32, null=True, blank=True)
    contig = models.CharField(max_length=64, null=True, blank=True)
    start_pos = models.BigIntegerField(null=True, blank=True)
    end_pos = models.BigIntegerField(null=True, blank=True)
    haplotype = models.SmallIntegerField(null=True, blank=True)
    value_numeric = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True)
    value_text = models.TextField(null=True, blank=True)
    value_code = models.CharField(max_length=128, null=True, blank=True)
    unit = models.CharField(max_length=64, null=True, blank=True)
    percentile = models.DecimalField(max_digits=7, decimal_places=4, null=True, blank=True)
    confidence = models.DecimalField(max_digits=7, decimal_places=6, null=True, blank=True)
    payload = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_default=TransactionNow())

    class Meta:
        db_table = 'analysis_result'
        indexes = [
            models.Index(fields=['participant', 'module'], name='idx_result_participant_module'),
            models.Index(fields=['analysis'], name='idx_result_analysis'),
            models.Index(
                fields=['reference_assembly', 'contig', 'start_pos', 'end_pos'], name='idx_result_interval',
            ),
        ]
        constraints = [
            models.CheckConstraint(condition=models.Q(start_pos__gte=1), name='analysis_result_start_pos_gte_1'),
            models.CheckConstraint(
                condition=models.Q(end_pos__gte=models.F('start_pos')),
                name='analysis_result_end_pos_gte_start',
            ),
            models.CheckConstraint(condition=models.Q(haplotype__gte=0), name='analysis_result_haplotype_gte_0'),
            models.CheckConstraint(
                condition=models.Q(percentile__gte=0, percentile__lte=100),
                name='analysis_result_percentile_0_100',
            ),
            models.CheckConstraint(
                condition=models.Q(confidence__gte=0, confidence__lte=1),
                name='analysis_result_confidence_0_1',
            ),
        ]
