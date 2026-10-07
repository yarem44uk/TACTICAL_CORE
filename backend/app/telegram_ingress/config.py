"""WO-083 — Telegram ingress configuration.

Configuration follows the repository's existing env convention (ADR-010,
``backend/.env.example``, the WO-080 WhatsApp ingress, and the operator
entrypoint): values are read from the process environment and are NEVER logged.

Credential boundary (WO-082 GATE G / WO-083 §9):

    Telegram webhook secret (``secret_token``)
        -> ingress process ONLY (``X-Telegram-Bot-Api-Secret-Token``)
    Bot token
        -> NOT required for inbound webhook ingestion (out of scope)

Telegram's webhook secret is a STATIC SHARED SECRET sent by Telegram in the
``X-Telegram-Bot-Api-Secret-Token`` header.  It is deliberately NOT an HMAC body
signature (that is the WhatsApp/Meta mechanism): Telegram does not sign the
request body.  See :mod:`app.telegram_ingress.secret`.

No vault, no external secret manager, no database secret storage, and no custom
secret platform is introduced.  A missing REQUIRED value fails closed at startup
rather than starting an unauthenticated or non-durable ingress.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping, Optional

# Environment variable names (mirrors the WO-080 ingress convention).
SECRET_TOKEN_ENV = "TELEGRAM_WEBHOOK_SECRET"
HOST_ENV = "TELEGRAM_HOST"
PORT_ENV = "TELEGRAM_PORT"
WEBHOOK_PATH_ENV = "TELEGRAM_WEBHOOK_PATH"
DATABASE_URL_ENV = "DATABASE_URL"

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8030
DEFAULT_WEBHOOK_PATH = "/telegram/webhook"

# Conservative body ceiling for the public endpoint (bytes).  The webhook is
# metadata/reference-only (media is reference-only too), so a small ceiling is
# sufficient and bounds the untrusted surface (WO-083 §23).  Telegram never
# sends media bytes in an Update.
DEFAULT_MAX_BODY_BYTES = 1024 * 1024  # 1 MiB


class TelegramIngressConfigError(Exception):
    """Raised when the ingress configuration is missing or invalid (fail-closed)."""


@dataclass(frozen=True)
class TelegramIngressConfig:
    """Resolved Telegram ingress configuration (never contains log output)."""

    secret_token: str
    webhook_path: str
    host: str
    port: int
    database_url: str
    max_body_bytes: int = DEFAULT_MAX_BODY_BYTES

    def __repr__(self) -> str:  # pragma: no cover - defensive masking
        return (
            "TelegramIngressConfig("
            f"secret_token=<redacted:{bool(self.secret_token)}>, "
            f"webhook_path={self.webhook_path!r}, host={self.host!r}, "
            f"port={self.port}, database_url=<redacted>, "
            f"max_body_bytes={self.max_body_bytes})"
        )

    @classmethod
    def from_env(
        cls, env: Optional[Mapping[str, str]] = None
    ) -> "TelegramIngressConfig":
        """Build the configuration from the environment, failing closed.

        Raises:
            TelegramIngressConfigError: If a required value (webhook secret,
                DATABASE_URL) is missing/empty, or the port is not an integer.
                The error message never contains a secret value.
        """
        source = os.environ if env is None else env

        secret_token = (source.get(SECRET_TOKEN_ENV) or "").strip()
        if not secret_token:
            raise TelegramIngressConfigError(
                f"{SECRET_TOKEN_ENV} is required (Telegram webhook "
                "secret_token) and is not configured; refusing to start "
                "without secret-token verification."
            )

        database_url = (source.get(DATABASE_URL_ENV) or "").strip()
        if not database_url:
            raise TelegramIngressConfigError(
                f"{DATABASE_URL_ENV} is required: commit-before-ACK requires the "
                "canonical durable store; refusing to start without it."
            )

        host = (source.get(HOST_ENV) or DEFAULT_HOST).strip() or DEFAULT_HOST
        raw_port = (source.get(PORT_ENV) or str(DEFAULT_PORT)).strip()
        try:
            port = int(raw_port)
        except (TypeError, ValueError):
            raise TelegramIngressConfigError(
                f"{PORT_ENV} must be an integer"
            ) from None

        webhook_path = (source.get(WEBHOOK_PATH_ENV) or DEFAULT_WEBHOOK_PATH).strip()
        if not webhook_path.startswith("/"):
            webhook_path = "/" + webhook_path

        return cls(
            secret_token=secret_token,
            webhook_path=webhook_path,
            host=host,
            port=port,
            database_url=database_url,
        )
