"""Per-client genomic results: a dev generator and the client's own read endpoint.

Only monogenic risk comes from real catalog data (ClinVar significance of the
assigned variants). Ancestry, polygenic risk, pharmacogenetics and traits are
SIMULATED but internally consistent: global ancestry is computed from the local
ancestry segments, and polygenic scores from the assigned genotypes.
"""
import bisect
import hashlib
import math
import random
from datetime import timedelta
from decimal import Decimal
from statistics import NormalDist

from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.authentication import JWTAuthentication
from accounts.models import AppUser, Role
from genoma.models import Analysis, AnalysisResult, DataRelease, Genotype, Population, VariantAnnotation, VariantPlacement
from participants.codes import ensure_client_code
from participants.models import Observation, Participant
from profiles.models import Profile, normalize_rut
from services.models import Purchase, PurchaseStatus, Sample, ServiceRequest, ServiceStatus, ServiceStatusLog
from services.status import get_service_projection
from services.views import STATUS_SEQUENCE, _sample_code_for

CHR1_LENGTH = 248_956_422  # GRCh38; the loaded ClinVar catalog only covers chromosome 1.
MEAN_SEGMENT_BP = 15_000_000  # Typical admixture tract length for ~10 generations of mixing.
ANCESTRIES = {  # code: (label, typical Chilean proportion)
    'NAT': ('Amerindio', 0.45), 'EUR': ('Europeo', 0.50), 'AFR': ('Africano', 0.03), 'EAS': ('Asiático', 0.02),
}
# Country-level reference panels (1000 Genomes style); each splits its continental group's share.
REFERENCE_POPULATIONS = {  # code: (label, group, ISO 3166-1 alpha-2, country, typical weight in group)
    'MAP': ('Mapuche', 'NAT', 'CL', 'Chile', .65), 'AYM': ('Aymara', 'NAT', 'BO', 'Bolivia', .2),
    'QUE': ('Quechua', 'NAT', 'PE', 'Perú', .15),
    'IBS': ('Ibérico', 'EUR', 'ES', 'España', .6), 'TSI': ('Toscano', 'EUR', 'IT', 'Italia', .25),
    'GBR': ('Británico', 'EUR', 'GB', 'Reino Unido', .15),
    'YRI': ('Yoruba', 'AFR', 'NG', 'Nigeria', .6), 'LWK': ('Luhya', 'AFR', 'KE', 'Kenia', .4),
    'CHB': ('Han', 'EAS', 'CN', 'China', .6), 'JPT': ('Japonés', 'EAS', 'JP', 'Japón', .4),
}
PATHOGENIC = {'Pathogenic', 'Likely_pathogenic', 'Pathogenic/Likely_pathogenic'}
GENOTYPES = (('0|1', 0.4), ('1|0', 0.4), ('1|1', 0.2))  # Only carried variants are assigned.
DOSAGE_MEAN, DOSAGE_VAR = 1.2, 0.16  # Mean/variance of alt dosage under GENOTYPES.
POLYGENIC = (('diabetes_tipo_2', 'Diabetes tipo 2'), ('enfermedad_coronaria', 'Enfermedad coronaria'),
             ('hipertension', 'Hipertensión arterial'), ('cancer_mama', 'Cáncer de mama'),
             ('alzheimer', 'Enfermedad de Alzheimer'))
PGX = (
    ('CYP2C19', (('*1/*1', 'Metabolizador normal', .6), ('*1/*2', 'Metabolizador intermedio', .25),
                 ('*2/*2', 'Metabolizador lento', .05), ('*1/*17', 'Metabolizador rápido', .1)),
     ('Clopidogrel', 'Omeprazol', 'Sertralina')),
    ('CYP2D6', (('*1/*1', 'Metabolizador normal', .7), ('*1/*4', 'Metabolizador intermedio', .2),
                ('*4/*4', 'Metabolizador lento', .05), ('*1/*1xN', 'Metabolizador ultrarrápido', .05)),
     ('Codeína', 'Tramadol', 'Tamoxifeno')),
    ('CYP2C9', (('*1/*1', 'Metabolizador normal', .75), ('*1/*2', 'Metabolizador intermedio', .15),
                ('*1/*3', 'Metabolizador intermedio', .1)), ('Warfarina', 'Ibuprofeno')),
    ('SLCO1B1', (('*1/*1', 'Función normal', .75), ('*1/*5', 'Función disminuida', .2),
                 ('*5/*5', 'Función baja', .05)), ('Simvastatina', 'Atorvastatina')),
    ('VKORC1', (('G/G', 'Sensibilidad normal', .4), ('G/A', 'Sensibilidad intermedia', .4),
                ('A/A', 'Sensibilidad alta', .2)), ('Warfarina',)),
)
TRAITS = (  # code, label, category, gene, rsid, description, ((result, explanation, weight), ...)
    ('color_ojos', 'Color de ojos', 'Apariencia Física', 'HERC2', 'rs12913832',
     'Variantes cerca de HERC2/OCA2 regulan cuánta melanina se produce en el iris.',
     (('Café', 'Tu variante favorece más melanina en el iris, lo que da ojos oscuros.', .8),
      ('Verde', 'Nivel intermedio de melanina en el iris; suele combinarse con otras variantes.', .12),
      ('Azul', 'Tu variante reduce la melanina del iris, lo que da ojos claros.', .08))),
    ('cabello', 'Tipo de cabello', 'Apariencia Física', 'TCHH', 'rs11803731',
     'La tricohialina (TCHH) influye en la forma del folículo y en la textura del cabello.',
     (('Liso', 'Tu combinación se asocia a cabello liso.', .6),
      ('Ondulado', 'Tu combinación se asocia a cabello ondulado.', .3),
      ('Rizado', 'Tu combinación se asocia a cabello rizado.', .1))),
    ('lactosa', 'Tolerancia a la lactosa', 'Metabolismo', 'MCM6', 'rs4988235',
     'Esta variante regula si el gen de la lactasa (LCT) sigue activo en la adultez.',
     (('Tolerante', 'Mantienes la producción de lactasa en la adultez y digieres bien la lactosa.', .45),
      ('Intolerante', 'La producción de lactasa baja con la edad; podrías tener molestias con lácteos.', .55))),
    ('cafeina', 'Metabolismo de la cafeína', 'Metabolismo', 'CYP1A2', 'rs762551',
     'CYP1A2 es la enzima del hígado que elimina la mayor parte de la cafeína.',
     (('Rápido', 'Eliminas la cafeína rápido; su efecto te dura menos.', .5),
      ('Lento', 'Eliminas la cafeína lento; su efecto te dura más y puede afectar tu sueño.', .5))),
    ('sabor_amargo', 'Percepción del sabor amargo', 'Rendimiento Físico y Sensorial', 'TAS2R38', 'rs713598',
     'TAS2R38 codifica un receptor del sabor amargo, presente en vegetales como el brócoli.',
     (('Alta', 'Percibes con intensidad los sabores amargos.', .3),
      ('Media', 'Tu percepción del amargor es intermedia.', .45),
      ('Baja', 'Percibes poco el amargor; los vegetales amargos te resultan suaves.', .25))),
    ('actn3', 'Tipo de fibra muscular', 'Rendimiento Físico y Sensorial', 'ACTN3', 'rs1815739',
     'ACTN3 produce alfa-actinina-3, una proteína de las fibras musculares rápidas.',
     (('Potencia', 'Produces alfa-actinina-3: perfil favorable para esfuerzos cortos e intensos.', .3),
      ('Mixta', 'Tienes un perfil intermedio entre potencia y resistencia.', .5),
      ('Resistencia', 'No produces alfa-actinina-3: perfil asociado a esfuerzos prolongados.', .2))),
    ('comt', 'Respuesta al estrés', 'Cognición', 'COMT', 'rs4680',
     'COMT degrada la dopamina en la corteza prefrontal, vinculada a la atención y al manejo del estrés.',
     (('Guerrero', 'Degradas la dopamina rápido: tiendes a rendir mejor bajo presión.', .25),
      ('Intermedio', 'Equilibrio entre rendimiento bajo presión y memoria de trabajo.', .5),
      ('Preocupado', 'Degradas la dopamina lento: mejor memoria de trabajo y más sensibilidad al estrés.', .25))),
    ('cronotipo', 'Cronotipo', 'Bienestar y Salud', 'CLOCK', 'rs1801260',
     'El gen CLOCK participa en el reloj circadiano que regula el sueño y la vigilia.',
     (('Matutino', 'Tiendes a despertar temprano y a rendir mejor en la mañana.', .4),
      ('Intermedio', 'Tu horario de sueño es flexible, sin una preferencia marcada.', .35),
      ('Vespertino', 'Tiendes a dormir tarde y a rendir mejor en la tarde y la noche.', .25))),
)
# Every possible result with its (simulated) population frequency, so the UI can show where the client falls.
TRAIT_OPTIONS = {code: [{'result': value, 'frequency': weight} for value, _, weight in options]
                 for code, _, _, _, _, _, options in TRAITS}
MODULES = ('variant_calling', 'local_ancestry', 'global_ancestry', 'monogenic_risk', 'polygenic_risk',
           'pharmacogenetics', 'traits')
RELEASE = {'name': 'GenomIA resultados dev', 'version': '1'}
CLIENT_STATES = ('registrado', 'datos_compra', *STATUS_SEQUENCE)  # STATUS_SEQUENCE ends in COMPLETED.
PIPELINE = 'genomia-dev-poblar_usuario'


def _pick(rng, options):
    return rng.choices([option[:-1] if len(option) > 2 else option[0] for option in options],
                       weights=[option[-1] for option in options])[0]


def _polygenic_weight(condition, variant_id):
    """Deterministic per (condition, variant): ~20% of variants are risk loci for each condition."""
    digest = hashlib.sha256(f'{condition}:{variant_id}'.encode()).digest()
    if digest[0] >= 51:
        return 0.0
    return int.from_bytes(digest[1:5]) / 2**32 * 2 - 1


def _local_ancestry_segments(rng, proportions):
    segments = []
    codes, weights = list(proportions), list(proportions.values())
    for haplotype in (0, 1):
        start = 1
        while start <= CHR1_LENGTH:
            end = min(start + int(rng.expovariate(1 / MEAN_SEGMENT_BP)), CHR1_LENGTH)
            code = rng.choices(codes, weights=weights)[0]
            if segments and segments[-1]['haplotype'] == haplotype and segments[-1]['code'] == code:
                segments[-1]['end'] = end
            else:
                segments.append({'haplotype': haplotype, 'code': code, 'start': start, 'end': end,
                                 'confidence': round(rng.uniform(0.85, 0.99), 4)})
            start = end + 1
    return segments


def _lock_service(owner, participant, actor, now):
    """Reuse the client's active service (completing it) or open a new completed one."""
    active = (ServiceRequest.objects.select_for_update(of=('self',)).select_related('status')
              .filter(purchase__owner=owner, purchase__status__code='PAID')
              .exclude(status__code='COMPLETED').order_by('-created_at').first())
    if active is None:
        purchase = Purchase.objects.create(owner=owner, status=PurchaseStatus.objects.get(code='PAID'),
                                           purchased_at=now)
        active = ServiceRequest.objects.create(purchase=purchase, participant=participant, started_at=now,
                                               status=ServiceStatus.objects.get(code=STATUS_SEQUENCE[0]))
        remaining = STATUS_SEQUENCE
    else:
        if active.participant_id is None:
            active.participant = participant
        remaining = STATUS_SEQUENCE[STATUS_SEQUENCE.index(active.status.code) + 1:]
    # Strictly increasing timestamps keep COMPLETED as the latest log the client projection reads.
    for step, code in enumerate(remaining):
        ServiceStatusLog.objects.create(request=active, status=ServiceStatus.objects.get(code=code), actor=actor,
                                        changed_at=now + timedelta(milliseconds=step), comment='poblar_usuario')
    active.status = ServiceStatus.objects.get(code='COMPLETED')
    active.completed_at = now + timedelta(milliseconds=len(remaining))
    active.save()
    sample = Sample.objects.filter(service_request=active).order_by('created_at').first()
    if sample is None:
        sample = Sample.objects.create(service_request=active, participant=participant, sample_type='saliva',
                                       sample_code=_sample_code_for(participant))
    sample.status, sample.collected_at = 'received', sample.collected_at or now
    sample.save()
    return active, sample


def _clear_previous_runs(owner):
    """Keep one generated state per client: drop earlier generated results and the services they created."""
    analyses = Analysis.objects.filter(participant__user_id=owner.django_user_id, pipeline_name=PIPELINE)
    AnalysisResult.objects.filter(analysis__in=analyses).delete()
    Genotype.objects.filter(analysis__in=analyses).delete()
    analyses.delete()
    # A service from the real flow (any log not written by this tool) keeps its history; only generated ones go.
    service_ids = ServiceRequest.objects.filter(purchase__owner=owner).values_list('pk', flat=True)
    created = [pk for pk in service_ids
               if not ServiceStatusLog.objects.filter(request_id=pk).exclude(comment='poblar_usuario').exists()
               and not Analysis.objects.filter(service_request_id=pk).exists()
               and not Observation.objects.filter(sample__service_request_id=pk).exists()]
    purchases = set(ServiceRequest.objects.filter(pk__in=created).values_list('purchase_id', flat=True))
    ServiceStatusLog.objects.filter(request_id__in=created).delete()
    Sample.objects.filter(service_request_id__in=created).delete()
    ServiceRequest.objects.filter(pk__in=created).delete()
    Purchase.objects.filter(pk__in=purchases, service_request__isnull=True).delete()


def _lock_client(user):
    owner = AppUser.objects.select_for_update(of=('self',)).filter(
        django_user=user, django_user__is_active=True, role__code=Role.Code.CLIENTE,
    ).first()
    if owner is None:
        raise ValueError('El usuario debe ser un cliente activo.')
    return owner


def _status_actor():
    actor = AppUser.objects.filter(role__code__in=[Role.Code.ANALISTA, Role.Code.ADMIN]).order_by(
        'role__code').first()
    if actor is None:
        raise ValueError('Se necesita al menos un analista o admin para registrar los cambios de estado.')
    return actor


def _ensure_purchase_profile(user, rng):
    """Synthetic purchase data (the form a real client fills before buying), kept if already present."""
    if not Profile.objects.filter(user=user, rut__isnull=False).exists():
        while True:
            body = rng.randint(10_000_000, 25_999_999)
            rut = next(f'{body}-{dv}' for dv in '0123456789K' if normalize_rut(f'{body}-{dv}'))
            if not Profile.objects.filter(rut=rut).exists():
                break
        Profile.objects.update_or_create(user=user, defaults={
            'rut': rut, 'phone': f'+569{rng.randrange(10**8):08d}',
        })
    ensure_client_code(user)
    participant = Participant.objects.get(user=user)
    if participant.sex_at_birth is None:
        participant.sex_at_birth = rng.choice(Participant.SexAtBirth.values)
        participant.birth_year = rng.randint(1950, 2005)
        participant.save(update_fields=['sex_at_birth', 'birth_year'])
    return participant


def set_client_state(user, state, *, seed=None):
    """Put a client at a non-COMPLETED point of the flow (COMPLETED goes through populate_client_results).

    'registrado': account only (no purchase data, no service); 'datos_compra': purchase form filled,
    nothing bought; WAITING_SAMPLE/SAMPLE_RECEIVED/PROCESSING: paid service at that step, no results.
    Earlier generated services/results are replaced; a real (reception-confirmed) active service is never touched.
    """
    if state not in CLIENT_STATES or state == 'COMPLETED':
        raise ValueError(f'Estado no válido: {state}')
    rng = random.Random(seed)
    now = timezone.now()
    with transaction.atomic():
        owner = _lock_client(user)
        _clear_previous_runs(owner)
        if ServiceRequest.objects.filter(purchase__owner=owner, purchase__status__code='PAID').exclude(
                status__code='COMPLETED').exists():
            raise ValueError('El cliente tiene un servicio real en curso; avánzalo desde la vista del analista.')
        if state == 'registrado':
            Profile.objects.filter(user=user).delete()
            return {'state': state}
        participant = _ensure_purchase_profile(user, rng)
        if state == 'datos_compra':
            return {'state': state, 'client_code': participant.participant_code}
        actor = _status_actor()
        steps = STATUS_SEQUENCE[:STATUS_SEQUENCE.index(state) + 1]
        purchase = Purchase.objects.create(owner=owner, status=PurchaseStatus.objects.get(code='PAID'),
                                           purchased_at=now)
        service = ServiceRequest.objects.create(purchase=purchase, participant=participant, started_at=now,
                                                status=ServiceStatus.objects.get(code=state))
        for step, code in enumerate(steps):
            ServiceStatusLog.objects.create(request=service, status=ServiceStatus.objects.get(code=code),
                                            actor=actor, changed_at=now + timedelta(milliseconds=step),
                                            comment='poblar_usuario')
        waiting = state == 'WAITING_SAMPLE'
        sample = Sample.objects.create(
            service_request=service, participant=participant, sample_code=_sample_code_for(participant),
            sample_type='saliva', status='pending_collection' if waiting else 'received',
            collected_at=None if waiting else now,
        )
        return {'state': state, 'client_code': participant.participant_code, 'sample_code': sample.sample_code}


def populate_client_results(user, variant_count, *, seed=None):
    """Assign `variant_count` ClinVar variants to a client and generate all module results."""
    rng = random.Random(seed)
    now = timezone.now()
    with transaction.atomic():
        owner = _lock_client(user)
        actor = _status_actor()
        pool = list(VariantPlacement.objects.filter(
            reference_assembly='GRCh38', variant__annotations__source_name='ClinVar',
        ).order_by('variant_id', 'pk').distinct('variant_id').values_list('variant_id', flat=True))
        if not 1 <= variant_count <= len(pool):
            raise ValueError(f'Puedes asignar entre 1 y {len(pool)} variantes.')
        _clear_previous_runs(owner)
        participant = _ensure_purchase_profile(user, rng)
        service, sample = _lock_service(owner, participant, actor, now)
        release, _ = DataRelease.objects.get_or_create(**RELEASE, defaults={
            'status': 'synthetic', 'reference_assembly': 'GRCh38',
            'description': 'Resultados de desarrollo generados por poblar_usuario. No clínicos.',
        })
        analyses = {module: Analysis.objects.create(
            participant=participant, sample=sample, service_request=service, release=release, module=module,
            pipeline_name=PIPELINE, pipeline_version='1', reference_assembly='GRCh38',
            parameters={'variants': variant_count, 'seed': seed}, status='completed',
            started_at=now, finished_at=now,
        ) for module in MODULES}

        def result(module, result_type, **values):
            return AnalysisResult(analysis=analyses[module], participant=participant, sample=sample,
                                  release=release, module=module, result_type=result_type, **values)

        chosen = rng.sample(pool, variant_count)
        annotations = {a.variant_id: a for a in VariantAnnotation.objects.filter(
            variant_id__in=chosen, source_name='ClinVar').order_by('variant_id', 'pk').distinct('variant_id')}
        # Pathogenic variants are rare; homozygous ones would mean a rare disease, so keep them as carriers.
        calls = {variant_id: _pick(rng, GENOTYPES[:2] if annotations[variant_id].clinical_significance in PATHOGENIC
                                   else GENOTYPES) for variant_id in chosen}
        Genotype.objects.bulk_create([Genotype(
            release=release, variant_id=variant_id, participant=participant, sample=sample,
            analysis=analyses['variant_calling'], genotype=call, phased=True, phase_set='chr1',
            read_depth=rng.randint(20, 60), genotype_quality=Decimal(rng.randint(30, 99)), filters=['PASS'],
        ) for variant_id, call in calls.items()])

        gammas = {code: rng.gammavariate(100 * share, 1) for code, (_, share) in ANCESTRIES.items()}
        segments = _local_ancestry_segments(rng, {code: g / sum(gammas.values()) for code, g in gammas.items()})
        populations = {code: Population.objects.get_or_create(code=code, defaults={'name': label})[0]
                       for code, (label, _) in ANCESTRIES.items()}
        rows = [result('local_ancestry', 'ancestry_segment', population=populations[s['code']],
                       reference_assembly='GRCh38', contig='1', start_pos=s['start'], end_pos=s['end'],
                       haplotype=s['haplotype'], confidence=Decimal(str(s['confidence'])),
                       value_code=s['code']) for s in segments]
        lengths = {code: 0 for code in ANCESTRIES}
        for s in segments:
            lengths[s['code']] += s['end'] - s['start'] + 1
        reference = {code: Population.objects.get_or_create(code=code, defaults={
            'name': label, 'geographic_region': country, 'parent_population': populations[group]})[0]
            for code, (label, group, _iso, country, _weight) in REFERENCE_POPULATIONS.items()}
        for group, length in lengths.items():
            members = [code for code, ref in REFERENCE_POPULATIONS.items() if ref[1] == group and length]
            draws = {code: rng.gammavariate(20 * REFERENCE_POPULATIONS[code][4], 1) for code in members}
            for code in members:
                _label, _group, iso, country, _weight = REFERENCE_POPULATIONS[code]
                share = length / (2 * CHR1_LENGTH) * draws[code] / sum(draws.values())
                rows.append(result('global_ancestry', 'ancestry_proportion', population=reference[code],
                                   value_code=code, value_numeric=Decimal(share).quantize(Decimal('1e-6')),
                                   unit='proportion', payload={'group': group, 'group_label': ANCESTRIES[group][0],
                                                               'country_code': iso, 'country': country}))

        placements = {p.variant_id: p for p in VariantPlacement.objects.filter(
            variant_id__in=chosen, reference_assembly='GRCh38').order_by('variant_id', 'pk').distinct('variant_id')}
        for variant_id, call in calls.items():
            annotation = annotations[variant_id]
            if annotation.clinical_significance not in PATHOGENIC:
                continue
            info = (annotation.payload or {}).get('info', {})
            conditions = [name.replace('_', ' ') for name in str(info.get('CLNDN', '')).split('|')
                          if name and name != 'not_provided']
            place = placements[variant_id]
            rows.append(result(
                'monogenic_risk', 'pathogenic_variant', variant_id=variant_id, reference_assembly='GRCh38',
                contig=place.contig, start_pos=place.start_pos, end_pos=place.end_pos,
                value_code=annotation.clinical_significance, value_text='; '.join(conditions) or None,
                payload={'gene': _gene(annotation), 'conditions': conditions,
                         'zygosity': 'homocigoto' if call == '1|1' else 'heterocigoto',
                         'review_status': annotation.evidence_level, 'source': 'ClinVar'},
            ))

        for condition, label in POLYGENIC:
            weights = {v: _polygenic_weight(condition, v) for v in chosen}
            loci = [v for v, w in weights.items() if w]
            score = sum(weights[v] * calls[v].count('1') for v in loci)
            spread = math.sqrt(sum(weights[v] ** 2 for v in loci) * DOSAGE_VAR)
            z = (score - DOSAGE_MEAN * sum(weights[v] for v in loci)) / spread if spread else 0.0
            percentile = round(NormalDist().cdf(z) * 100, 2)
            category = 'Elevado' if percentile >= 80 else 'Bajo' if percentile <= 20 else 'Promedio'
            rows.append(result('polygenic_risk', 'polygenic_score', value_code=condition, value_text=category,
                               value_numeric=Decimal(str(round(score, 6))), percentile=Decimal(str(percentile)),
                               payload={'condition': condition, 'label': label, 'category': category,
                                        'risk_loci': len(loci), 'simulated': True}))
        for gene, options, drugs in PGX:
            diplotype, phenotype = _pick(rng, options)
            rows.append(result('pharmacogenetics', 'diplotype', value_code=f'{gene} {diplotype}',
                               value_text=phenotype, payload={'gene': gene, 'diplotype': diplotype,
                                                              'phenotype': phenotype, 'drugs': list(drugs),
                                                              'simulated': True}))
        for code, label, category, gene, rsid, description, options in TRAITS:
            value, explanation = _pick(rng, options)
            rows.append(result('traits', 'trait', value_code=code, value_text=value, payload={
                'trait': code, 'label': label, 'category': category, 'gene': gene, 'rsid': rsid,
                'description': description, 'result': value, 'explanation': explanation, 'simulated': True}))
        AnalysisResult.objects.bulk_create(rows)
    return {'service_request_id': service.pk, 'sample_code': sample.sample_code, 'variants': variant_count,
            'pathogenic': sum(row.module == 'monogenic_risk' for row in rows),
            'segments': len(segments)}


def _gene(annotation):
    if annotation is None:
        return None
    info = (annotation.payload or {}).get('info') or {}
    return annotation.gene_symbol or (str(info['GENEINFO']).split(':')[0] if info.get('GENEINFO') else None)


def _variant_label(annotation):
    info = ((annotation.payload or {}).get('info') or {}) if annotation else {}
    return f"rs{info['RS']}" if info.get('RS') else None


def read_client_results(user):
    """The client's own newest COMPLETED service results; None when there are none to show."""
    projection = get_service_projection(user)
    if not projection.can_view_results:
        return None
    service_id = projection.service_request_id
    # A service can hold earlier runs of a module; only the newest analysis per module counts.
    latest = list(Analysis.objects.filter(service_request_id=service_id, participant__user=user, module__in=MODULES)
                  .order_by('module', '-created_at', '-pk').distinct('module').values_list('pk', flat=True))
    results = list(AnalysisResult.objects.filter(
        analysis_id__in=latest, participant__user=user,
    ).select_related('population').order_by('module', 'haplotype', 'start_pos', 'pk'))
    by_module = {module: [r for r in results if r.module == module] for module in MODULES[1:]}
    segments = {0: [], 1: []}
    for row in by_module['local_ancestry']:
        segments[row.haplotype].append(row)
    starts = {h: [row.start_pos for row in rows] for h, rows in segments.items()}

    def ancestry_at(haplotype, position):
        index = bisect.bisect_right(starts[haplotype], position) - 1
        row = segments[haplotype][index] if index >= 0 else None
        if row is None or row.end_pos < position:
            return None
        return {'population': row.value_code, 'label': ANCESTRIES[row.value_code][0],
                'confidence': float(row.confidence)}

    genotypes = list(Genotype.objects.filter(
        analysis_id__in=latest, participant__user=user,
    ).select_related('variant'))
    ids = [g.variant_id for g in genotypes]
    annotations = {a.variant_id: a for a in VariantAnnotation.objects.filter(
        variant_id__in=ids, source_name='ClinVar').order_by('variant_id', 'pk').distinct('variant_id')}
    placements = {p.variant_id: p for p in VariantPlacement.objects.filter(
        variant_id__in=ids, reference_assembly='GRCh38').order_by('variant_id', 'pk').distinct('variant_id')}
    variants, by_type = [], {}
    for g in sorted(genotypes, key=lambda g: placements[g.variant_id].start_pos):
        place, annotation = placements[g.variant_id], annotations.get(g.variant_id)
        by_type[g.variant.variant_type] = by_type.get(g.variant.variant_type, 0) + 1
        haplotypes = {h: ancestry_at(h, place.start_pos) for h in (0, 1)}
        variants.append({
            'variant_id': str(g.variant_id), 'rsid': _variant_label(annotation), 'type': g.variant.variant_type,
            'contig': place.contig, 'position': place.start_pos, 'ref': place.reference_allele,
            'alt': place.alternate_allele, 'genotype': g.genotype,
            'zygosity': 'homocigoto' if g.genotype in ('1|1', '1/1') else 'heterocigoto',
            'gene': _gene(annotation),
            'clinical_significance': annotation.clinical_significance if annotation else None,
            'local_ancestry': {'haplotype_0': haplotypes[0], 'haplotype_1': haplotypes[1]},
            # Phased call: the alt allele sits on the haplotype(s) marked "1"; unphased calls can't tell.
            'alt_allele_ancestry': [haplotypes[h]['population'] for h in (0, 1)
                                    if g.genotype.split('|')[h] == '1' and haplotypes[h]]
            if g.phased and '|' in g.genotype else None,
        })
    return {
        'service_request_id': str(service_id),
        'sample_code': Sample.objects.filter(service_request_id=service_id).order_by('created_at', 'pk')
        .values_list('sample_code', flat=True).first(),
        'disclaimer': 'Resultados de desarrollo. Solo el riesgo monogénico usa datos reales de ClinVar; '
                      'el resto es simulado y no tiene valor clínico.',
        'modules': {
            'global_ancestry': [{'population': r.value_code,
                                 'label': r.population.name if r.population else r.value_code,
                                 **(r.payload or {}), 'proportion': float(r.value_numeric)}
                                for r in sorted(by_module['global_ancestry'], key=lambda r: -r.value_numeric)],
            'local_ancestry': [{'haplotype': r.haplotype, 'contig': r.contig, 'start': r.start_pos,
                                'end': r.end_pos, 'population': r.value_code,
                                'label': ANCESTRIES[r.value_code][0], 'confidence': float(r.confidence)}
                               for r in by_module['local_ancestry']],
            'monogenic_risk': [{'variant_id': str(r.variant_id), 'position': r.start_pos,
                                'clinical_significance': r.value_code, **r.payload}
                               for r in by_module['monogenic_risk']],
            'polygenic_risk': [{'percentile': float(r.percentile), 'score': float(r.value_numeric), **r.payload}
                               for r in by_module['polygenic_risk']],
            'pharmacogenetics': [r.payload for r in by_module['pharmacogenetics']],
            'traits': [r.payload | {'options': TRAIT_OPTIONS.get(r.payload.get('trait'), [])}
                       for r in by_module['traits']],
        },
        'variant_summary': {'total': len(variants), 'by_type': by_type},
        'variants': variants,
    }


MIN_COHORT = 10  # Ley 21.719: below this, aggregates could single out a person, so nothing is returned.


def read_ancestry_cohort(user):
    """Where the client's global ancestry falls among other sequenced clients; aggregates only."""
    own = read_client_results(user)
    if own is None:
        return None
    mine = {row['population']: row['proportion'] for row in own['modules']['global_ancestry']}
    latest = (Analysis.objects.filter(module='global_ancestry', status='completed')
              .exclude(participant__user=user)
              .order_by('participant_id', '-created_at', '-pk').distinct('participant_id').values_list('pk', flat=True))
    others = {}
    for analysis_id, code, value in AnalysisResult.objects.filter(
            analysis_id__in=list(latest), module='global_ancestry').values_list('analysis_id', 'value_code', 'value_numeric'):
        others.setdefault(analysis_id, {})[code] = float(value)
    size = len(others)
    if size < MIN_COHORT:
        return {'cohort_size': size, 'min_cohort': MIN_COHORT, 'populations': {}}
    populations = {}
    for code in REFERENCE_POPULATIONS:
        values = [shares.get(code, 0.0) for shares in others.values()]
        value = mine.get(code, 0.0)
        below = sum(v < value for v in values) + sum(v == value for v in values) / 2
        populations[code] = {'mean': round(sum(values) / size, 6),
                             'carriers': round(sum(v > 0 for v in values) / size, 4),
                             'percentile': round(below / size * 100, 1)}
    return {'cohort_size': size, 'min_cohort': MIN_COHORT, 'populations': populations}


class AncestryCohortAPIView(APIView):
    """GET /api/genoma/v1/results/ancestry-cohort/: aggregate comparison, never other clients' rows."""
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        data = read_ancestry_cohort(request.user)
        if data is None:
            return Response({'error': 'No hay resultados disponibles'}, status=status.HTTP_404_NOT_FOUND)
        return Response(data)


class ClientResultsAPIView(APIView):
    """GET /api/genoma/v1/results/: only the logged-in client's own results (Ley 21.719)."""
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        data = read_client_results(request.user)
        if data is None:
            return Response({'error': 'No hay resultados disponibles'}, status=status.HTTP_404_NOT_FOUND)
        return Response(data)
