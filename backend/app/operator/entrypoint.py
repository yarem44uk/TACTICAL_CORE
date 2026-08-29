"""WO-037-02 — Operator process uvicorn entrypoint.

Launches the separate read-only operator FastAPI application with uvicorn.

Invocation:
    python -m app.operator.entrypoint

This entrypoint deliberately does NOT import or start the durable engine:
``backend/main.py``, ``EventPipeline``, ``DurableDeliveryDispatcher`` and
``ReconstructionService`` are never imported here. The operator process is
independently startable and is a pure consumer of the authoritative
repositories.

Configuration follows the repository's env convention (see ``backend/.env.example``):
  * ``OPERATOR_HOST``  (default 127.0.0.1 — localhost-only by default; set to a
    non-loopback address to expose on the LAN, which then REQUIRES a token)
  * ``OPERATOR_PORT``  (default 8010 — distinct from the durable process port)
  * ``OPERATOR_TOKEN`` (optional; enables the operator auth gate. Required when
    ``OPERATOR_HOST`` is non-loopback.)
  * ``DATABASE_URL``   (default sqlite:///./storage/database/tactical_core.db)
  * ``DATABASE_ECHO``  (default false)
"""

from __future__ import annotations

import logging
import os

from app.operator.auth import build_operator_auth_gate, resolve_operator_token

logger = logging.getLogger("app.operator.entrypoint")


def _is_loopback(host: str) -> bool:
    """True for loopback-only bind hosts (localhost-safe)."""
    return host in ("127.0.0.1", "::1", "localhost")


def resolve_operator_bind() -> tuple[str, int]:
    """Resolve the operator bind host/port with WO-037-05 startup safety.

    Returns ``(host, port)``. Raises ``RuntimeError`` (startup refusal) when the
    bind host is non-loopback and no ``OPERATOR_TOKEN`` is configured — exposing
    the operator API beyond loopback without authentication is refused rather
    than silently started (AD-2). The error is deterministic and non-secret; the
    token is never logged or echoed.
    """
    host = os.environ.get("OPERATOR_HOST", "127.0.0.1")
    try:
        port = int(os.environ.get("OPERATOR_PORT", "8010"))
    except (TypeError, ValueError):
        raise RuntimeError("OPERATOR_PORT must be an integer") from None
    token = resolve_operator_token()
    if not _is_loopback(host) and token is None:
        raise RuntimeError(
            "operator startup refused: OPERATOR_HOST=%r is non-loopback but "
            "OPERATOR_TOKEN is not configured; refusing to expose the operator "
            "API without authentication (set OPERATOR_TOKEN or bind loopback)."
            % host
        )
    return host, port


def _configure_global_session() -> None:
    """Configure the global DatabaseSessionManager from environment variables.

    The operator defaults to constructing its authoritative repositories from
    the global session manager, so that manager must be configured before the
    application is created. A caller that injects repositories directly (e.g.
    tests) never reaches this path.
    """
    from app.database.session import configure_session_manager

    database_url = os.environ.get(
        "DATABASE_URL", "sqlite:///./storage/database/tactical_core.db"
    )
    echo = os.environ.get("DATABASE_ECHO", "false").lower() in {"1", "true", "yes"}
    configure_session_manager(database_url=database_url, echo=echo)
    logger.info("operator session manager configured: %s", database_url)


def main() -> None:
    """Start the operator uvicorn server against the operator FastAPI app."""
    import uvicorn

    _configure_global_session()

    from app.operator.app import create_operator_app

    app = create_operator_app()

    host, port = resolve_operator_bind()
    logger.info(
        "operator binding %s:%s (auth_gate=%s)",
        host,
        port,
        "enabled" if build_operator_auth_gate().enabled else "disabled",
    )

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
