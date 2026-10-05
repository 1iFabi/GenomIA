"""Immutable bundled GDB-04f1 demo, never a biological or clinical import.

Only the management command uses this entry point. No file, payload, owner,
consent, or completion override is accepted. Version 1 must remain immutable;
changes to the bundled placeholders require a new explicitly versioned demo.
"""

import hashlib
import ipaddress
import json
import os
import uuid
from dataclasses import dataclass

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management.base import CommandError
from django.db import DatabaseError, IntegrityError, connection, transaction
from django.db.models import Q
from django.utils import timezone

from accounts.models import AppUser, Role
from genetics.models import Analysis, AnalysisResult, DataRelease
from participants.models import Participant
from services.models import Purchase, PurchaseStatus, Sample, ServiceRequest, ServiceStatus


DEMO_NAME = 'gdb-04f1-synthetic-genomics'
DEMO_VERSION = '1'
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


def _identifier(scope, kind):
    return uuid.uuid5(uuid.NAMESPACE_URL, f'genomia:{DEMO_NAME}:{DEMO_VERSION}:{scope}:{kind}')


RELEASE_ID = _identifier('bundle', 'release')
# Serialize the shared release as well as same-account retries across processes.
IMPORT_LOCK = int.from_bytes(RELEASE_ID.bytes[:8], byteorder='big', signed=True)


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


def _assert_matches(row, values):
    if row is None or any(getattr(row, field) != expected for field, expected in values.items()):
        raise CommandError(INCONSISTENT)


def _release_values():
    return {
        'pk': RELEASE_ID, 'name': DEMO_NAME, 'version': DEMO_VERSION, 'status': 'synthetic',
        'reference_assembly': 'not-applicable', 'description': DISCLAIMER,
        'manifest_checksum': MANIFEST_CHECKSUM, 'frozen_at': None,
    }


def _plan(ids, owner_id, participant_id, paid_id, waiting_id, marker, timestamp):
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
            'parent_sample_id': None, 'sample_code': f'SYNTHETIC-DEMO-V{DEMO_VERSION}-{ids["sample"].hex}',
            'sample_type': 'synthetic', 'status': 'synthetic', 'metadata': marker,
            'material': None, 'collection_method': None, 'collected_at': None, 'storage_location': None,
            'created_at': timestamp,
        }],
        Analysis: [], AnalysisResult: [],
    }
    for module, label in MODULES:
        plan[Analysis].append({
            'pk': ids[f'analysis:{module}'], 'participant_id': participant_id, 'sample_id': ids['sample'],
            'service_request_id': ids['request'], 'release_id': RELEASE_ID, 'module': module,
            'pipeline_name': DEMO_NAME, 'pipeline_version': DEMO_VERSION, 'container_digest': None,
            'reference_assembly': None, 'parameters': marker | {'module': module},
            'status': 'synthetic_placeholder', 'started_at': None, 'finished_at': None, 'created_at': timestamp,
        })
        plan[AnalysisResult].append({
            'pk': ids[f'result:{module}'], 'analysis_id': ids[f'analysis:{module}'],
            'participant_id': participant_id, 'sample_id': ids['sample'], 'release_id': RELEASE_ID,
            'module': module, 'result_type': 'synthetic_placeholder',
            'value_text': f'{label}. {DISCLAIMER}', 'value_code': 'SYNTHETIC_NOT_EVALUATED',
            'payload': marker | _placeholder(module, label), 'created_at': timestamp,
            **dict.fromkeys(('variant_id', 'epigenetic_feature_id', 'population_id', 'reference_assembly',
                             'contig', 'start_pos', 'end_pos', 'haplotype', 'value_numeric', 'unit',
                             'percentile', 'confidence')),
        })
    return plan


def _existing_rows(plan, marker, participant_id):
    """Find reserved keys AND displaced/duplicate rows carrying our provenance.

    Follow upstream references as well: a duplicate cannot escape detection just
    by replacing its primary key, or by pointing a marked row at another owner.
    Never adopt or update these rows, even when they look repairable.
    """
    def rows(model, extra):
        keys = [values['pk'] for values in plan[model]]
        return list(model.objects.select_for_update(of=('self',)).filter(Q(pk__in=keys) | extra))

    found = {}
    found[AnalysisResult] = rows(AnalysisResult,
        Q(payload__import_id=marker['import_id']) | Q(sample_id=plan[Sample][0]['pk'])
        | Q(analysis_id__in=[values['pk'] for values in plan[Analysis]])
        | Q(release_id=RELEASE_ID, participant_id=participant_id))
    found[Analysis] = rows(Analysis,
        Q(parameters__import_id=marker['import_id']) | Q(sample_id=plan[Sample][0]['pk'])
        | Q(service_request_id=plan[ServiceRequest][0]['pk'])
        | Q(pk__in=[row.analysis_id for row in found[AnalysisResult]])
        | Q(pipeline_name=DEMO_NAME, pipeline_version=DEMO_VERSION, participant_id=participant_id))
    found[Sample] = rows(Sample,
        Q(metadata__import_id=marker['import_id']) | Q(sample_code=plan[Sample][0]['sample_code'])
        | Q(metadata__demo_id=DEMO_NAME, metadata__demo_version=DEMO_VERSION, participant_id=participant_id)
        | Q(service_request_id=plan[ServiceRequest][0]['pk'])
        | Q(pk__in=[row.sample_id for row in found[AnalysisResult] + found[Analysis]]))
    found[ServiceRequest] = rows(ServiceRequest,
        Q(purchase_id=plan[Purchase][0]['pk'])
        | Q(pk__in=[row.service_request_id for row in found[Sample] + found[Analysis]]))
    found[Purchase] = rows(Purchase, Q(pk__in=[row.purchase_id for row in found[ServiceRequest]]))
    return found


def import_synthetic_genomics(*, user_id):
    """Create one owned demo chain, or validate an exact existing chain without writes."""
    validate_user_id(user_id)
    _require_local_development()
    try:
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute('SELECT pg_advisory_xact_lock(%s)', [IMPORT_LOCK])
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
            ids = {kind: _identifier(scope, kind) for kind in kinds}
            marker = _provenance() | {'manifest_checksum': MANIFEST_CHECKSUM, 'import_id': str(ids['import'])}
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
                })  # Existing consent/enrollment are never inferred, granted, or overwritten.

            releases = list(DataRelease.objects.select_for_update().filter(
                Q(pk=RELEASE_ID) | Q(name=DEMO_NAME, version=DEMO_VERSION),
            ))
            if len(releases) > 1:
                raise CommandError(INCONSISTENT)
            release = releases[0] if releases else None
            if release:
                _assert_matches(release, _release_values())
            participant_id = participant.pk if participant else ids['participant']
            plan = _plan(ids, owner.pk, participant_id, paid.pk, waiting.pk, marker, timezone.now())
            found = _existing_rows(plan, marker, participant_id)
            exists = any(found.values())
            if exists:
                if participant is None or release is None:
                    raise CommandError(INCONSISTENT)
                purchase = next((row for row in found[Purchase] if row.pk == ids['purchase']), None)
                if purchase is None:
                    raise CommandError(INCONSISTENT)
                plan = _plan(ids, owner.pk, participant_id, paid.pk, waiting.pk, marker, purchase.created_at)
                for model, expected in plan.items():
                    actual = {row.pk: row for row in found[model]}
                    if set(actual) != {values['pk'] for values in expected}:
                        raise CommandError(INCONSISTENT)
                    for values in expected:
                        _assert_matches(actual[values['pk']], values)
            else:
                if seeded_participant:
                    raise CommandError(INCONSISTENT)  # A participant-only partial import is not resumable.
                if participant is None:
                    Participant.objects.create(
                        pk=participant_id, user_id=user_id, participant_code=participant_code, metadata=marker,
                    )  # Model defaults deliberately leave enrollment and consent pending.
                if release is None:
                    DataRelease.objects.create(**_release_values())
                # Parents first; ordinary saves preserve the existing ownership validation.
                for model, values_list in plan.items():
                    for values in values_list:
                        model.objects.create(**values)
            return SyntheticImportReceipt(not exists, ids['purchase'], ids['request'], ids['sample'])
    except (IntegrityError, ValidationError) as error:
        # A competing non-command writer or key collision never triggers an upsert/repair.
        raise CommandError(INCONSISTENT) from error
