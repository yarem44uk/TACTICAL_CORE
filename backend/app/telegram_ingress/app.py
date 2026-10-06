"""WO-083 — Telegram ingress HTTP application factory.

Constructs the SEPARATE Telegram webhook ingress application for the Telegram
Bot API webhook model (``setWebhook``).  This application is:

  * NOT ``backend/main.py`` (it never starts the durable-core source catalogue);
  * NOT the operator read-only application (the operator API stays off the
    ingestion path);
  * a thin transport boundary: it verifies
    ``X-Telegram-Bot-Api-Secret-Token``, decodes JSON, and hands the Update to
    :class:`~app.telegram_ingress.service.TelegramIngressService`.

Routes:
    POST <webhook_path>   Inbound Telegram Update (secret token verified)
    GET  /healthz         ingress process health (read-only)

FRAMEWORK NOTE (WO-083 §10) — the WO text states the project "uses Flask".  That
premise is factually incorrect for this repository and is therefore resolved on
repository evidence, which is exactly the escalation the WO provides for:

  1. FastAPI is ALREADY an accepted runtime pattern: it runs the accepted
     read-only operator process (ADR-011 / ``app/operator/app.py``) AND the
     accepted WO-080 WhatsApp ingress (``app/whatsapp_ingress/app.py``);
  2. the dependency is already declared/available
     (``backend/requirements.txt``: ``fastapi>=0.141.0,<0.142``,
     ``uvicorn>=0.52.0,<0.53``);
  3. introducing Flask WOULD create the unnecessary second HTTP framework —
     and a new dependency (WO-083 §33 forbids adding one for convenience);
  4. runtime/deployment integration (separate uvicorn process) is already
     established by the WhatsApp ingress entrypoint.

There is no Flask reference anywhere in the repository.  FastAPI is therefore
the existing pattern, not a convenience choice.

Security notes:
  * the webhook secret is compared with a constant-time comparison and is never
    logged;
  * the raw request body is never logged at production verbosity (it contains
    message content).
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .config import DEFAULT_MAX_BODY_BYTES, TelegramIngressConfig
from .secret import SECRET_HEADER, verify_secret_token
from .service import TelegramIngressService

logger = logging.getLogger(__name__)


def create_telegram_ingress_app(
    *,
    service: TelegramIngressService,
    secret_token: str,
    webhook_path: str = "/telegram/webhook",
    max_body_bytes: int = DEFAULT_MAX_BODY_BYTES,
    title: str = "Tactical Core Telegram Ingress",
    version: str = "1.0.0",
) -> FastAPI:
    """Construct the Telegram webhook ingress application.

    Args:
        service: The ingress service (drives the canonical path).
        secret_token: The configured Telegram webhook ``secret_token`` used to
            verify ``X-Telegram-Bot-Api-Secret-Token``.
        webhook_path: Webhook route path (must start with "/").
        max_body_bytes: Maximum accepted request body size.
        title: OpenAPI title.
        version: OpenAPI version.

    Returns:
        A configured FastAPI application.
    """
    if not webhook_path.startswith("/"):
        webhook_path = "/" + webhook_path

    app = FastAPI(title=title, version=version)
    app.state.telegram_ingress_service = service

    @app.post(webhook_path, include_in_schema=False)
    async def receive(request: Request):  # noqa: ANN202 - FastAPI handler
        """Inbound webhook: verify secret -> decode -> durable ingest -> ACK."""
        raw_body = await request.body()

        if len(raw_body) > max_body_bytes:
            logger.warning(
                "telegram ingress rejected oversized body (%d bytes)", len(raw_body)
            )
            return JSONResponse(
                content={"detail": "payload too large"}, status_code=413
            )

        # Telegram's static shared secret header.  NEVER log the header value.
        presented = request.headers.get(SECRET_HEADER)
        if not verify_secret_token(secret_token, presented):
            # Untrusted input: reject WITHOUT reaching the canonical path.
            logger.warning("telegram ingress rejected request: invalid secret token")
            return JSONResponse(
                content={"detail": "invalid secret token"}, status_code=401
            )

        try:
            payload = await request.json()
        except Exception:  # noqa: BLE001 - malformed body is a client error
            logger.info("telegram ingress rejected request: malformed JSON")
            return JSONResponse(
                content={"detail": "malformed JSON"}, status_code=400
            )

        if not isinstance(payload, dict):
            logger.info("telegram ingress rejected request: payload not an object")
            return JSONResponse(
                content={"detail": "payload must be a JSON object"}, status_code=400
            )

        outcome = service.handle_update(payload)
        content = {
            "status": "accepted" if outcome.ok else "rejected",
            "event_ids": list(outcome.event_ids),
            "duplicate": outcome.duplicate,
        }
        if outcome.error:
            content["detail"] = outcome.error
        return JSONResponse(content=content, status_code=outcome.status_code)

    @app.get("/healthz", include_in_schema=False)
    async def healthz():  # noqa: ANN202 - FastAPI handler
        """Read-only ingress health (never exposes the secret)."""
        return JSONResponse(content={"status": "ok", "source": service.health()})

    return app


def build_app_from_config(
    config: Optional[TelegramIngressConfig] = None,
) -> FastAPI:
    """Build the ingress app end-to-end from the process environment.

    Convenience for the entrypoint: resolves configuration, configures the
    canonical database, builds the durable ingress runtime, and returns the app.
    """
    from app.database.database import initialize_database

    if config is None:
        config = TelegramIngressConfig.from_env()

    # Fail-closed database configuration (mirrors backend/main.py / WO-080).
    initialize_database(database_url=config.database_url, create_tables=True)

    from .composition import build_telegram_ingress_runtime

    wired = build_telegram_ingress_runtime()
    service = TelegramIngressService(adapter_runtime=wired.adapter_runtime)

    app = create_telegram_ingress_app(
        service=service,
        secret_token=config.secret_token,
        webhook_path=config.webhook_path,
        max_body_bytes=config.max_body_bytes,
    )
    app.state.telegram_ingress_runtime = wired
    return app
