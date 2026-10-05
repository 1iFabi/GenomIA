"""Fail-closed, owner-only reads of the immutable bundled synthetic v1 graph."""

import json
import uuid
from dataclasses import dataclass

from django.core.management.base import CommandError
from django.db.models import Q
from django.http import Http404

from accounts.models import AppUser, Role
from genetics import synthetic_import as bundle
from genetics.models import Analysis, AnalysisResult, DataRelease
from services.models import Purchase, Sample, ServiceRequest


@dataclass(frozen=True)
class SyntheticServiceRead:
    summary: dict
    results: list


def _related_rows(plan, marker, participant_id):
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
        | Q(release_id=bundle.RELEASE_ID, participant_id=participant_id))
    found[Analysis] = rows(Analysis,
        Q(parameters__import_id=marker['import_id']) | Q(sample_id=plan[Sample][0]['pk'])
        | Q(service_request_id=plan[ServiceRequest][0]['pk'])
        | Q(pk__in=[row.analysis_id for row in found[AnalysisResult]])
        | Q(pipeline_name=bundle.DEMO_NAME, pipeline_version=bundle.DEMO_VERSION, participant_id=participant_id))
    found[Sample] = rows(Sample,
        Q(metadata__import_id=marker['import_id']) | Q(sample_code=plan[Sample][0]['sample_code'])
        | Q(metadata__demo_id=bundle.DEMO_NAME, metadata__demo_version=bundle.DEMO_VERSION,
            participant_id=participant_id)
        | Q(service_request_id=plan[ServiceRequest][0]['pk'])
        | Q(pk__in=[row.sample_id for row in found[AnalysisResult] + found[Analysis]]))
    found[ServiceRequest] = rows(ServiceRequest,
        Q(purchase_id=plan[Purchase][0]['pk'])
        | Q(pk__in=[row.service_request_id for row in found[Sample] + found[Analysis]]))
    found[Purchase] = rows(Purchase, Q(pk__in=[row.purchase_id for row in found[ServiceRequest]]))
    return found


def _assert_bundle_row(row, values):
    bundle._assert_matches(row, values)
    # Python equates True with 1 and False with 0; JSON provenance must not.
    for field, expected in values.items():
        if isinstance(expected, dict) and json.dumps(
            getattr(row, field), sort_keys=True, separators=(',', ':'),
        ) != json.dumps(expected, sort_keys=True, separators=(',', ':')):
            raise CommandError(bundle.INCONSISTENT)


def _read_bundle(user, service_request_id):
    if not user.is_authenticated or not user.is_active:
        return None
    # Read live ownership/role, never a cached reverse relation or Django admin flags.
    owner = AppUser.objects.filter(
        django_user_id=user.pk, django_user__is_active=True, role__code=Role.Code.CLIENTE,
    ).first()
    if owner is None:
        return None
    kinds = ['import', 'purchase', 'request', 'sample'] + [
        f'{kind}:{module}' for module, _ in bundle.MODULES for kind in ('analysis', 'result')
    ]
    ids = {kind: bundle._identifier(f'app-user:{owner.pk}', kind) for kind in kinds}
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
    releases = list(DataRelease.objects.filter(
        Q(pk=bundle.RELEASE_ID) | Q(name=bundle.DEMO_NAME, version=bundle.DEMO_VERSION),
    ))
    if len(releases) != 1:
        return None
    release = releases[0]
    bundle._assert_matches(release, bundle._release_values())
    marker = bundle._provenance() | {
        'manifest_checksum': bundle.MANIFEST_CHECKSUM, 'import_id': str(ids['import']),
    }
    # The importer owns the exact bundle manifest, including placeholder values,
    # null biological fields and immutable identifiers/timestamps.
    plan = bundle._plan(ids, owner.pk, request.participant_id, request.purchase.status_id,
                        request.status_id, marker, request.purchase.created_at)
    found = _related_rows(plan, marker, request.participant_id)
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
        'synthetic': True, 'non_clinical': True, 'disclaimer': bundle.DISCLAIMER,
    }
    return SyntheticServiceRead(summary, [{
        'module': module, 'result_type': results[module].result_type,
        'value_code': results[module].value_code, 'value_text': results[module].value_text,
        # Only the validated raw placeholders/public provenance leave the reader;
        # import tokens and all participant/account relations remain internal.
        'payload': {key: value for key, value in results[module].payload.items()
                    if key not in ('import_id', 'manifest_checksum')},
    } for module, _ in bundle.MODULES])


def get_owned_synthetic_service(user, service_request_id=None):
    """Return a complete owned bundle or no service; a blocked environment is 404.

    Authentication happens in the views. The importer's guard is the sole local
    authority and must run before any domain query, even for missing services.
    """
    try:
        bundle._require_local_development()
    except CommandError:
        raise Http404 from None
    try:
        return _read_bundle(user, service_request_id)
    except CommandError:
        return None
