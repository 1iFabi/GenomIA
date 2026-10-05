"""Immutable bundled demos, never biological or clinical imports.

No file, payload, owner, consent, or completion override is accepted. Version 1
and its Python defaults remain unchanged; the management command defaults to
version 2. Display-fixture changes require a new version, never an upsert.
"""

import hashlib
import ipaddress
import json
import os
import uuid
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management.base import CommandError
from django.db import DatabaseError, IntegrityError, connection, transaction
from django.db.models import Q
from django.utils import timezone

from accounts.models import AppUser, Role
from genoma.models import Analysis, AnalysisResult, DataRelease
from participants.models import Participant
from services.models import Purchase, PurchaseStatus, Sample, ServiceRequest, ServiceStatus


DEMO_NAME = 'gdb-04f1-synthetic-genomics'
DEMO_VERSION = '1'  # Compatibility constants and Python entry-point defaults are immutable.
DEFAULT_DEMO_VERSION = '2'
SUPPORTED_DEMO_VERSIONS = ('1', '2')
V2_MANIFEST_CHECKSUM = '08ca8e67cb5e620b840d058d7869f4058215814eaa1cac63903beea18a1fcc95'
V2_DISCLAIMER = (
    'SYNTHETIC DEMO ONLY: fictional non-clinical display fixtures, not derived from a biological sample. '
    'All numeric values are arbitrary demo-only display fixtures and are not evaluated. '
    'No biological, risk, actionability, or clinical interpretation is provided. '
    'Not for diagnosis, treatment, or medical decisions. No clinical review or consent is implied.'
)
DISCLAIMER = (
    'SYNTHETIC DEMO ONLY: non-clinical placeholders, not derived from a biological sample. '
    'Not for diagnosis, treatment, or medical decisions. No clinical review or consent is implied.'
)
MODULES = (
    ('global_ancestry', 'Synthetic global ancestry placeholder'),
    ('local_ancestry', 'Synthetic local ancestry placeholder'),
    ('polygenic_risk', 'Synthetic polygenic risk placeholder'),
    ('monogenic_risk', 'Synthetic monogenic risk placeholder'),
    ('traits', 'Synthetic traits placeholder'),
    ('pharmacogenetics', 'Synthetic pharmacogenetics placeholder'),
)
LOCAL_ONLY = (
    'Synthetic import requires explicit local development: ENVIRONMENT=development, DEBUG=True, '
    'no deployment signals or database routers, and a verified loopback PostgreSQL development database.'
)
INCONSISTENT = 'Inconsistent or duplicate synthetic import; no rows were changed. Manual inspection is required.'


def _placeholder(module, label):
    return {
        'module': module, 'label': label, 'state': 'not_evaluated',
        'rows': [{'label': label, 'state': 'not_evaluated', 'value': None}],
    }


def _provenance():
    return {
        'demo_id': DEMO_NAME, 'demo_version': DEMO_VERSION,
        'synthetic': True, 'non_clinical': True, 'clinically_reviewed': False,
        'disclaimer': DISCLAIMER,
    }


# Canonical, account-independent manifest: no input files or identifying data.
MANIFEST_CHECKSUM = hashlib.sha256(json.dumps(
    _provenance() | {'modules': [_placeholder(module, label) for module, label in MODULES]},
    sort_keys=True, separators=(',', ':'),
).encode('utf-8')).hexdigest()


def _identifier(scope, kind, *, version=DEMO_VERSION):
    return uuid.uuid5(uuid.NAMESPACE_URL, f'genomia:{DEMO_NAME}:{version}:{scope}:{kind}')


RELEASE_ID = _identifier('bundle', 'release')
# Serialize the shared release as well as same-account retries across processes.
IMPORT_LOCK = int.from_bytes(RELEASE_ID.bytes[:8], byteorder='big', signed=True)


def _validate_demo_version(version):
    if type(version) is not str or version not in SUPPORTED_DEMO_VERSIONS:
        raise CommandError('Select bundled demo version 1 or 2; caller file paths are not accepted.')


def _unique_json_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError('Duplicate fixture field.')
        value[key] = item
    return value


def _validate_v2_manifest(manifest):
    """Closed display schema: no free-text biology/PII, typed results or evaluation.

    Exact labels, fields and types are allowlisted. Numeric values describe only
    fictional components, abstract segments or display items, never genomic data.
    The separate pinned checksum freezes even schema-valid numeric changes.
    """
    def require(condition):
        if not condition:
            raise CommandError('Invalid bundled synthetic v2 schema; nothing was imported.')

    def shape(value, fields):
        require(type(value) is dict and set(value) == set(fields))

    def integer(value, minimum=0, maximum=100):
        require(type(value) is int and minimum <= value <= maximum)

    provenance = _provenance() | {
        'demo_version': '2', 'schema_version': '2', 'display_only': True,
        'numeric_semantics': 'arbitrary_demo_only_not_evaluated', 'disclaimer': V2_DISCLAIMER,
    }
    shape(manifest, set(provenance) | {'modules'})
    for key, expected in provenance.items():
        require(type(manifest[key]) is type(expected) and manifest[key] == expected)
    modules = manifest['modules']
    require(type(modules) is list and len(modules) == len(MODULES))
    displays = (
        ('fictional_components', 'Demo group A'), ('abstract_segments', 'Demo group A'),
        ('demo_index', 'Demo index A'), ('demo_entries', 'Demo index A'),
        ('demo_traits', 'Demo trait A'), ('demo_interactions', 'Demo interaction A'),
    )
    for item, (module, _), (kind, label) in zip(modules, MODULES, displays):
        shape(item, ('module', 'label', 'state', 'display'))
        require((item['module'], item['label'], item['state']) == (module, label, 'not_evaluated'))
        display = item['display']
        if module == 'global_ancestry':
            shape(display, ('kind', 'components'))
            components = display['components']
            require(type(components) is list and len(components) == 2)
            for component, group in zip(components, ('Demo group A', 'Demo group B')):
                shape(component, ('label', 'display_percentage'))
                require(component['label'] == group)
                integer(component['display_percentage'])
            require(sum(row['display_percentage'] for row in components) == 100)
        elif module == 'local_ancestry':
            shape(display, ('kind', 'axis', 'segments'))
            axis = display['axis']
            shape(axis, ('label', 'extent', 'unit'))
            require((axis['label'], axis['unit']) == ('Demo axis A', 'abstract_demo_units'))
            integer(axis['extent'], minimum=1)
            segments = display['segments']
            require(type(segments) is list and len(segments) == 2)
            offset = 0
            for segment, group in zip(segments, ('Demo group A', 'Demo group B')):
                shape(segment, ('label', 'offset', 'length'))
                require(segment['label'] == group)
                integer(segment['offset'])
                integer(segment['length'], minimum=1)
                require(segment['offset'] == offset)
                offset += segment['length']
            require(offset == axis['extent'])
        else:
            shape(display, ('kind', 'items'))
            require(type(display['items']) is list and len(display['items']) == 1)
            entry = display['items'][0]
            shape(entry, ('label', 'display_value'))
            require(entry['label'] == label)
            integer(entry['display_value'])
        require(display['kind'] == kind)


@dataclass(frozen=True)
class SyntheticDemoBundle:
    version: str
    manifest: dict
    manifest_checksum: str

    @property
    def provenance(self):
        return {key: value for key, value in self.manifest.items() if key != 'modules'}

    @property
    def release_id(self):
        return _identifier('bundle', 'release', version=self.version)

    @property
    def import_lock(self):
        return int.from_bytes(self.release_id.bytes[:8], byteorder='big', signed=True)

    @property
    def disclaimer(self):
        return self.manifest['disclaimer']


def get_synthetic_bundle(version=DEMO_VERSION):
    """Load only a known packaged version; fresh objects cannot mutate later loads."""
    _validate_demo_version(version)
    if version == '1':
        manifest = _provenance() | {'modules': [_placeholder(module, label) for module, label in MODULES]}
        return SyntheticDemoBundle(version, manifest, MANIFEST_CHECKSUM)
    try:
        manifest = json.loads(
            (Path(__file__).parent / 'fixtures' / 'synthetic_genomics_v2.json').read_text(encoding='utf-8'),
            object_pairs_hook=_unique_json_object,
        )
    except (OSError, UnicodeError, ValueError) as error:
        raise CommandError('Invalid or unavailable bundled synthetic v2 schema; nothing was imported.') from error
    _validate_v2_manifest(manifest)
    checksum = hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()
    if checksum != V2_MANIFEST_CHECKSUM:
        raise CommandError('Bundled synthetic v2 checksum mismatch; fixture changes require a new version.')
    return SyntheticDemoBundle(version, manifest, checksum)


@dataclass(frozen=True)
class SyntheticImportReceipt:
    created: bool
    purchase_id: uuid.UUID
    service_request_id: uuid.UUID
    sample_id: uuid.UUID


def validate_user_id(user_id):
    maximum = connection.ops.integer_field_range(get_user_model()._meta.pk.get_internal_type())[1]
    if type(user_id) is not int or maximum is None or not 0 < user_id <= maximum:
        raise CommandError('An explicit positive Django User ID is required.')
    return user_id


def _require_local_development():
    config = connection.settings_dict
    if (
        os.environ.get('ENVIRONMENT') != 'development' or settings.DEBUG is not True
        or any(os.environ.get(key) for key in ('RENDER', 'RENDER_EXTERNAL_HOSTNAME'))
        or settings.DATABASE_ROUTERS or config.get('ENGINE') != 'django.db.backends.postgresql'
        or config.get('HOST') not in ('127.0.0.1', '::1', 'localhost')
        or not config.get('NAME') or config['NAME'] in ('postgres', 'template0', 'template1')
        or {'service', 'host', 'hostaddr', 'dbname', 'database'} & set(config.get('OPTIONS') or {})
    ):
        raise CommandError(LOCAL_ONLY)
    # Check the actual connection too: configuration alone cannot validate a tunnel,
    # libpq override, or misresolved localhost. No domain queries precede this guard.
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT current_database(), inet_server_addr()::text')
            database, server = cursor.fetchone()
        address = ipaddress.ip_interface(server).ip
        mapped = getattr(address, 'ipv4_mapped', None)
        if database != config['NAME'] or not (address.is_loopback or mapped and mapped.is_loopback):
            raise CommandError(LOCAL_ONLY)
    except (DatabaseError, ValueError, TypeError) as error:
        raise CommandError(LOCAL_ONLY) from error


def _assert_matches(row, values, *, strict_json=False):
    if row is None or any(getattr(row, field) != expected for field, expected in values.items()):
        raise CommandError(INCONSISTENT)
    if strict_json:
        for field, expected in values.items():
            if isinstance(expected, dict) and json.dumps(
                getattr(row, field), sort_keys=True, separators=(',', ':'),
            ) != json.dumps(expected, sort_keys=True, separators=(',', ':')):
                raise CommandError(INCONSISTENT)  # JSON booleans are not integer flags.


def _release_values(*, demo=None):
    demo = demo or get_synthetic_bundle()
    return {
        'pk': demo.release_id, 'name': DEMO_NAME, 'version': demo.version, 'status': 'synthetic',
        'reference_assembly': 'not-applicable', 'description': demo.disclaimer,
        'manifest_checksum': demo.manifest_checksum, 'frozen_at': None,
    }


def _plan(ids, owner_id, participant_id, paid_id, waiting_id, marker, timestamp, *, demo=None):
    demo = demo or get_synthetic_bundle()
    plan = {
        Purchase: [{
            'pk': ids['purchase'], 'owner_id': owner_id, 'status_id': paid_id,
            'purchased_at': timestamp, 'created_at': timestamp,
        }],
        ServiceRequest: [{
            'pk': ids['request'], 'purchase_id': ids['purchase'], 'participant_id': participant_id,
            'status_id': waiting_id, 'created_at': timestamp, 'started_at': timestamp, 'completed_at': None,
        }],
        Sample: [{
            'pk': ids['sample'], 'service_request_id': ids['request'], 'participant_id': participant_id,
            'parent_sample_id': None, 'sample_code': f'SYNTHETIC-DEMO-V{demo.version}-{ids["sample"].hex}',
            'sample_type': 'synthetic', 'status': 'synthetic', 'metadata': marker,
            'material': None, 'collection_method': None, 'collected_at': None, 'storage_location': None,
            'created_at': timestamp,
        }],
        Analysis: [], AnalysisResult: [],
    }
    for payload in demo.manifest['modules']:
        module, label = payload['module'], payload['label']
        plan[Analysis].append({
            'pk': ids[f'analysis:{module}'], 'participant_id': participant_id, 'sample_id': ids['sample'],
            'service_request_id': ids['request'], 'release_id': demo.release_id, 'module': module,
            'pipeline_name': DEMO_NAME, 'pipeline_version': demo.version, 'container_digest': None,
            'reference_assembly': None, 'parameters': marker | {'module': module},
            'status': 'synthetic_placeholder', 'started_at': None, 'finished_at': None, 'created_at': timestamp,
        })
        plan[AnalysisResult].append({
            'pk': ids[f'result:{module}'], 'analysis_id': ids[f'analysis:{module}'],
            'participant_id': participant_id, 'sample_id': ids['sample'], 'release_id': demo.release_id,
            'module': module, 'result_type': 'synthetic_placeholder',
            'value_text': f'{label}. {demo.disclaimer}', 'value_code': 'SYNTHETIC_NOT_EVALUATED',
            'payload': marker | payload, 'created_at': timestamp,
            **dict.fromkeys(('variant_id', 'epigenetic_feature_id', 'population_id', 'reference_assembly',
                             'contig', 'start_pos', 'end_pos', 'haplotype', 'value_numeric', 'unit',
                             'percentile', 'confidence')),
        })
    return plan


def _existing_rows(plan, marker, participant_id, *, demo=None):
    """Find reserved keys AND displaced/duplicate rows carrying our provenance.

    Follow upstream references as well: a duplicate cannot escape detection just
    by replacing its primary key, or by pointing a marked row at another owner.
    Never adopt or update these rows, even when they look repairable.
    """
    demo = demo or get_synthetic_bundle()

    def rows(model, extra):
        keys = [values['pk'] for values in plan[model]]
        return list(model.objects.select_for_update(of=('self',)).filter(Q(pk__in=keys) | extra))

    found = {}
    found[AnalysisResult] = rows(AnalysisResult,
        Q(payload__import_id=marker['import_id']) | Q(sample_id=plan[Sample][0]['pk'])
        | Q(analysis_id__in=[values['pk'] for values in plan[Analysis]])
        | Q(release_id=demo.release_id, participant_id=participant_id))
    found[Analysis] = rows(Analysis,
        Q(parameters__import_id=marker['import_id']) | Q(sample_id=plan[Sample][0]['pk'])
        | Q(service_request_id=plan[ServiceRequest][0]['pk'])
        | Q(pk__in=[row.analysis_id for row in found[AnalysisResult]])
        | Q(pipeline_name=DEMO_NAME, pipeline_version=demo.version, participant_id=participant_id))
    found[Sample] = rows(Sample,
        Q(metadata__import_id=marker['import_id']) | Q(sample_code=plan[Sample][0]['sample_code'])
        | Q(metadata__demo_id=DEMO_NAME, metadata__demo_version=demo.version, participant_id=participant_id)
        | Q(service_request_id=plan[ServiceRequest][0]['pk'])
        | Q(pk__in=[row.sample_id for row in found[AnalysisResult] + found[Analysis]]))
    found[ServiceRequest] = rows(ServiceRequest,
        Q(purchase_id=plan[Purchase][0]['pk'])
        | Q(pk__in=[row.service_request_id for row in found[Sample] + found[Analysis]]))
    found[Purchase] = rows(Purchase, Q(pk__in=[row.purchase_id for row in found[ServiceRequest]]))
    return found


def import_synthetic_genomics(*, user_id, version=DEMO_VERSION):
    """Create a versioned owned demo, or validate it without writes; v1 remains the Python default."""
    validate_user_id(user_id)
    _validate_demo_version(version)
    _require_local_development()
    demo = get_synthetic_bundle(version)
    try:
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute('SELECT pg_advisory_xact_lock(%s)', [demo.import_lock])
            user = get_user_model().objects.select_for_update().filter(pk=user_id, is_active=True).first()
            owner = AppUser.objects.select_for_update(of=('self',)).filter(
                django_user_id=user_id, role__code=Role.Code.CLIENTE,
            ).first() if user else None
            if owner is None:
                raise CommandError('The selected Django User must have an existing active client AppUser mapping.')
            paid = PurchaseStatus.objects.filter(code='PAID').first()
            waiting = ServiceStatus.objects.filter(code='WAITING_SAMPLE').first()
            if paid is None or waiting is None:
                raise CommandError('Required purchase/service status catalog is unavailable; nothing was imported.')

            scope = f'app-user:{owner.user_id}'
            kinds = ['import', 'participant', 'purchase', 'request', 'sample'] + [
                f'{kind}:{module}' for module, _ in MODULES for kind in ('analysis', 'result')
            ]
            ids = {kind: _identifier(scope, kind, version=demo.version) for kind in kinds}
            marker = demo.provenance | {'manifest_checksum': demo.manifest_checksum, 'import_id': str(ids['import'])}
            participant_code = f'SYNTHETIC-{ids["participant"].hex}'
            participants = list(Participant.objects.select_for_update().filter(
                Q(user_id=user_id) | Q(pk=ids['participant']) | Q(participant_code=participant_code)
                | Q(metadata__import_id=marker['import_id']),
            ))
            if len(participants) > 1 or participants and participants[0].user_id != user_id:
                raise CommandError(INCONSISTENT)
            participant = participants[0] if participants else None
            seeded_participant = participant is not None and (
                participant.pk == ids['participant'] or participant.participant_code == participant_code
                or isinstance(participant.metadata, dict) and participant.metadata.get('import_id') == marker['import_id']
            )
            if seeded_participant:
                _assert_matches(participant, {
                    'pk': ids['participant'], 'user_id': user_id,
                    'participant_code': participant_code, 'metadata': marker,
                }, strict_json=demo.version == '2')  # Consent/enrollment are never inferred, granted, or overwritten.

            releases = list(DataRelease.objects.select_for_update().filter(
                Q(pk=demo.release_id) | Q(name=DEMO_NAME, version=demo.version),
            ))
            if len(releases) > 1:
                raise CommandError(INCONSISTENT)
            release = releases[0] if releases else None
            if release:
                _assert_matches(release, _release_values(demo=demo))
            participant_id = participant.pk if participant else ids['participant']
            plan = _plan(ids, owner.pk, participant_id, paid.pk, waiting.pk, marker, timezone.now(), demo=demo)
            found = _existing_rows(plan, marker, participant_id, demo=demo)
            exists = any(found.values())
            if exists:
                if participant is None or release is None:
                    raise CommandError(INCONSISTENT)
                purchase = next((row for row in found[Purchase] if row.pk == ids['purchase']), None)
                if purchase is None:
                    raise CommandError(INCONSISTENT)
                plan = _plan(ids, owner.pk, participant_id, paid.pk, waiting.pk, marker, purchase.created_at, demo=demo)
                for model, expected in plan.items():
                    actual = {row.pk: row for row in found[model]}
                    if set(actual) != {values['pk'] for values in expected}:
                        raise CommandError(INCONSISTENT)
                    for values in expected:
                        _assert_matches(actual[values['pk']], values, strict_json=demo.version == '2')
            else:
                if seeded_participant:
                    raise CommandError(INCONSISTENT)  # A participant-only partial import is not resumable.
                if participant is None:
                    Participant.objects.create(
                        pk=participant_id, user_id=user_id, participant_code=participant_code, metadata=marker,
                    )  # Model defaults deliberately leave enrollment and consent pending.
                if release is None:
                    DataRelease.objects.create(**_release_values(demo=demo))
                # Parents first; ordinary saves preserve the existing ownership validation.
                for model, values_list in plan.items():
                    for values in values_list:
                        model.objects.create(**values)
            return SyntheticImportReceipt(not exists, ids['purchase'], ids['request'], ids['sample'])
    except (IntegrityError, ValidationError) as error:
        # A competing non-command writer or key collision never triggers an upsert/repair.
        raise CommandError(INCONSISTENT) from error
