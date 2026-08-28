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
  * ``OPERATOR_HOST``  (default 0.0.0.0)
  * ``OPERATOR_PORT``  (default 8010 — distinct from the durable process port)
  * ``DATABASE_URL``   (default sqlite:///./storage/database/tactical_core.db)
  * ``DATABASE_ECHO``  (default false)
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger("app.operator.entrypoint")


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

    host = os.environ.get("OPERATOR_HOST", "0.0.0.0")
    port = int(os.environ.get("OPERATOR_PORT", "8010"))

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
