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
from accounts.audit import record_genetic_access
from accounts.models import AppUser, GeneticDataAccessLog, Role
from genoma.gene_inheritance import inheritance, mondo_ids
from genoma.models import Analysis, AnalysisResult, DataRelease, Genotype, VariantAnnotation, VariantPlacement
from genoma.population_catalog import Catalog
from participants.codes import ensure_client_code
from participants.models import Observation, Participant
from profiles.models import Profile, normalize_rut
from services.models import Purchase, PurchaseStatus, Sample, ServiceRequest, ServiceStatus, ServiceStatusLog
from services.status import get_service_projection
from services.views import STATUS_SEQUENCE, _sample_code_for

CHR1_LENGTH = 248_956_422  # GRCh38; the loaded ClinVar catalog only covers chromosome 1.
MEAN_SEGMENT_BP = 15_000_000  # Typical admixture tract length for ~10 generations of mixing.
# Simulated typical Chilean mix per continental group; the groups and units come from the population catalog.
GROUP_SHARES = {'AMR': 0.45, 'EUR': 0.48, 'AFR': 0.03, 'MID': 0.02, 'EAS': 0.02}
# Typical weight of each reported unit inside its group; units not listed weigh 1 / units in the group.
UNIT_WEIGHTS = {'AMR_ANDES': .8, 'AMR_AMAZON': .15, 'AMR_MESO': .05, 'IBS': .7, 'TSI': .1, 'CEU': .08,
                'GBR': .07, 'FIN': .05, 'YRI': .35, 'ESN': .2, 'MID_LEVANT': .8, 'MID_MAGHREB': .2,
                'CHB': .6, 'JPT': .4}
PATHOGENIC = {'Pathogenic', 'Likely_pathogenic', 'Pathogenic/Likely_pathogenic'}
# ClinVar review status → stars (0–4), as the page shows them next to the classification.
REVIEW_STARS = {'practice_guideline': 4, 'reviewed_by_expert_panel': 3,
                'criteria_provided,_multiple_submitters,_no_conflicts': 2,
                'criteria_provided,_single_submitter': 1,
                'criteria_provided,_conflicting_classifications': 1}
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
    # The rest of the CPIC level A/B genes, with rough population weights.
    ('CYP2B6', (('*1/*1', 'Metabolizador normal', .45), ('*1/*6', 'Metabolizador intermedio', .4),
                ('*6/*6', 'Metabolizador lento', .15)), ('Efavirenz', 'Sertralina')),
    ('CYP3A5', (('*3/*3', 'Metabolizador lento', .75), ('*1/*3', 'Metabolizador intermedio', .2),
                ('*1/*1', 'Metabolizador normal', .05)), ('Tacrolimus',)),
    ('CYP4F2', (('*1/*1', 'Función normal', .55), ('*1/*3', 'Función disminuida', .38),
                ('*3/*3', 'Función baja', .07)), ('Warfarina',)),
    ('DPYD', (('Ref/Ref', 'Metabolizador normal', .95), ('c.1905+1G>A/Ref', 'Metabolizador intermedio', .04),
              ('c.1905+1G>A/c.1905+1G>A', 'Metabolizador lento', .01)), ('Fluorouracilo', 'Capecitabina')),
    ('TPMT', (('*1/*1', 'Metabolizador normal', .9), ('*1/*3A', 'Metabolizador intermedio', .09),
              ('*3A/*3A', 'Metabolizador lento', .01)), ('Azatioprina', 'Mercaptopurina', 'Tioguanina')),
    ('NUDT15', (('*1/*1', 'Metabolizador normal', .95), ('*1/*3', 'Metabolizador intermedio', .045),
                ('*3/*3', 'Metabolizador lento', .005)), ('Azatioprina', 'Mercaptopurina', 'Tioguanina')),
    ('UGT1A1', (('*1/*1', 'Metabolizador normal', .45), ('*1/*28', 'Metabolizador intermedio', .43),
                ('*28/*28', 'Metabolizador lento', .12)), ('Atazanavir',)),
    ('G6PD', (('B', 'Actividad normal', .97), ('A-', 'Deficiente', .03)),
     ('Primaquina', 'Nitrofurantoína', 'Dapsona', 'Rasburicasa')),
    ('HLA-B', (('*57:01, *58:01 y *15:02 negativos', 'No portador', .9), ('*58:01 positivo', 'Portador de HLA-B*58:01', .05),
               ('*57:01 positivo', 'Portador de HLA-B*57:01', .04), ('*15:02 positivo', 'Portador de HLA-B*15:02', .01)),
     ('Abacavir', 'Alopurinol', 'Carbamazepina', 'Oxcarbazepina', 'Fenitoína')),
    ('HLA-A', (('*31:01 negativo', 'No portador', .94), ('*31:01 positivo', 'Portador de HLA-A*31:01', .06)),
     ('Carbamazepina',)),
    ('RYR1', (('Ref/Ref', 'Sin variante asociada', .995), ('c.7300G>A/Ref', 'Susceptible a hipertermia maligna', .005)),
     ('Sevoflurano', 'Desflurano', 'Isoflurano', 'Succinilcolina')),
    ('CACNA1S', (('Ref/Ref', 'Sin variante asociada', .998), ('c.520C>T/Ref', 'Susceptible a hipertermia maligna', .002)),
     ('Sevoflurano', 'Desflurano', 'Isoflurano', 'Succinilcolina')),
    ('MT-RNR1', (('m.1555A', 'Riesgo habitual', .998), ('m.1555A>G', 'Riesgo aumentado de sordera', .002)),
     ('Gentamicina', 'Amikacina')),
    ('ABCG2', (('C/C', 'Función normal', .8), ('C/A', 'Función disminuida', .18), ('A/A', 'Función baja', .02)),
     ('Rosuvastatina',)),
)
TRAITS = (  # code, label, category, gene, rsid, description, ((result, explanation, weight), ...)
    ('color_ojos', 'Color de ojos', 'Apariencia Física', 'HERC2', 'rs12913832',
     'HERC2 contiene el interruptor de OCA2, el gen que decide cuánta melanina hay en tu iris.',
     (('Café', 'Tu variante favorece más melanina en el iris, lo que da ojos oscuros.', .8),
      ('Verde', 'Nivel intermedio de melanina en el iris; suele combinarse con otras variantes.', .12),
      ('Azul', 'Tu variante reduce la melanina del iris, lo que da ojos claros.', .08))),
    ('cabello', 'Tipo de cabello', 'Apariencia Física', 'TCHH', 'rs11803731',
     'La tricohialina (TCHH) influye en la forma del folículo y en la textura del cabello.',
     (('Liso', 'Tu combinación se asocia a cabello liso.', .6),
      ('Ondulado', 'Tu combinación se asocia a cabello ondulado.', .3),
      ('Rizado', 'Tu combinación se asocia a cabello rizado.', .1))),
    ('lactosa', 'Tolerancia a la lactosa', 'Metabolismo', 'MCM6', 'rs4988235',
     'MCM6 contiene el interruptor que mantiene encendido el gen de la lactasa (LCT) en la adultez.',
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
    # Single-gene traits with strong evidence (GWAS Catalog, MedlinePlus Genetics). Weights are rough estimates
    # for an admixed Chilean population.
    ('cerumen', 'Tipo de cerumen', 'Apariencia Física', 'ABCC11', 'rs17822931',
     'ABCC11 es una bomba que saca sustancias grasas en las glándulas del oído y de las axilas.',
     (('Húmedo', 'Tu cerumen tiende a ser húmedo y pegajoso, y el olor de axilas es el habitual.', .7),
      ('Seco', 'Tu cerumen tiende a ser seco y en escamas, y tus axilas producen poco olor.', .3))),
    ('pelo_rojo', 'Pelo rojizo', 'Apariencia Física', 'MC1R', 'rs1805007, rs1805008',
     'MC1R es el interruptor que decide si tus células del pelo y la piel producen pigmento oscuro o rojizo.',
     (('Sin variantes rojas', 'Produces sobre todo pigmento oscuro; el pelo rojo es poco probable.', .9),
      ('Una copia', 'Tienes una copia con variante roja: puedes tener reflejos o barba rojiza.', .09),
      ('Dos copias', 'Tus dos copias favorecen el pigmento rojizo: es probable el pelo rojo o cobrizo.', .01))),
    ('pecas', 'Tendencia a pecas', 'Apariencia Física', 'IRF4', 'rs12203592',
     'IRF4 regula cuánta melanina producen las células de la piel y del pelo.',
     (('Baja', 'Tu variante se asocia a pocas pecas.', .8),
      ('Media', 'Tienes una copia que favorece que te salgan pecas con el sol.', .17),
      ('Alta', 'Tus dos copias favorecen las pecas y una piel más sensible al sol.', .03))),
    ('grupo_sanguineo', 'Grupo sanguíneo', 'Bienestar y Salud', 'ABO', 'rs8176719, rs8176746',
     'ABO arma las marcas de azúcar que lleva cada glóbulo rojo; según cuáles tengas, tu sangre es A, B, AB u O.',
     (('O', 'Tus glóbulos rojos no llevan marcas A ni B. Es una estimación: antes de una transfusión siempre se confirma con un examen de sangre.', .6),
      ('A', 'Tus glóbulos rojos llevan la marca A. Es una estimación: antes de una transfusión siempre se confirma con un examen de sangre.', .28),
      ('B', 'Tus glóbulos rojos llevan la marca B. Es una estimación: antes de una transfusión siempre se confirma con un examen de sangre.', .09),
      ('AB', 'Tus glóbulos rojos llevan las marcas A y B. Es una estimación: antes de una transfusión siempre se confirma con un examen de sangre.', .03))),
    ('alcohol', 'Rubor con el alcohol', 'Metabolismo', 'ALDH2', 'rs671',
     'ALDH2 es la enzima que limpia el acetaldehído, la sustancia tóxica que deja el alcohol en el cuerpo.',
     (('Habitual', 'Limpias el acetaldehído como la mayoría; esta variante no hace que el alcohol te enrojezca.', .98),
      ('Rubor', 'Limpias el acetaldehído más lento: el alcohol puede enrojecerte la cara y acelerarte el pulso.', .02))),
    ('vitamina_b12', 'Niveles de vitamina B12', 'Metabolismo', 'FUT2', 'rs601338',
     'FUT2 decide si tus mucosas llevan ciertas marcas de azúcar, lo que cambia tu flora intestinal y cómo absorbes la vitamina B12.',
     (('Habituales', 'Tu variante se asocia a niveles habituales de vitamina B12.', .8),
      ('Algo más altos', 'Tu variante se asocia a niveles de vitamina B12 algo más altos en la sangre.', .2))),
    ('vitamina_d', 'Niveles de vitamina D', 'Metabolismo', 'GC', 'rs2282679',
     'GC produce la proteína que transporta la vitamina D por la sangre.',
     (('Habituales', 'Tu variante se asocia a niveles habituales de vitamina D.', .5),
      ('Algo más bajos', 'Tienes una copia que se asocia a niveles algo más bajos de vitamina D.', .4),
      ('Más bajos', 'Tus dos copias se asocian a niveles más bajos de vitamina D.', .1))),
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
    catalog = Catalog()
    units = [(unit, catalog.group_of(unit)) for unit in catalog.units()]
    populations = {group.code: group for _, group in units if group.code in GROUP_SHARES}
    if not populations:
        raise ValueError('No hay catálogo de poblaciones: corre manage.py load_populations.')
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

        gammas = {code: rng.gammavariate(100 * GROUP_SHARES[code], 1) for code in sorted(populations)}
        segments = _local_ancestry_segments(rng, {code: g / sum(gammas.values()) for code, g in gammas.items()})
        rows = [result('local_ancestry', 'ancestry_segment', population=populations[s['code']],
                       reference_assembly='GRCh38', contig='1', start_pos=s['start'], end_pos=s['end'],
                       haplotype=s['haplotype'], confidence=Decimal(str(s['confidence'])),
                       value_code=s['code']) for s in segments]
        lengths = {code: 0 for code in populations}
        for s in segments:
            lengths[s['code']] += s['end'] - s['start'] + 1
        for group, length in lengths.items():
            members = [unit for unit, unit_group in units if unit_group.code == group and length]
            draws = {unit.code: rng.gammavariate(20 * UNIT_WEIGHTS.get(unit.code, 1 / len(members)), 1)
                     for unit in members}
            for unit in members:
                # Results are per reference population, so they add up by unit (Andino) or by country (Perú).
                leaves = catalog.leaves(unit)
                splits = {leaf.code: rng.gammavariate(20 / len(leaves), 1) for leaf in leaves}
                for leaf in leaves:
                    share = (length / (2 * CHR1_LENGTH) * draws[unit.code] / sum(draws.values())
                             * splits[leaf.code] / sum(splits.values()))
                    rows.append(result('global_ancestry', 'ancestry_proportion', population=leaf,
                                       value_code=leaf.code, value_numeric=Decimal(share).quantize(Decimal('1e-6')),
                                       unit='proportion', payload={'group': group}))

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


def _monogenic(row, annotation):
    """One pathogenic variant read with what the page asks of it: mode, evidence, HGVS and ClinVar id."""
    payload = row.payload or {}
    info = ((annotation.payload or {}).get('info') or {}) if annotation else {}
    return {
        'variant_id': str(row.variant_id), 'position': row.start_pos, 'contig': row.contig,
        'clinical_significance': row.value_code, **payload,
        'inheritance': inheritance(payload.get('gene'), mondo_ids(info.get('CLNDISDB'))),
        'review_stars': REVIEW_STARS.get(payload.get('review_status'), 0),
        'hgvs': info.get('CLNHGVS'),
        'clinvar_id': (annotation.payload or {}).get('variation_id') if annotation else None,
    }


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
        return {'population': row.value_code, 'label': row.population.name if row.population else row.value_code,
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
    catalog = Catalog()
    by_unit, by_country = _ancestry_views(by_module['global_ancestry'], catalog)
    return {
        'service_request_id': str(service_id),
        'sample_code': Sample.objects.filter(service_request_id=service_id).order_by('created_at', 'pk')
        .values_list('sample_code', flat=True).first(),
        'disclaimer': 'Resultados de desarrollo. Solo el riesgo monogénico usa datos reales de ClinVar; '
                      'el resto es simulado y no tiene valor clínico.',
        'modules': {
            'global_ancestry': by_unit,
            'local_ancestry': [{'haplotype': r.haplotype, 'contig': r.contig, 'start': r.start_pos,
                                'end': r.end_pos, 'population': r.value_code,
                                'label': r.population.name if r.population else r.value_code,
                                'confidence': float(r.confidence)}
                               for r in by_module['local_ancestry']],
            'monogenic_risk': [_monogenic(r, annotations.get(r.variant_id))
                               for r in by_module['monogenic_risk']],
            'polygenic_risk': [{'percentile': float(r.percentile), 'score': float(r.value_numeric), **r.payload}
                               for r in by_module['polygenic_risk']],
            'pharmacogenetics': [r.payload for r in by_module['pharmacogenetics']],
            'traits': [r.payload | {'options': TRAIT_OPTIONS.get(r.payload.get('trait'), [])}
                       for r in by_module['traits']],
        },
        'variant_summary': {'total': len(variants), 'by_type': by_type},
        # 'country' only once the catalog has an Indigenous Chilean reference (see population_catalog).
        'ancestry_view': 'country' if catalog.country_view() else 'unit',
        'ancestry_by_country': by_country,
        'variants': variants,
    }


MIN_COHORT = 10  # Ley 21.719: below this, aggregates could single out a person, so nothing is returned.


def _share_keys(population, code, catalog):
    """Keys a reference result adds to: its unit and its country (the unit again when it has no country)."""
    if population not in catalog:
        return [code]  # Rows from before the catalog stand on their own.
    unit = catalog.unit_of(population)
    return list(dict.fromkeys((unit.code, population.metadata.get('country') or unit.code)))


def _ancestry_views(rows, catalog):
    """Reference results summed by reported unit (Andino) and by country (Perú), largest first."""
    by_unit, by_country = {}, {}
    for r in rows:
        value = float(r.value_numeric)
        if r.population not in catalog:
            by_unit[r.value_code] = {'population': r.value_code, 'label': r.population.name if r.population
                                     else r.value_code, **(r.payload or {}), 'proportion': value}
            continue
        unit, group = catalog.unit_of(r.population), catalog.group_of(r.population)
        entry = by_unit.setdefault(unit.code, {'population': unit.code, 'label': unit.name,
                                               **catalog.describe(unit), 'proportion': 0.0})
        entry['proportion'] += value
        country = r.population.metadata.get('country')
        place = by_country.setdefault(country or unit.code, {
            'key': country or unit.code, 'country_code': country, 'label': None if country else unit.name,
            'region_countries': [country] if country else unit.metadata['region_countries'],
            'proportion': 0.0, 'populations': []})
        place['proportion'] += value
        place['populations'].append({'population': r.value_code, 'label': r.population.name, 'unit': unit.code,
                                     'group': group.code, 'group_label': group.name, 'proportion': value,
                                     'note': group.metadata.get('client_note')})
    for place in by_country.values():
        place['populations'].sort(key=lambda p: -p['proportion'])
        top = place['populations'][0]
        place.update(group=top['group'], group_label=top['group_label'], note=top['note'])
    for entry in [*by_unit.values(), *by_country.values()]:
        entry['proportion'] = round(entry['proportion'], 6)
    return (sorted(by_unit.values(), key=lambda e: -e['proportion']),
            sorted(by_country.values(), key=lambda e: -e['proportion']))


def read_ancestry_cohort(user):
    """Where the client's global ancestry falls among other sequenced clients; aggregates only."""
    own = read_client_results(user)
    if own is None:
        return None
    mine = {row['population']: row['proportion'] for row in own['modules']['global_ancestry']}
    mine.update({row['key']: row['proportion'] for row in own['ancestry_by_country']})
    catalog = Catalog()
    latest = (Analysis.objects.filter(module='global_ancestry', status='completed')
              .exclude(participant__user=user)
              .order_by('participant_id', '-created_at', '-pk').distinct('participant_id').values_list('pk', flat=True))
    others = {}
    for analysis_id, population_id, code, value in AnalysisResult.objects.filter(
            analysis_id__in=list(latest), module='global_ancestry',
    ).values_list('analysis_id', 'population_id', 'value_code', 'value_numeric'):
        shares = others.setdefault(analysis_id, {})
        for key in _share_keys(catalog.by_pk.get(population_id), code, catalog):
            shares[key] = shares.get(key, 0.0) + float(value)
    size = len(others)
    if size < MIN_COHORT:
        return {'cohort_size': size, 'min_cohort': MIN_COHORT, 'populations': {}}
    populations = {}
    for code in sorted(set(mine).union(*others.values())):
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
    throttle_scope = 'results'

    def get(self, request):
        data = read_ancestry_cohort(request.user)
        record_genetic_access(request, GeneticDataAccessLog.Resource.ANCESTRY_COHORT, request.user.pk,
                              'not_found' if data is None else 'ok')
        if data is None:
            return Response({'error': 'No hay resultados disponibles'}, status=status.HTTP_404_NOT_FOUND)
        return Response(data)


class ClientResultsAPIView(APIView):
    """GET /api/genoma/v1/results/: only the logged-in client's own results (Ley 21.719)."""
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    throttle_scope = 'results'

    def get(self, request):
        data = read_client_results(request.user)
        record_genetic_access(request, GeneticDataAccessLog.Resource.RESULTS, request.user.pk,
                              'not_found' if data is None else 'ok')
        if data is None:
            return Response({'error': 'No hay resultados disponibles'}, status=status.HTTP_404_NOT_FOUND)
        return Response(data)
