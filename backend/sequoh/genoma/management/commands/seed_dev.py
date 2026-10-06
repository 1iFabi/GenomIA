import hashlib
import random
from datetime import timedelta
from decimal import Decimal

from allauth.account.models import EmailAddress
from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from accounts.models import (
    EmailVerification, PasswordResetToken, RegistrationEmailChallenge, RevokedToken, WelcomeStatus,
)
from accounts.roles import grant_admin_role, grant_analyst_role, grant_reception_role
from genoma.models import (
    AlleleFrequency, Analysis, AnalysisResult, Artifact, DataRelease, EpigeneticFeature, ExternalIdentifier,
    Genotype, Population, ReleaseEpigeneticFeature, ReleaseVariant, Variant, VariantAnnotation, VariantPlacement,
)
from genoma.synthetic_import import _require_local_development, import_synthetic_genomics
from participants.codes import ensure_client_code
from participants.models import Observation, Participant, ParticipantMetadata, ParticipantMetadataLink
from profiles.models import Profile
from services.models import Purchase, PurchaseStatus, Sample, ServiceRequest, ServiceStatus, ServiceStatusLog
from services.views import STATUS_SEQUENCE

SEED_RELEASE = 'GenomIA dev seed'
PASSWORD = 'GenomIA-dev-2026!'
STAFF = (('admin.dev', 'Ada', 'Admin', grant_admin_role),
         ('analista.dev', 'Ana', 'Analista', grant_analyst_role),
         ('recepcion.dev', 'Raúl', 'Recepción', grant_reception_role))
# One client per service state; 'DEMO' gets the bundled synthetic genomics demo the result pages read.
CLIENTS = (('cliente.sin_compra', None), ('cliente.esperando', 'WAITING_SAMPLE'),
           ('cliente.muestra', 'SAMPLE_RECEIVED'), ('cliente.procesando', 'PROCESSING'),
           ('cliente.completo', 'COMPLETED'), ('cliente.demo', 'DEMO'))
POPULATIONS = (('AMR', 'Americas', None, False, False), ('CHL', 'Chile', 'AMR', True, False),
               ('MAPUCHE_MASKED', 'Mapuche (masked)', 'CHL', True, True), ('EUR', 'Europe', None, False, False),
               ('AFR', 'Africa', None, False, False), ('EAS', 'East Asia', None, False, False))
FREQUENCY_POPULATIONS = ('CHL', 'EUR', 'AFR', 'EAS')
PGX = (('CYP2C19', '*1/*2', 'Intermediate metabolizer'), ('CYP2D6', '*1/*1', 'Normal metabolizer'),
       ('SLCO1B1', '*1/*5', 'Decreased function'))
VARIANTS_NEEDED = 60


def _checksum(text):
    return hashlib.sha256(text.encode()).hexdigest()


class Command(BaseCommand):
    help = ('Populate every domain table with SYNTHETIC local-development data: staff, clients in each '
            'service state, participants, samples, analyses, genotypes, frequencies and methylation. '
            f'Run once on a fresh database; all accounts use password "{PASSWORD}".')
    requires_system_checks = []

    def handle(self, *args, **options):
        _require_local_development()
        if DataRelease.objects.filter(name=SEED_RELEASE).exists():
            raise CommandError('Database already seeded. Recreate the database to seed again.')
        self.rng = random.Random(42)
        self.now = timezone.now()
        with transaction.atomic():
            self.seed()
        self.report()

    def seed(self):
        self.release = DataRelease.objects.create(
            name=SEED_RELEASE, version='1', status='synthetic', reference_assembly='GRCh38',
            description='SYNTHETIC development data. Not clinical, not real participants.',
        )
        self.variants = self.seed_variants()
        self.populations = self.seed_populations()
        self.features = self.seed_epigenetic_features()
        self.seed_frequencies()
        self.forms = self.seed_forms()

        users = get_user_model().objects
        self.staff = {}
        for index, (username, first, last, grant) in enumerate(STAFF):
            user = self.create_account(users, username, first, last, index)
            grant(user)
            self.staff[username] = user.app_user
        for index, (username, state) in enumerate(CLIENTS, start=len(STAFF)):
            user = self.create_account(users, username, username.split('.')[1].replace('_', ' ').title(),
                                       'Cliente', index)
            if state == 'DEMO':
                import_synthetic_genomics(user_id=user.pk, version='2')
            elif state:
                self.seed_client_service(user, state, index)
            else:
                ensure_client_code(user)  # Same Sample ID a verified client gets in the welcome email.
        self.seed_account_tokens(users.get(username='cliente.esperando'))

    def create_account(self, users, username, first, last, index):
        email = f'{username}@genomia.dev'
        user = users.create_user(username=username, email=email, password=PASSWORD,
                                 first_name=first, last_name=last)
        EmailAddress.objects.create(user=user, email=email, verified=True, primary=True)
        Profile.objects.create(user=user, phone=f'+5691234{index:04d}', rut=f'{20000000 + index}-K')
        WelcomeStatus.objects.create(user=user, welcome_sent=True, sent_at=self.now)
        return user

    def seed_variants(self):
        variants = list(Variant.objects.filter(placements__reference_assembly='GRCh38')
                        .distinct().order_by('created_at', 'pk')[:VARIANTS_NEEDED])
        # Without the ClinVar catalog, create enough synthetic variants to keep every table populated.
        for index in range(len(variants), VARIANTS_NEEDED):
            start = 2_000_000 + index * 997
            variant = Variant.objects.create(variant_type='SNV', canonical_name=f'Synthetic SNV {index}',
                                             metadata={'seed': True})
            VariantPlacement.objects.create(variant=variant, reference_assembly='GRCh38', contig='1',
                                            start_pos=start, end_pos=start, reference_allele='C',
                                            alternate_allele='T', is_canonical=True)
            ExternalIdentifier.objects.create(variant=variant, namespace='GenomIA-seed', accession=f'SEED{index}',
                                              is_primary=True)
            VariantAnnotation.objects.create(variant=variant, source_name='GenomIA-seed', source_version='1',
                                             annotation_type='synthetic', gene_symbol='SYN1')
            variants.append(variant)
        for variant in variants:
            ReleaseVariant.objects.create(release=self.release, variant=variant,
                                          placement=variant.placements.order_by('pk').first())
        return variants

    def seed_populations(self):
        populations = {}
        for code, name, parent, internal, masked in POPULATIONS:
            populations[code], _ = Population.objects.get_or_create(code=code, defaults={
                'name': name, 'parent_population': populations.get(parent), 'is_internal': internal,
                'is_masked': masked, 'geographic_region': name, 'metadata': {'seed': True},
            })
        return populations

    def seed_epigenetic_features(self):
        features = []
        for index in range(20):
            start = 1_000_000 + index * 1500
            feature = EpigeneticFeature.objects.create(
                feature_type='cpg_site', reference_assembly='GRCh38', contig='1', start_pos=start, end_pos=start + 1,
                strand='+', modification_code='m', name=f'CpG chr1:{start}', metadata={'seed': True},
            )
            ReleaseEpigeneticFeature.objects.create(release=self.release, epigenetic_feature=feature)
            features.append(feature)
        return features

    def seed_frequencies(self):
        for variant in self.variants:
            allele = variant.placements.order_by('pk').first().alternate_allele or 'N'
            for code in FREQUENCY_POPULATIONS:
                samples = self.rng.randint(500, 5000)
                allele_number = samples * 2
                allele_count = self.rng.randint(0, allele_number // 2)
                homozygotes = self.rng.randint(0, allele_count // 4)
                AlleleFrequency.objects.create(
                    release=self.release, variant=variant, population=self.populations[code],
                    source_name='GenomIA-seed', source_version='1', allele=allele, allele_count=allele_count,
                    allele_number=allele_number, sample_count=samples, homozygote_count=homozygotes,
                    heterozygote_count=allele_count - 2 * homozygotes,
                    allele_frequency=(Decimal(allele_count) / allele_number).quantize(Decimal('1e-10')),
                )

    def seed_forms(self):
        consent = ParticipantMetadata.objects.create(
            name='Consentimiento informado', type='consent', version=1, description='Consentimiento GenomIA v1',
            questionary={'items': [{'id': 'accept', 'text': 'Acepto participar', 'type': 'boolean'}]},
        )
        health = ParticipantMetadata.objects.create(
            name='Cuestionario de salud', type='form', version=1, description='Antecedentes básicos',
            questionary={'items': [{'id': 'smoker', 'type': 'boolean'}, {'id': 'family_history', 'type': 'text'}]},
        )
        return consent, health

    def seed_client_service(self, user, state, index):
        started = self.now - timedelta(days=30 - index)
        participant = Participant.objects.create(
            user=user, participant_code=f'SEED-{user.username.upper()}', enrollment_status='active',
            consent_status='granted', consent_version='v1', consented_at=started, metadata={'seed': True},
        )
        consent, health = self.forms
        ParticipantMetadataLink.objects.create(idm=consent, idp=participant, answer={'accept': True},
                                               first_date=started.date(), last_update=started.date())
        ParticipantMetadataLink.objects.create(idm=health, idp=participant,
                                               answer={'smoker': index % 2 == 0, 'family_history': 'ninguno'},
                                               first_date=started.date(), last_update=started.date())
        steps = STATUS_SEQUENCE[:STATUS_SEQUENCE.index(state) + 1]
        purchase = Purchase.objects.create(owner=user.app_user, status=PurchaseStatus.objects.get(code='PAID'),
                                           purchased_at=started, created_at=started)
        service = ServiceRequest.objects.create(
            purchase=purchase, participant=participant, status=ServiceStatus.objects.get(code=state),
            created_at=started, started_at=started,
            completed_at=started + timedelta(days=len(steps)) if state == 'COMPLETED' else None,
        )
        for step, code in enumerate(steps):
            actor = self.staff['recepcion.dev' if step == 0 else 'analista.dev']
            ServiceStatusLog.objects.create(request=service, status=ServiceStatus.objects.get(code=code),
                                            actor=actor, changed_at=started + timedelta(days=step))
        sample = None
        if state != 'WAITING_SAMPLE':
            sample = Sample.objects.create(
                service_request=service, participant=participant, sample_code=f'SEED-{index:04d}',
                sample_type='saliva', material='genomic DNA', collection_method='saliva kit',
                collected_at=started + timedelta(days=1), storage_location='Freezer A-1', status='received',
                metadata={'seed': True},
            )
        for label, code, value, unit in (('Altura', '8302-2', '172.0', 'cm'), ('Peso', '29463-7', '70.5', 'kg')):
            Observation.objects.create(
                participant=participant, sample=None, observation_type='clinical_measurement',
                code_system='LOINC', code=code, label=label, value_numeric=Decimal(value), unit=unit,
                source_name='GenomIA-seed', observed_at=started,
            )
        if sample:
            Observation.objects.create(
                participant=participant, sample=sample, observation_type='laboratory_result', code_system='LOINC',
                code='48767-8', label='Calidad del ADN (A260/280)', value_numeric=Decimal('1.85'),
                reference_low=Decimal('1.8'), reference_high=Decimal('2.0'), source_name='GenomIA-seed',
                observed_at=started + timedelta(days=1),
            )
        if state in ('PROCESSING', 'COMPLETED'):
            self.seed_analyses(participant, sample, service, started, completed=state == 'COMPLETED')

    def seed_analyses(self, participant, sample, service, started, *, completed):
        def analysis(module, done):
            return Analysis.objects.create(
                participant=participant, sample=sample, service_request=service, release=self.release,
                module=module, pipeline_name=f'genomia-seed-{module}', pipeline_version='1.0.0',
                reference_assembly='GRCh38', parameters={'seed': True}, status='completed' if done else 'running',
                started_at=started + timedelta(days=2), finished_at=started + timedelta(days=3) if done else None,
            )

        calling = analysis('variant_calling', True)
        genotyped = self.variants[:40]
        for variant in genotyped:
            alt = self.rng.randint(5, 30)
            Genotype.objects.create(
                release=self.release, variant=variant, participant=participant, sample=sample, analysis=calling,
                genotype=self.rng.choice(('0/1', '0/1', '1/1')), read_depth=alt + self.rng.randint(5, 30),
                genotype_quality=Decimal(self.rng.randint(20, 99)), allele_depths=[self.rng.randint(0, 30), alt],
                filters=['PASS'],
            )
        for variant in genotyped[:5]:
            VariantAnnotation.objects.create(variant=variant, analysis=calling, source_name='GenomIA-seed',
                                             source_version='1', annotation_type='functional_consequence',
                                             consequence='missense_variant', payload={'seed': True})
        AnalysisResult.objects.create(analysis=calling, participant=participant, sample=sample, release=self.release,
                                      module='variant_calling', result_type='variant_count',
                                      value_numeric=Decimal(len(genotyped)), unit='variants')
        for uri, kind, fmt, role in ((f'file:///seed/{sample.sample_code}.cram', 'CRAM', 'cram', 'input'),
                                     (f'file:///seed/{sample.sample_code}.vcf.gz', 'VCF', 'vcf.gz', 'output')):
            Artifact.objects.create(analysis=calling, release=self.release, sample=sample, role=role,
                                    artifact_type=kind, format=fmt, uri=uri, checksum_sha256=_checksum(uri),
                                    size_bytes=self.rng.randint(10**6, 10**9), reference_assembly='GRCh38')

        ancestry = analysis('ancestry', completed)
        pgx = analysis('pgx', completed)
        methylation = analysis('methylation', completed)
        if not completed:
            return
        shares = [self.rng.random() for _ in FREQUENCY_POPULATIONS]
        for code, share in zip(FREQUENCY_POPULATIONS, shares):
            AnalysisResult.objects.create(
                analysis=ancestry, participant=participant, sample=sample, release=self.release,
                population=self.populations[code], module='ancestry', result_type='global_ancestry',
                value_numeric=Decimal(share / sum(shares)).quantize(Decimal('1e-6')), unit='proportion',
                confidence=Decimal('0.95'),
            )
        for gene, diplotype, phenotype in PGX:
            AnalysisResult.objects.create(
                analysis=pgx, participant=participant, sample=sample, release=self.release, module='pgx',
                result_type='diplotype', value_code=f'{gene}{diplotype}', value_text=phenotype,
                payload={'gene': gene, 'diplotype': diplotype, 'phenotype': phenotype},
            )
        for feature in self.features[:10]:
            AnalysisResult.objects.create(
                analysis=methylation, participant=participant, sample=sample, release=self.release,
                epigenetic_feature=feature, module='methylation', result_type='beta_value',
                reference_assembly='GRCh38', contig=feature.contig, start_pos=feature.start_pos,
                end_pos=feature.end_pos, value_numeric=Decimal(self.rng.random()).quantize(Decimal('1e-4')),
                unit='beta',
            )
        report_uri = f'file:///seed/{sample.sample_code}-report.pdf'
        Artifact.objects.create(analysis=pgx, release=self.release, sample=sample, role='report',
                                artifact_type='report', format='pdf', uri=report_uri,
                                checksum_sha256=_checksum(report_uri), size_bytes=250_000)

    def seed_account_tokens(self, user):
        EmailVerification.objects.create(user=user, email=user.email, is_verified=True, verified_at=self.now,
                                         expires_at=self.now + timedelta(days=1))
        PasswordResetToken.objects.create(user=user, expires_at=self.now - timedelta(hours=1), used=True)
        RevokedToken.objects.create(jti='seed-dev-revoked-token', user=user, expires_at=self.now - timedelta(hours=1))
        RegistrationEmailChallenge.objects.create(email='nuevo.registro@genomia.dev',
                                                  code_hash=_checksum('seed-not-a-real-code'),
                                                  expires_at=self.now + timedelta(minutes=10))

    def report(self):
        empty = []
        for label in ('accounts', 'profiles', 'participants', 'services', 'genoma'):
            for model in apps.get_app_config(label).get_models():
                count = model.objects.count()
                self.stdout.write(f'{model._meta.label:38} {count}')
                if not count:
                    empty.append(model._meta.label)
        self.stdout.write(self.style.WARNING(f'Empty tables: {empty}') if empty
                          else self.style.SUCCESS(f'All tables populated. Accounts password: {PASSWORD}'))
