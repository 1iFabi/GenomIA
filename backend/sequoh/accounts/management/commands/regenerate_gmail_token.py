"""
Management command para generar/regenerar config/token.json de la API de Gmail.

Reutiliza las rutas de settings (GMAIL_CREDENTIALS_FILE / GMAIL_TOKEN_FILE)
y los SCOPES definidos en autenticacion.email_utils, para no duplicar lógica.

Uso:
    python manage.py regenerate_gmail_token          # genera/refresca si hace falta
    python manage.py regenerate_gmail_token --force  # reautoriza aunque el token sea valido
    python manage.py regenerate_gmail_token --credentials /ruta/credenciales.json --token /ruta/token.json
"""

from __future__ import annotations

import os

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from accounts.email_utils import SCOPES


class Command(BaseCommand):
    """Genera o regenera token.json ejecutando el flujo OAuth de Gmail."""

    help = (
        "Genera/regenera config/token.json ejecutando el flujo OAuth de Gmail. "
        "Usa --force para reautorizar aunque el token actual siga valido."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Fuerza la reautorizacion (ignora un token actual valido).",
        )
        parser.add_argument(
            "--credentials",
            default=None,
            help="Ruta al credentials.json (por defecto usa settings.GMAIL_CREDENTIALS_FILE).",
        )
        parser.add_argument(
            "--token",
            default=None,
            help="Ruta al token.json a escribir (por defecto usa settings.GMAIL_TOKEN_FILE).",
        )

    def handle(self, *args, **options):
        force = options["force"]
        cred_path = options["credentials"] or settings.GMAIL_CREDENTIALS_FILE
        token_path = options["token"] or settings.GMAIL_TOKEN_FILE

        if not os.path.exists(cred_path):
            raise CommandError(
                f"No se encontro credentials.json en: {cred_path}. "
                "Crea un ID de cliente OAuth (Aplicacion de escritorio) y colocalo ahi "
                "o pasa --credentials con la ruta correcta."
            )

        creds = None
        if os.path.exists(token_path):
            try:
                creds = Credentials.from_authorized_user_file(token_path, SCOPES)
                self.stdout.write(f"Token cargado desde {token_path}")
            except Exception as e:  # noqa: BLE001
                self.stderr.write(f"No se pudo leer el token existente: {e}")
                creds = None

        # Si el token ya es valido y no se pidio forzar, no hacemos nada.
        if creds and creds.valid and not force:
            self.stdout.write(
                self.style.SUCCESS(
                    "El token actual sigue siendo valido. Usa --force para reautorizar."
                )
            )
            return

        # Si esta expirado pero conserva refresh_token, intentamos refrescar primero.
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                self._save_token(creds, token_path)
                self.stdout.write(self.style.SUCCESS("Token refrescado y guardado."))
                return
            except Exception as e:  # noqa: BLE001
                self.stderr.write(
                    "No se pudo refrescar el token (suele vencer a los 7 dias en modo "
                    f"Pruebas de la pantalla de consentimiento): {e}"
                )
                creds = None

        # Flujo interactivo: abre el navegador para que el usuario autorice el acceso.
        self.stdout.write("Abriendo el navegador para autorizar el acceso a Gmail...")
        try:
            from google_auth_oauthlib.flow import InstalledAppFlow

            flow = InstalledAppFlow.from_client_secrets_file(cred_path, SCOPES)
            creds = flow.run_local_server(port=0)
        except Exception as e:  # noqa: BLE001
            raise CommandError(f"Fallo el flujo OAuth: {e}")

        self._save_token(creds, token_path)
        self.stdout.write(self.style.SUCCESS("token.json generado correctamente."))

    def _save_token(self, creds: Credentials, token_path: str) -> None:
        os.makedirs(os.path.dirname(token_path), exist_ok=True)
        with open(token_path, "w", encoding="utf-8") as f:
            f.write(creds.to_json())
