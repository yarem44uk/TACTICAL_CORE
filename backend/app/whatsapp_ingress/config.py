"""WO-080 — WhatsApp ingress configuration.

Configuration follows the repository's existing env convention (ADR-010,
``backend/.env.example``, and the operator entrypoint): values are read from the
process environment and are NEVER logged.

Credential boundary (ADR-015 §12):

    Meta App Secret     -> ingress process ONLY (X-Hub-Signature-256)
    Verify Token        -> ingress process ONLY (GET challenge)
    Access Token        -> NOT required for inbound ingestion (out of scope)

No vault, no external secret manager, no database secret storage, and no custom
secret platform is introduced.  A missing REQUIRED value fails closed at
startup rather than starting an unauthenticated or non-durable ingress.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping, Optional

# Environment variable names (the smallest additive mechanism; see WO-080 §15).
APP_SECRET_ENV = "WHATSAPP_APP_SECRET"
VERIFY_TOKEN_ENV = "WHATSAPP_VERIFY_TOKEN"
HOST_ENV = "WHATSAPP_HOST"
PORT_ENV = "WHATSAPP_PORT"
WEBHOOK_PATH_ENV = "WHATSAPP_WEBHOOK_PATH"
DATABASE_URL_ENV = "DATABASE_URL"

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8020
DEFAULT_WEBHOOK_PATH = "/webhook"

# Conservative body ceiling for the public endpoint (bytes).  The webhook is
# metadata/reference-only, so a small ceiling is sufficient and bounds the
# untrusted surface (ADR-015 §6).
DEFAULT_MAX_BODY_BYTES = 1024 * 1024  # 1 MiB


class WhatsAppIngressConfigError(Exception):
    """Raised when the ingress configuration is missing or invalid (fail-closed)."""


@dataclass(frozen=True)
class WhatsAppIngressConfig:
    """Resolved WhatsApp ingress configuration (never contains log output)."""

    app_secret: str
    verify_token: str
    webhook_path: str
    host: str
    port: int
    database_url: str
    max_body_bytes: int = DEFAULT_MAX_BODY_BYTES

    def __repr__(self) -> str:  # pragma: no cover - defensive masking
        return (
            "WhatsAppIngressConfig("
            f"app_secret=<redacted:{bool(self.app_secret)}>, "
            f"verify_token=<redacted:{bool(self.verify_token)}>, "
            f"webhook_path={self.webhook_path!r}, host={self.host!r}, "
            f"port={self.port}, database_url=<redacted>, "
            f"max_body_bytes={self.max_body_bytes})"
        )

    @classmethod
    def from_env(
        cls, env: Optional[Mapping[str, str]] = None
    ) -> "WhatsAppIngressConfig":
        """Build the configuration from the environment, failing closed.

        Raises:
            WhatsAppIngressConfigError: If a required value (App Secret, Verify
                Token, DATABASE_URL) is missing/empty, or the port is not an
                integer.  The error message never contains a secret value.
        """
        source = os.environ if env is None else env

        app_secret = (source.get(APP_SECRET_ENV) or "").strip()
        if not app_secret:
            raise WhatsAppIngressConfigError(
                f"{APP_SECRET_ENV} is required (Meta App Secret) and is not "
                "configured; refusing to start without signature verification."
            )

        verify_token = (source.get(VERIFY_TOKEN_ENV) or "").strip()
        if not verify_token:
            raise WhatsAppIngressConfigError(
                f"{VERIFY_TOKEN_ENV} is required (Meta webhook Verify Token) "
                "and is not configured; refusing to start."
            )

        database_url = (source.get(DATABASE_URL_ENV) or "").strip()
        if not database_url:
            raise WhatsAppIngressConfigError(
                f"{DATABASE_URL_ENV} is required: commit-before-ACK requires the "
                "canonical durable store; refusing to start without it."
            )

        host = (source.get(HOST_ENV) or DEFAULT_HOST).strip() or DEFAULT_HOST
        raw_port = (source.get(PORT_ENV) or str(DEFAULT_PORT)).strip()
        try:
            port = int(raw_port)
        except (TypeError, ValueError):
            raise WhatsAppIngressConfigError(
                f"{PORT_ENV} must be an integer"
            ) from None

        webhook_path = (source.get(WEBHOOK_PATH_ENV) or DEFAULT_WEBHOOK_PATH).strip()
        if not webhook_path.startswith("/"):
            webhook_path = "/" + webhook_path

        return cls(
            app_secret=app_secret,
            verify_token=verify_token,
            webhook_path=webhook_path,
            host=host,
            port=port,
            database_url=database_url,
        )
