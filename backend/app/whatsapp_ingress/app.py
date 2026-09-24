"""WO-080 — WhatsApp ingress FastAPI application factory.

Constructs the SEPARATE WhatsApp webhook ingress FastAPI application.  This
application is:

  * NOT ``backend/main.py`` (it never starts the durable-core source catalogue);
  * NOT the operator FastAPI application (the operator API stays read-only and
    is never on the ingestion path — ADR-011 §15, ADR-015 §5);
  * a thin transport boundary: it verifies the Meta signature over the raw
    body, decodes JSON, and hands the payload to
    :class:`~app.whatsapp_ingress.service.WhatsAppIngressService`.

Routes:
    GET  <webhook_path>   Meta verification challenge (`hub.mode` /
                          `hub.verify_token` / `hub.challenge`)
    POST <webhook_path>   Inbound webhook (X-Hub-Signature-256 verified)
    GET  /healthz         ingress process health (read-only)

The factory does NOT launch uvicorn; the separate ``entrypoint`` does that.

Security notes:
  * the Verify Token is compared with a constant-time comparison and is never
    logged;
  * the App Secret is never logged or echoed;
  * the raw request body is never logged at production verbosity (it contains
    message content).
"""

from __future__ import annotations

import logging
import secrets
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from .config import DEFAULT_MAX_BODY_BYTES, WhatsAppIngressConfig
from .service import WhatsAppIngressService
from .signature import SIGNATURE_HEADER, verify_signature

logger = logging.getLogger(__name__)


def create_whatsapp_ingress_app(
    *,
    service: WhatsAppIngressService,
    app_secret: str,
    verify_token: str,
    webhook_path: str = "/webhook",
    max_body_bytes: int = DEFAULT_MAX_BODY_BYTES,
    title: str = "Tactical Core WhatsApp Ingress",
    version: str = "1.0.0",
) -> FastAPI:
    """Construct the WhatsApp webhook ingress FastAPI application.

    Args:
        service: The ingress service (drives the canonical path).
        app_secret: Meta App Secret used for X-Hub-Signature-256 verification.
        verify_token: Meta webhook Verify Token (GET challenge).
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
    app.state.whatsapp_ingress_service = service

    @app.get(webhook_path, include_in_schema=False)
    async def verify(request: Request):  # noqa: ANN202 - FastAPI handler
        """Meta webhook verification challenge (fail closed)."""
        params = request.query_params
        mode = params.get("hub.mode")
        token = params.get("hub.verify_token")
        challenge = params.get("hub.challenge")

        if (
            mode == "subscribe"
            and token is not None
            and secrets.compare_digest(token, verify_token)
            and challenge is not None
        ):
            # Return the raw challenge ONLY on successful verification.
            return PlainTextResponse(content=challenge, status_code=200)

        logger.warning("whatsapp ingress verification failed (mode=%r)", mode)
        return PlainTextResponse(
            content="verification failed", status_code=403
        )

    @app.post(webhook_path, include_in_schema=False)
    async def receive(request: Request):  # noqa: ANN202 - FastAPI handler
        """Inbound webhook: verify -> decode -> durable ingest -> ACK."""
        raw_body = await request.body()

        if len(raw_body) > max_body_bytes:
            logger.warning("whatsapp ingress rejected oversized body (%d bytes)", len(raw_body))
            return JSONResponse(
                content={"detail": "payload too large"}, status_code=413
            )

        header_value = request.headers.get(SIGNATURE_HEADER)
        if not verify_signature(app_secret, raw_body, header_value):
            # Untrusted input: reject WITHOUT reaching the canonical path.
            logger.warning("whatsapp ingress rejected request: invalid signature")
            return JSONResponse(
                content={"detail": "invalid signature"}, status_code=401
            )

        try:
            payload = await request.json()
        except Exception:  # noqa: BLE001 - malformed body is a client error
            logger.info("whatsapp ingress rejected request: malformed JSON")
            return JSONResponse(
                content={"detail": "malformed JSON"}, status_code=400
            )

        if not isinstance(payload, dict):
            logger.info("whatsapp ingress rejected request: payload not an object")
            return JSONResponse(
                content={"detail": "payload must be a JSON object"}, status_code=400
            )

        outcome = service.handle_webhook(payload)
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
        """Read-only ingress health."""
        return JSONResponse(content={"status": "ok", "source": service.health()})

    return app


def build_app_from_config(
    config: Optional[WhatsAppIngressConfig] = None,
) -> FastAPI:
    """Build the ingress app end-to-end from the process environment.

    Convenience for the entrypoint: resolves configuration, configures the
    canonical database, builds the durable ingress runtime, and returns the app.
    """
    from app.database.database import initialize_database

    if config is None:
        config = WhatsAppIngressConfig.from_env()

    # Fail-closed database configuration (mirrors backend/main.py WO-033).
    initialize_database(database_url=config.database_url, create_tables=True)

    from .composition import build_whatsapp_ingress_runtime

    wired = build_whatsapp_ingress_runtime()
    service = WhatsAppIngressService(adapter_runtime=wired.adapter_runtime)

    app = create_whatsapp_ingress_app(
        service=service,
        app_secret=config.app_secret,
        verify_token=config.verify_token,
        webhook_path=config.webhook_path,
        max_body_bytes=config.max_body_bytes,
    )
    app.state.whatsapp_ingress_runtime = wired
    return app
