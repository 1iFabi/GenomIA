"""Fail-closed, owner-only reads of complete immutable bundled synthetic graphs."""

import uuid
from dataclasses import dataclass
from datetime import datetime

from django.core.management.base import CommandError
from django.db.models import Q
from django.http import Http404

from accounts.models import AppUser, Role
from genoma import synthetic_import as bundle
from genoma.models import Analysis, AnalysisResult, DataRelease
from services.models import Purchase, Sample, ServiceRequest


@dataclass(frozen=True)
class SyntheticServiceRead:
    summary: dict
    results: list
    metrics: dict
    purchased_at: datetime
    purchase_ordering: tuple


def _related_rows(plan, marker, participant_id, *, demo):
    """Include reserved keys, provenance and displaced upstream links, not just valid rows.

    Filtering to matching modules/markers would hide corruption and duplicates.
    Unlike the importer's retry scan, these reads never acquire write locks.
    """
    def rows(model, extra):
        return list(model.objects.filter(Q(pk__in=[values['pk'] for values in plan[model]]) | extra))

    found = {}
    found[AnalysisResult] = rows(AnalysisResult,
        Q(payload__import_id=marker['import_id']) | Q(sample_id=plan[Sample][0]['pk'])
        | Q(analysis_id__in=[values['pk'] for values in plan[Analysis]])
        | Q(release_id=demo.release_id, participant_id=participant_id))
    found[Analysis] = rows(Analysis,
        Q(parameters__import_id=marker['import_id']) | Q(sample_id=plan[Sample][0]['pk'])
        | Q(service_request_id=plan[ServiceRequest][0]['pk'])
        | Q(pk__in=[row.analysis_id for row in found[AnalysisResult]])
        | Q(pipeline_name=bundle.DEMO_NAME, pipeline_version=demo.version, participant_id=participant_id))
    found[Sample] = rows(Sample,
        Q(metadata__import_id=marker['import_id']) | Q(sample_code=plan[Sample][0]['sample_code'])
        | Q(metadata__demo_id=bundle.DEMO_NAME, metadata__demo_version=demo.version,
            participant_id=participant_id)
        | Q(service_request_id=plan[ServiceRequest][0]['pk'])
        | Q(pk__in=[row.sample_id for row in found[AnalysisResult] + found[Analysis]]))
    found[ServiceRequest] = rows(ServiceRequest,
        Q(purchase_id=plan[Purchase][0]['pk'])
        | Q(pk__in=[row.service_request_id for row in found[Sample] + found[Analysis]]))
    found[Purchase] = rows(Purchase, Q(pk__in=[row.purchase_id for row in found[ServiceRequest]]))
    return found


def _assert_bundle_row(row, values):
    bundle._assert_matches(row, values, strict_json=True)


def _record_count_metrics(analyses, results):
    """Count validated persisted records, never evaluated or biological outcomes."""
    modules = []
    for module, _ in bundle.MODULES:
        module_analyses = [row for row in analyses if row.module == module]
        module_results = [row for row in results if row.module == module]
        modules.append({
            'module': module,
            'analysis_record_count': len(module_analyses),
            'analysis_synthetic_placeholder_record_count': sum(
                row.status == 'synthetic_placeholder' for row in module_analyses),
            'analysis_result_record_count': len(module_results),
            'result_synthetic_placeholder_record_count': sum(
                row.result_type == 'synthetic_placeholder' and row.payload['state'] == 'not_evaluated'
                for row in module_results),
        })
    return {'kind': 'record_count', 'modules': modules}


def _read_bundle(user, service_request_id, *, version=bundle.DEMO_VERSION):
    if not user.is_authenticated or not user.is_active:
        return None
    # Read live ownership/role, never a cached reverse relation or Django admin flags.
    owner = AppUser.objects.filter(
        django_user_id=user.pk, django_user__is_active=True, role__code=Role.Code.CLIENTE,
    ).first()
    if owner is None:
        return None
    kinds = ['import', 'participant', 'purchase', 'request', 'sample'] + [
        f'{kind}:{module}' for module, _ in bundle.MODULES for kind in ('analysis', 'result')
    ]
    ids = {kind: bundle._identifier(f'app-user:{owner.pk}', kind, version=version) for kind in kinds}
    if service_request_id is not None:
        try:
            if uuid.UUID(str(service_request_id)) != ids['request']:
                return None
        except (ValueError, TypeError, AttributeError):
            return None
    request = ServiceRequest.objects.select_related('purchase', 'participant').filter(
        pk=ids['request'], purchase_id=ids['purchase'], purchase__owner_id=owner.pk,
        purchase__owner__django_user_id=user.pk, purchase__status__code='PAID',
        participant__user_id=user.pk, status__code='WAITING_SAMPLE',
    ).first()
    if request is None:
        return None
    demo = bundle.get_synthetic_bundle(version)
    releases = list(DataRelease.objects.filter(
        Q(pk=demo.release_id) | Q(name=bundle.DEMO_NAME, version=demo.version),
    ))
    if len(releases) != 1:
        return None
    release = releases[0]
    bundle._assert_matches(release, bundle._release_values(demo=demo))
    marker = demo.provenance | {
        'manifest_checksum': demo.manifest_checksum, 'import_id': str(ids['import']),
    }
    if demo.version == '2':
        participant = request.participant
        participant_code = f'SYNTHETIC-{ids["participant"].hex}'
        seeded = (
            participant.pk == ids['participant'] or participant.participant_code == participant_code
            or isinstance(participant.metadata, dict) and participant.metadata.get('import_id') == marker['import_id']
        )
        if seeded:
            _assert_bundle_row(participant, {
                'pk': ids['participant'], 'user_id': user.pk,
                'participant_code': participant_code, 'metadata': marker,
            })  # Generic/v1 participants and independent consent/enrollment stay untouched.
    # The importer owns the exact bundle manifest, including placeholder values,
    # null biological fields and immutable identifiers/timestamps.
    plan = bundle._plan(ids, owner.pk, request.participant_id, request.purchase.status_id,
                        request.status_id, marker, request.purchase.created_at, demo=demo)
    found = _related_rows(plan, marker, request.participant_id, demo=demo)
    for model, expected in plan.items():
        actual = {row.pk: row for row in found[model]}
        if set(actual) != {values['pk'] for values in expected}:
            return None
        for values in expected:
            _assert_bundle_row(actual[values['pk']], values)
    sample = found[Sample][0]
    results = {row.module: row for row in found[AnalysisResult]}
    summary = {
        'service_request_id': str(request.pk), 'sample_id': str(sample.pk),
        'sample_code': sample.sample_code, 'release_version': release.version,
        'synthetic': True, 'non_clinical': True, 'disclaimer': demo.disclaimer,
    }
    return SyntheticServiceRead(
        summary=summary,
        results=[{
            'module': module, 'result_type': results[module].result_type,
            'value_code': results[module].value_code, 'value_text': results[module].value_text,
            # Only validated raw demo display data/public provenance leave the reader;
            # import tokens and all participant/account relations remain internal.
            'payload': {key: value for key, value in results[module].payload.items()
                        if key not in ('import_id', 'manifest_checksum')},
        } for module, _ in bundle.MODULES],
        metrics=_record_count_metrics(found[Analysis], found[AnalysisResult]),
        purchased_at=request.purchase.purchased_at,
        purchase_ordering=(request.purchase.purchased_at, request.purchase.created_at, request.purchase.pk),
    )


def get_owned_synthetic_service(user, service_request_id=None):
    """Return a complete owned bundle or no service; a blocked environment is 404.

    Authentication happens in the views. The importer's guard is the sole local
    authority and must run before any domain query, even for missing services.
    """
    try:
        bundle._require_local_development()
    except CommandError:
        raise Http404 from None
    versions = bundle.SUPPORTED_DEMO_VERSIONS if service_request_id is not None else (bundle.DEMO_VERSION,)
    for version in versions:
        try:
            service = _read_bundle(user, service_request_id, version=version)
        except CommandError:
            continue
        if service is not None:
            return service
    return None


def list_owned_synthetic_services(user):
    """List actually imported, fully validated bundles in stable version order.

    Each version fails closed independently: corrupt or absent v2 never hides an
    intact v1, and vice versa. No account selector or inferred placeholder enters
    this list, and the local guard runs once before any domain query.
    """
    try:
        bundle._require_local_development()
    except CommandError:
        raise Http404 from None
    services = []
    for version in bundle.SUPPORTED_DEMO_VERSIONS:
        try:
            service = _read_bundle(user, None, version=version)
        except CommandError:
            continue
        if service is not None:
            services.append(service)
    return sorted(services, key=lambda service: service.purchase_ordering, reverse=True)
