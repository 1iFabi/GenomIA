import uuid
from datetime import datetime, timedelta, timezone

import jwt
from django.conf import settings


def _algorithm() -> str:
    return getattr(settings, "JWT_ALGORITHM", "HS256")


def _issuer() -> str:
    return getattr(settings, "JWT_ISSUER", "genomia")


def _audience() -> str:
    return getattr(settings, "JWT_AUDIENCE", "genomia-app")


def _default_ttl_seconds() -> int:
    hours = getattr(settings, "JWT_EXPIRATION_HOURS", 8)
    return int(hours) * 3600


def encode_jwt(payload: dict, ttl_seconds: int | None = None) -> str:
    """
    Emite un JWT firmado con PyJWT.

    Agrega iat/exp/iss/aud/jti si no vienen en el payload. Devuelve un str
    (PyJWT >= 2.x ya retorna str).
    """
    now = datetime.now(timezone.utc)
    ttl = ttl_seconds if ttl_seconds is not None else _default_ttl_seconds()

    payload.setdefault("iat", now)
    payload.setdefault("exp", now + timedelta(seconds=ttl))
    payload.setdefault("iss", _issuer())
    payload.setdefault("aud", _audience())
    payload.setdefault("jti", str(uuid.uuid4()))

    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=_algorithm())


def decode_jwt(token: str) -> dict:
    """
    Decodifica y valida un JWT.

    Valida firma y exp, y exige las claims iat/exp/iss/aud. Lanza
    jwt.exceptions.PyJWTError si el token es inválido o expiró.
    """
    return jwt.decode(
        token,
        settings.JWT_SECRET_KEY,
        algorithms=[_algorithm()],
        issuer=_issuer(),
        audience=_audience(),
        options={"require": ["iat", "exp", "iss", "aud"]},
    )
