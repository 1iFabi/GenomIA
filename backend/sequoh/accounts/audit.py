import logging

from .models import GeneticDataAccessLog

logger = logging.getLogger('genomia.audit')


def audit(event, request=None, **fields):
    """One line per security event for the log collector (OWASP logging, NIST SP 800-92).

    Only ids and enums: never emails, RUTs, tokens or results (Ley 21.719).
    """
    if request is not None:
        # shortcut: REMOTE_ADDR is the proxy behind a reverse proxy; read X-Forwarded-For once the proxy sets it.
        fields['ip'] = request.META.get('REMOTE_ADDR')
    logger.info('%s %s', event, ' '.join(f'{key}={value}' for key, value in fields.items()))


def record_genetic_access(request, resource, subject_user_id, outcome):
    """Keep a read of genetic results in the database (queryable trail) and in the audit log stream."""
    GeneticDataAccessLog.objects.create(
        actor_user_id=request.user.pk, subject_user_id=subject_user_id, resource=resource, outcome=outcome,
        ip=request.META.get('REMOTE_ADDR') or None,
    )
    audit('genetic_data_access', request, actor=request.user.pk, subject=subject_user_id,
          resource=resource, outcome=outcome)
