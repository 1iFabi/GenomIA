import re

from django.db.models import Q
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from accounts.authentication import JWTAuthentication
from accounts.csrf import CSRFDoubleSubmitMixin
from profiles.models import Profile
from accounts.models import AppUser, Role
from accounts.roles import is_admin, is_reception
from participants.models import Participant
from reception.models import ReceptionAccessLog
from services.models import Sample
from services.status import ClientStatus, get_service_projections


def has_reception_access(user) -> bool:
    """Devuelve True si el usuario puede operar en recepción (admin o recepción)."""
    return is_admin(user) or is_reception(user)


def _log(request, action, *, query='', target_user_id=None, outcome):
    ReceptionAccessLog.objects.create(
        actor=AppUser.objects.get(django_user_id=request.user.pk), action=action, query=query[:96],
        target_user_id=target_user_id, outcome=outcome,
    )


def serialize_reception_profile(profile: Profile, projection, client_code=None) -> dict:
    """Ley 21.719 proportionality: only what reception needs. No email, phone, RUT or results."""
    user = profile.user
    return {
        "user_id": user.id,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "client_code": client_code,
        "service_status": projection.service_status if projection else ClientStatus.NO_PURCHASED,
        "service_request_status": projection.request_status if projection else None,
        "service_samples": [
            {field: getattr(sample, field) for field in (
                'sample_code', 'sample_type', 'status', 'collected_at', 'created_at',
            )} for sample in projection.service_samples
        ] if projection else [],
    }


class ReceptionSearchAPIView(APIView):
    """Busca un cliente solo por su Sample ID (código de cliente o de muestra). Solo recepción/admin."""
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not has_reception_access(request.user):
            return Response({"error": "No tienes permisos"}, status=status.HTTP_403_FORBIDDEN)
        code = (request.query_params.get("sample_code") or "").strip()
        if not code:
            return Response({"error": "Debes enviar sample_code"}, status=status.HTTP_400_BAD_REQUEST)

        client_codes = dict(Participant.objects.filter(participant_code__iexact=code)
                            .values_list('user_id', 'participant_code'))
        sample_owners = Sample.objects.filter(sample_code__iexact=code).values_list(
            'service_request__purchase__owner__django_user_id', flat=True,
        )
        profiles = list(Profile.objects.select_related("user").filter(
            Q(user_id__in=client_codes) | Q(user_id__in=sample_owners),
            user__is_active=True, user__app_user__role__code=Role.Code.CLIENTE,
        ))
        projections = get_service_projections((profile.user_id for profile in profiles), include_samples=True)
        normalized = code.casefold()
        # A Sample hit only counts when it belongs to the client's newest valid paid service.
        profiles = [
            profile for profile in profiles
            if profile.user_id in client_codes or profile.user_id in projections and any(
                sample.sample_code.casefold() == normalized
                for sample in projections[profile.user_id].service_samples
            )
        ]
        _log(request, ReceptionAccessLog.Action.SEARCH, query=code,
             target_user_id=profiles[0].user_id if len(profiles) == 1 else None,
             outcome=f'{len(profiles)} result(s)')
        codes = dict(Participant.objects.filter(user_id__in=[p.user_id for p in profiles])
                     .values_list('user_id', 'participant_code'))
        return Response({"results": [
            serialize_reception_profile(profile, projections.get(profile.user_id), codes.get(profile.user_id))
            for profile in profiles
        ]})


def _normalize_rut(value):
    return re.sub(r'[.\s]', '', str(value or '')).upper()


class ReceptionVerifyRutAPIView(CSRFDoubleSubmitMixin, APIView):
    """Answers only whether the RUT typed from the ID card matches; the stored RUT is never returned."""
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    throttle_scope = 'reception_rut'

    def post(self, request):
        if not has_reception_access(request.user):
            return Response({"error": "No tienes permisos"}, status=status.HTTP_403_FORBIDDEN)
        user_id, rut = request.data.get('userId'), _normalize_rut(request.data.get('rut'))
        if type(user_id) is not int or user_id <= 0 or not re.fullmatch(r'\d{7,8}-[\dK]', rut):
            return Response({"error": "userId y un RUT con formato 12345678-K son obligatorios"},
                            status=status.HTTP_400_BAD_REQUEST)
        profile = Profile.objects.filter(
            user_id=user_id, user__is_active=True, user__app_user__role__code=Role.Code.CLIENTE,
        ).first()
        if profile is None:
            return Response({"error": "Cliente no encontrado"}, status=status.HTTP_404_NOT_FOUND)
        matches = bool(profile.rut) and _normalize_rut(profile.rut) == rut
        _log(request, ReceptionAccessLog.Action.VERIFY_RUT, target_user_id=user_id,
             outcome='match' if matches else 'no_match')
        return Response({"matches": matches})
