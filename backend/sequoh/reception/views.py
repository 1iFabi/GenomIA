from django.db.models import Q
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from accounts.authentication import JWTAuthentication
from profiles.models import Profile
from accounts.models import Role
from accounts.roles import is_admin, is_reception
from services.models import Sample
from services.status import ClientStatus, get_service_projections


def has_reception_access(user) -> bool:
    """Devuelve True si el usuario puede operar en recepción (admin o recepción)."""
    return is_admin(user) or is_reception(user)


def serialize_reception_profile(profile: Profile, projection) -> dict:
    user = profile.user
    return {
        "user_id": user.id,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "email": user.email,
        "phone": profile.phone,
        "rut": profile.rut,
        "service_status": projection.service_status if projection else ClientStatus.NO_PURCHASED,
        "service_samples": [
            {field: getattr(sample, field) for field in (
                'sample_code', 'sample_type', 'status', 'collected_at', 'created_at',
            )} for sample in projection.service_samples
        ] if projection else [],
    }


class ReceptionSearchAPIView(APIView):
    """Busca clientes por RUT, correo o código de muestra. Solo recepción/admin."""
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not has_reception_access(request.user):
            return Response({"error": "No tienes permisos"}, status=status.HTTP_403_FORBIDDEN)

        rut = (request.query_params.get("rut") or "").strip()
        email = (request.query_params.get("email") or "").strip()
        sample_code = (request.query_params.get("sample_code") or "").strip()
        if not (rut or email or sample_code):
            return Response({"error": "Debes enviar rut, email o sample_code"}, status=status.HTTP_400_BAD_REQUEST)

        qs = Profile.objects.select_related("user").filter(
            user__is_active=True,
            user__app_user__role__code=Role.Code.CLIENTE,
        )
        if rut:
            qs = qs.filter(rut__iexact=rut)
        if email:
            qs = qs.filter(Q(user__email__iexact=email) | Q(user__username__iexact=email))
        if sample_code:
            qs = qs.filter(user_id__in=Sample.objects.filter(sample_code__iexact=sample_code).values_list(
                'service_request__purchase__owner__django_user_id', flat=True,
            ))

        profiles = list(qs if sample_code else qs[:25])
        projections = get_service_projections((profile.user_id for profile in profiles), include_samples=True)
        if sample_code:
            # A Sample hit only identifies a candidate; it must belong to the newest paid service.
            normalized_code = sample_code.casefold()
            profiles = [
                profile for profile in profiles
                if profile.user_id in projections and any(
                    sample.sample_code.casefold() == normalized_code
                    for sample in projections[profile.user_id].service_samples
                )
            ]
        return Response({"results": [
            serialize_reception_profile(profile, projections.get(profile.user_id)) for profile in profiles
        ]})
