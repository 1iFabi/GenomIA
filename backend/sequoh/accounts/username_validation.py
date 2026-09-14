"""Validation helpers for public registration usernames."""

import re


USERNAME_REQUIRED_ERROR = "El nombre de usuario es obligatorio."
USERNAME_INVALID_ERROR = (
    "El nombre de usuario debe tener entre 3 y 30 caracteres y solo puede "
    "contener letras, números, puntos, guiones bajos y guiones."
)

_USERNAME_PATTERN = re.compile(r"^[a-z0-9_.-]{3,30}$")


def normalize_registration_username(raw_username: object) -> str:
    """Trim and lowercase a username, then validate its public format."""
    if raw_username is None:
        raise ValueError(USERNAME_REQUIRED_ERROR)
    if not isinstance(raw_username, str):
        raise ValueError(USERNAME_INVALID_ERROR)

    username = raw_username.strip().lower()
    if not username:
        raise ValueError(USERNAME_REQUIRED_ERROR)
    if not _USERNAME_PATTERN.fullmatch(username):
        raise ValueError(USERNAME_INVALID_ERROR)
    return username
