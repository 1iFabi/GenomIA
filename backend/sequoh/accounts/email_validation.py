"""Email normalization, syntax validation, and bounded MX validation."""

from dataclasses import dataclass
import ipaddress
import unicodedata

try:
    import dns.exception
    import dns.resolver
except ModuleNotFoundError:  # Keep Django startup-safe until dependencies are installed.
    dns = None

from django.conf import settings
from django.core.validators import validate_email
from django.core.exceptions import ValidationError


REGISTRATION_EMAIL_ERROR = "El correo no es válido."


@dataclass(frozen=True)
class EmailValidationResult:
    """Structured result used by public registration endpoints."""

    valid: bool
    normalized_email: str | None = None
    domain: str | None = None
    error_code: str | None = None
    error: str | None = None

    def as_api_error(self) -> dict[str, str]:
        return {"error": REGISTRATION_EMAIL_ERROR}


_NAME_SEPARATORS = frozenset({" ", "'", "\u2019", "-"})


def is_valid_registration_name(raw_name: str) -> bool:
    """Accept letters separated only by spaces, apostrophes, or hyphens."""
    if not isinstance(raw_name, str):
        return False

    value = unicodedata.normalize("NFC", raw_name).strip()
    if not value or value[0] in _NAME_SEPARATORS or value[-1] in _NAME_SEPARATORS:
        return False

    previous_was_separator = False
    has_letter = False
    for character in value:
        category = unicodedata.category(character)
        if character.isalpha():
            has_letter = True
            previous_was_separator = False
        elif category.startswith("M") and has_letter and not previous_was_separator:
            previous_was_separator = False
        elif character in _NAME_SEPARATORS and not previous_was_separator:
            previous_was_separator = True
        else:
            return False

    return has_letter and not previous_was_separator


def normalize_email_domain(raw_domain: str) -> str:
    """Normalize a domain for exact, case-insensitive IDNA comparisons."""
    if not isinstance(raw_domain, str):
        raise ValueError(REGISTRATION_EMAIL_ERROR)

    domain = raw_domain.strip().rstrip(".")
    if not domain:
        raise ValueError(REGISTRATION_EMAIL_ERROR)

    try:
        return domain.encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise ValueError(REGISTRATION_EMAIL_ERROR) from exc


def _configured_email_domains(setting_name: str) -> frozenset[str]:
    """Read and normalize a server-only domain setting for exact matching."""
    configured = getattr(settings, setting_name, "")
    values = configured.split(",") if isinstance(configured, str) else configured
    if not values:
        return frozenset()

    try:
        values = iter(values)
    except TypeError:
        return frozenset()

    normalized_domains = set()
    for value in values:
        try:
            normalized_domain = normalize_email_domain(value)
            validate_email(f"config@{normalized_domain}")
            normalized_domains.add(normalized_domain)
        except (TypeError, UnicodeError, ValueError, ValidationError):
            # Ignore malformed deployment configuration instead of weakening validation.
            continue
    return frozenset(normalized_domains)


def configured_blocked_email_domains() -> frozenset[str]:
    """Read and normalize the server-only blocked-domain setting."""
    return _configured_email_domains("BLOCKED_EMAIL_DOMAINS")


def configured_allowed_email_domains() -> frozenset[str]:
    """Read and normalize the server-only allowlist for exact domain matching."""
    return _configured_email_domains("ALLOWED_EMAIL_DOMAINS")


def normalize_email_address(raw_email: str) -> str:
    """Normalize an email using the application's case-insensitive convention."""
    if not isinstance(raw_email, str):
        raise ValueError("El correo electrónico no es válido.")

    value = raw_email.strip()
    local_part, separator, raw_domain = value.rpartition("@")
    if not separator or not local_part or not raw_domain:
        raise ValueError("El formato del correo electrónico no es válido.")

    # A trailing DNS root dot is equivalent, but other empty labels are not.
    ascii_domain = normalize_email_domain(raw_domain)

    # Registration has historically treated email addresses case-insensitively.
    normalized = f"{local_part.lower()}@{ascii_domain}"
    try:
        validate_email(normalized)
    except ValidationError as exc:
        raise ValueError("El formato del correo electrónico no es válido.") from exc
    return normalized


def _dns_timeout_seconds() -> float:
    configured = getattr(settings, "EMAIL_VALIDATION_DNS_TIMEOUT_SECONDS", 3.0)
    try:
        configured = float(configured)
    except (TypeError, ValueError):
        configured = 3.0
    # Keep a deployment setting from turning an API request into an unbounded wait.
    return max(0.1, min(configured, 10.0))


def _dns_fallback_nameservers() -> tuple[str, ...]:
    """Return valid configured IP nameservers, or an empty tuple when disabled."""
    configured = getattr(
        settings,
        "EMAIL_VALIDATION_DNS_FALLBACK_NAMESERVERS",
        "1.1.1.1,8.8.8.8",
    )
    if not isinstance(configured, str):
        return ()

    nameservers = []
    for raw_nameserver in configured.split(","):
        nameserver = raw_nameserver.strip()
        if not nameserver:
            continue
        try:
            ipaddress.ip_address(nameserver)
        except ValueError:
            continue
        nameservers.append(nameserver)
    return tuple(nameservers)


def _usable_mx_answers(answers) -> bool:
    for answer in answers:
        exchange = getattr(answer, "exchange", None)
        if exchange is None:
            continue
        exchange_text = exchange.to_text() if hasattr(exchange, "to_text") else str(exchange)
        if exchange_text.rstrip("."):
            return True
    return False


def _has_usable_mx(domain: str) -> tuple[bool, str | None, str | None]:
    if dns is None:
        return False, "dns_dependency_missing", "La validación del dominio no está disponible en este entorno."

    timeout = _dns_timeout_seconds()
    try:
        answers = dns.resolver.resolve(domain, "MX", lifetime=timeout)
    except (dns.resolver.LifetimeTimeout, dns.exception.Timeout):
        return False, "dns_timeout", "No se pudo comprobar el dominio a tiempo. Inténtalo nuevamente."
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.resolver.NoNameservers):
        # Only these system-resolver failures are eligible for the bounded fallback.
        nameservers = _dns_fallback_nameservers()
        if not nameservers:
            return False, "no_mx", "El dominio del correo no tiene registros MX utilizables."
        try:
            fallback_resolver = dns.resolver.Resolver(configure=False)
            fallback_resolver.nameservers = list(nameservers)
            answers = fallback_resolver.resolve(domain, "MX", lifetime=timeout)
        except (dns.resolver.LifetimeTimeout, dns.exception.Timeout):
            return False, "dns_timeout", "No se pudo comprobar el dominio a tiempo. Inténtalo nuevamente."
        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.resolver.NoNameservers):
            return False, "no_mx", "El dominio del correo no tiene registros MX utilizables."
        except dns.exception.DNSException:
            return False, "dns_error", "No se pudo comprobar el dominio del correo. Inténtalo nuevamente."
        except Exception:
            # Fail closed if a fallback resolver implementation raises unexpectedly.
            return False, "dns_error", "No se pudo comprobar el dominio del correo. Inténtalo nuevamente."
    except dns.exception.DNSException:
        return False, "dns_error", "No se pudo comprobar el dominio del correo. Inténtalo nuevamente."
    except Exception:
        # Fail closed if a resolver implementation raises an unexpected lookup error.
        return False, "dns_error", "No se pudo comprobar el dominio del correo. Inténtalo nuevamente."

    if _usable_mx_answers(answers):
        return True, None, None
    return False, "no_mx", "El dominio del correo no tiene registros MX utilizables."


def validate_registration_email(raw_email: str, *, check_mx: bool = True) -> EmailValidationResult:
    """Return a clear validation result without exposing DNS implementation details."""
    try:
        normalized_email = normalize_email_address(raw_email)
    except ValueError as exc:
        return EmailValidationResult(
            valid=False,
            error_code="invalid_syntax",
            error=str(exc),
        )

    domain = normalized_email.rsplit("@", 1)[1]
    if domain in configured_blocked_email_domains():
        return EmailValidationResult(
            valid=False,
            normalized_email=normalized_email,
            domain=domain,
            error_code="blocked_domain",
            error=REGISTRATION_EMAIL_ERROR,
        )

    allowed_domains = configured_allowed_email_domains()
    if allowed_domains and domain not in allowed_domains:
        return EmailValidationResult(
            valid=False,
            normalized_email=normalized_email,
            domain=domain,
            error_code="domain_not_allowed",
            error=REGISTRATION_EMAIL_ERROR,
        )

    if check_mx:
        has_mx, error_code, error = _has_usable_mx(domain)
        if not has_mx:
            return EmailValidationResult(
                valid=False,
                normalized_email=normalized_email,
                domain=domain,
                error_code=error_code,
                error=error,
            )

    return EmailValidationResult(
        valid=True,
        normalized_email=normalized_email,
        domain=domain,
    )
