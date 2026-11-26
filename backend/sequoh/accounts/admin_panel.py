"""Read-only API for the admin panel: overview counts and the activity trail.

Admin only. Names and emails are shown to the admin by product decision; RUT, phone, IP, what reception
typed and genetic results never leave the server (Ley 21.719).
"""
from django.contrib.auth.models import User
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from participants.models import Participant
from reception.models import ReceptionAccessLog
from services.models import Purchase, ServiceStatusLog
from services.status import get_service_projections

from .authentication import JWTAuthentication
from .models import AppUser, GeneticDataAccessLog, Role
from .roles import is_admin

STAGES = ('WAITING_SAMPLE', 'SAMPLE_RECEIVED', 'PROCESSING', 'COMPLETED')
STAFF = (Role.Code.ADMIN, Role.Code.ANALISTA, Role.Code.RECEPCION)


class AdminOnlyView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        self.forbidden = not is_admin(request.user)

    @staticmethod
    def fresh(payload, code=status.HTTP_200_OK):
        response = Response(payload, status=code)
        response['Cache-Control'] = 'no-store'
        return response


def _active_client_ids():
    return list(User.objects.filter(is_active=True, app_user__role__code=Role.Code.CLIENTE)
                .values_list('id', flat=True))


class AdminOverviewAPIView(AdminOnlyView):
    """Headline counts, services per stage (with the oldest one still waiting) and staff per role."""

    def get(self, request):
        if self.forbidden:
            return Response({"error": "No tienes permisos"}, status=status.HTTP_403_FORBIDDEN)
        now = timezone.now()
        client_ids = _active_client_ids()
        # Same projection as the stats and the analyst view, so a malformed service is left out everywhere.
        services = [p for p in get_service_projections(client_ids).values() if p.request_status in STAGES]
        stages = []
        for code in STAGES:
            here = [p for p in services if p.request_status == code]
            oldest = min((p.updated_at for p in here if p.updated_at), default=None)
            stages.append({
                "code": code,
                "count": len(here),
                "oldest_days": None if code == 'COMPLETED' or oldest is None else (now - oldest).days,
            })
        staff = dict.fromkeys(STAFF, 0)
        for code in AppUser.objects.filter(role__code__in=STAFF, django_user__is_active=True).values_list(
                'role__code', flat=True):
            staff[code] += 1
        completed = stages[-1]["count"]
        return self.fresh({
            "clients": len(client_ids),
            "purchases_pending": Purchase.objects.filter(
                status__code='PENDING', owner__django_user_id__in=client_ids).count(),
            "services_open": len(services) - completed,
            "services_completed": completed,
            "stages": stages,
            "staff": staff,
            "generated_at": now.isoformat(),
        })


PAGE = 50
KINDS = ('genetic', 'reception', 'status')
DELETED = "Cuenta eliminada"


def _matching_user_ids(text):
    return list(User.objects.filter(
        Q(email__icontains=text) | Q(first_name__icontains=text) | Q(last_name__icontains=text)
        | Q(username__icontains=text)
    ).values_list('id', flat=True))


def _people(user_ids):
    """One query per table: id -> person dict, for actors and subjects alike."""
    ids = {pk for pk in user_ids if pk is not None}
    users = {u['id']: u for u in User.objects.filter(id__in=ids).values(
        'id', 'username', 'email', 'first_name', 'last_name')}
    roles = dict(AppUser.objects.filter(django_user_id__in=ids).values_list('django_user_id', 'role__code'))
    codes = dict(Participant.objects.filter(user_id__in=ids).values_list('user_id', 'participant_code'))
    people = {}
    for pk in ids:
        user = users.get(pk)
        if user is None:
            people[pk] = {"id": pk, "name": DELETED, "email": None, "role": None, "sample_code": None}
            continue
        name = f"{user['first_name']} {user['last_name']}".strip() or user['username']
        people[pk] = {"id": pk, "name": name, "email": user['email'], "role": roles.get(pk),
                      "sample_code": codes.get(pk)}
    return people


class AdminActivityAPIView(AdminOnlyView):
    """Who touched which data: genetic result reads, reception look-ups and service status changes, newest first.

    Never returns IP, the text reception typed, RUT or results.
    shortcut: the cursor is a timestamp, so events sharing the exact boundary instant can be skipped;
    move to a (time, id) cursor if that ever matters.
    """

    def get(self, request):
        if self.forbidden:
            return Response({"error": "No tienes permisos"}, status=status.HTTP_403_FORBIDDEN)
        kind = request.query_params.get('kind') or None
        if kind is not None and kind not in KINDS:
            return Response({"error": "Tipo de evento inválido."}, status=status.HTTP_400_BAD_REQUEST)
        before = None
        if request.query_params.get('before'):
            before = parse_datetime(request.query_params['before'])
            if before is None:
                return Response({"error": "Fecha 'before' inválida."}, status=status.HTTP_400_BAD_REQUEST)
        text = (request.query_params.get('q') or '').strip()
        ids = _matching_user_ids(text) if text else None

        rows = []  # (at, kind, pk, actor_id, subject_id, action, outcome)
        if kind in (None, 'genetic'):
            logs = GeneticDataAccessLog.objects.all()
            if before:
                logs = logs.filter(created_at__lt=before)
            if ids is not None:
                logs = logs.filter(Q(actor_user_id__in=ids) | Q(subject_user_id__in=ids))
            rows += [(at, 'genetic', pk, actor, subject, resource, outcome) for at, pk, actor, subject, resource, outcome
                     in logs.order_by('-created_at', '-pk').values_list(
                         'created_at', 'pk', 'actor_user_id', 'subject_user_id', 'resource', 'outcome')[:PAGE]]
        if kind in (None, 'reception'):
            logs = ReceptionAccessLog.objects.all()
            if before:
                logs = logs.filter(created_at__lt=before)
            if ids is not None:
                logs = logs.filter(Q(actor__django_user_id__in=ids) | Q(target_user_id__in=ids))
            rows += [(at, 'reception', pk, actor, subject, action, outcome) for at, pk, actor, subject, action, outcome
                     in logs.order_by('-created_at', '-pk').values_list(
                         'created_at', 'pk', 'actor__django_user_id', 'target_user_id', 'action', 'outcome')[:PAGE]]
        if kind in (None, 'status'):
            logs = ServiceStatusLog.objects.all()
            if before:
                logs = logs.filter(changed_at__lt=before)
            if ids is not None:
                logs = logs.filter(Q(actor__django_user_id__in=ids)
                                   | Q(request__purchase__owner__django_user_id__in=ids))
            rows += [(at, 'status', pk, actor, subject, code, None) for at, pk, actor, subject, code
                     in logs.order_by('-changed_at', '-pk').values_list(
                         'changed_at', 'pk', 'actor__django_user_id', 'request__purchase__owner__django_user_id',
                         'status__code')[:PAGE]]

        rows.sort(key=lambda row: row[0], reverse=True)
        rows = rows[:PAGE]
        people = _people([row[3] for row in rows] + [row[4] for row in rows])
        events = []
        for at, event_kind, pk, actor_id, subject_id, action, outcome in rows:
            actor = dict(people[actor_id])
            actor.pop('sample_code')
            subject = None
            if subject_id is not None:
                subject = dict(people[subject_id])
                subject.pop('role')
            events.append({"id": f"{event_kind}:{pk}", "kind": event_kind, "at": at.isoformat(), "actor": actor,
                           "subject": subject, "action": action, "outcome": outcome})
        return self.fresh({
            "events": events,
            "next_before": rows[-1][0].isoformat() if len(rows) == PAGE else None,
        })
