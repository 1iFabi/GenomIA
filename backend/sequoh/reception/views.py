import json
import uuid
from django.db.models import Q
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from accounts.authentication import JWTAuthentication
from profiles.models import Profile, SampleStatus, ServiceStatus
from accounts.roles import is_admin, is_reception
from profiles.utils import ensure_sample_code
from accounts.email_utils import send_email, build_branded_html


def has_reception_access(user) -> bool:
    """Devuelve True si el usuario puede operar en recepciИn (admin o recepciИn)."""
    return is_admin(user) or is_reception(user)


def serialize_reception_profile(profile: Profile) -> dict:
    """Serializa datos permitidos para recepción (sin genéticos)."""
    user = profile.user
    sample_code = profile.sample_code or ensure_sample_code(profile)
    sample_status = profile.sample_status or SampleStatus.PENDING_COLLECTION

    return {
        "user_id": user.id,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "email": user.email,
        "phone": profile.phone,
        "rut": profile.rut,
        "sample_code": sample_code,
        "sample_status": sample_status,
        "sample_status_display": SampleStatus(sample_status).label if sample_status else "",
        "arrival_confirmed_at": profile.arrival_confirmed_at,
        "sample_taken_at": profile.sample_taken_at,
        "sample_sent_at": profile.sample_sent_at,
        "service_status": profile.service_status,
    }


class ReceptionSearchAPIView(APIView):
    """Busca usuarios por RUT, correo o SampleCode. Solo recepción/admin."""
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not has_reception_access(request.user):
            return Response({"error": "No tienes permisos"}, status=status.HTTP_403_FORBIDDEN)

        rut = (request.query_params.get("rut") or "").strip()
        email = (request.query_params.get("email") or "").strip()
        sample_code = (request.query_params.get("sample_code") or "").strip()
        query = rut or email or sample_code
        if not query:
            return Response({"error": "Debes enviar rut, email o sample_code"}, status=status.HTTP_400_BAD_REQUEST)

        qs = Profile.objects.select_related("user").filter(user__is_active=True, user__is_superuser=False)
        qs = qs.exclude(user__groups__name__in=["ADMIN", "ANALISTA"])

        if rut:
            qs = qs.filter(rut__iexact=rut)
        if email:
            qs = qs.filter(Q(user__email__iexact=email) | Q(user__username__iexact=email))
        if sample_code:
            qs = qs.filter(sample_code__iexact=sample_code)

        results = [serialize_reception_profile(p) for p in qs[:25]]
        return Response({"results": results})


class ReceptionArrivalAPIView(APIView):
    """Marca llegada presencial del usuario."""
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not has_reception_access(request.user):
            return Response({"error": "No tienes permisos"}, status=status.HTTP_403_FORBIDDEN)
        try:
            data = json.loads(request.body or "{}")
        except json.JSONDecodeError:
            data = request.data or {}

        user_id = data.get("userId") or data.get("user_id")
        if not user_id:
            return Response({"error": "userId es obligatorio"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            profile = Profile.objects.select_related("user").get(user_id=user_id, user__is_active=True)
        except Profile.DoesNotExist:
            return Response({"error": "Usuario no encontrado"}, status=status.HTTP_404_NOT_FOUND)

        ensure_sample_code(profile)
        profile.arrival_confirmed_at = timezone.now()
        if not profile.sample_status:
            profile.sample_status = SampleStatus.PENDING_COLLECTION
        # Marcar el servicio como pendiente para que el analista lo vea
        if profile.service_status != ServiceStatus.COMPLETED:
            profile.service_status = ServiceStatus.PENDING
        profile.save(update_fields=["arrival_confirmed_at", "sample_status", "service_status"])

        return Response({"user": serialize_reception_profile(profile)})


class ReceptionSampleCodeAPIView(APIView):
    """Devuelve/genera SampleCode y permite reenviarlo al correo."""
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not has_reception_access(request.user):
            return Response({"error": "No tienes permisos"}, status=status.HTTP_403_FORBIDDEN)
        try:
            data = json.loads(request.body or "{}")
        except json.JSONDecodeError:
            data = request.data or {}

        user_id = data.get("userId") or data.get("user_id")
        resend = bool(data.get("resend"))
        if not user_id:
            return Response({"error": "userId es obligatorio"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            profile = Profile.objects.select_related("user").get(user_id=user_id, user__is_active=True)
        except Profile.DoesNotExist:
            return Response({"error": "Usuario no encontrado"}, status=status.HTTP_404_NOT_FOUND)

        code = ensure_sample_code(profile)
        payload = serialize_reception_profile(profile)

        # Marcar servicio como pendiente al generar/reenviar sample
        if profile.service_status != ServiceStatus.COMPLETED:
            profile.service_status = ServiceStatus.PENDING
            profile.save(update_fields=["service_status"])

        if resend:
            try:
                subject = "Tu SampleCode para etiquetar la muestra"
                text_body = (
                    f"Hola {profile.user.first_name},\n\n"
                    f"Este es tu SampleCode para la toma de muestra: {code}\n"
                    "Úsalo solo para etiquetar la muestra en recepción. No contiene resultados genéticos.\n\n"
                    "Equipo GenomIA."
                )
                html_body = build_branded_html(
                    f"""
                    <p>Hola {profile.user.first_name},</p>
                    <p>Este es tu <strong>SampleCode</strong> para la toma de muestra:</p>
                    <p style="font-size: 20px; font-weight: 700; letter-spacing: 0.8px;">{code}</p>
                    <p>Se usa únicamente para etiquetar la muestra en recepción. No contiene resultados genéticos.</p>
                    <p>Equipo GenomIA.</p>
                    """
                )
                send_email(
                    to_email=profile.user.email,
                    subject=subject,
                    html_body=html_body,
                    text_body=text_body,
                )
                payload["sample_code_sent"] = True
            except Exception as exc:  # pragma: no cover - defensivo
                payload["sample_code_sent"] = False
                payload["send_error"] = str(exc)

        return Response({"user": payload})


class ReceptionSampleStatusAPIView(APIView):
    """Actualiza el estado de la muestra (ej. tomada/pediente de análisis)."""
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not has_reception_access(request.user):
            return Response({"error": "No tienes permisos"}, status=status.HTTP_403_FORBIDDEN)
        try:
            data = json.loads(request.body or "{}")
        except json.JSONDecodeError:
            data = request.data or {}

        user_id = data.get("userId") or data.get("user_id")
        action = (data.get("action") or "mark_taken").strip().lower()
        if not user_id:
            return Response({"error": "userId es obligatorio"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            profile = Profile.objects.select_related("user").get(user_id=user_id, user__is_active=True)
        except Profile.DoesNotExist:
            return Response({"error": "Usuario no encontrado"}, status=status.HTTP_404_NOT_FOUND)

        ensure_sample_code(profile)

        if action in {"mark_taken", "taken"}:
            profile.sample_status = SampleStatus.COLLECTED_PENDING_ANALYSIS
            profile.sample_taken_at = timezone.now()
            update_fields = ["sample_status", "sample_taken_at"]
        elif action in {"sent_lab", "sent_to_lab"}:
            profile.sample_status = SampleStatus.SENT_TO_LAB
            profile.sample_sent_at = timezone.now()
            update_fields = ["sample_status", "sample_sent_at"]
        else:
            return Response({"error": "Acción no soportada"}, status=status.HTTP_400_BAD_REQUEST)

        profile.save(update_fields=update_fields)
        return Response({"user": serialize_reception_profile(profile)})
