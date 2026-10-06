"""WO-083 — Telegram ingress process entrypoint.

A SEPARATE, independently startable process that serves the Telegram Bot API
webhook and drives the canonical durable ingestion path.

Invocation (from ``backend/``):

    python -m app.telegram_ingress.entrypoint

or, from the repository root:

    python -m backend.app.telegram_ingress.entrypoint

This entrypoint is INDEPENDENT of:

  * ``backend/main.py``          (the durable-core production process);
  * ``app.operator.entrypoint``  (the read-only operator process);
  * ``app.whatsapp_ingress``     (the separate WhatsApp ingress process).

It configures the canonical database (fail-closed), builds the durable ingress
runtime (fail-closed on durable delivery), and serves the app with uvicorn.  It
never starts the operator application and never adds a route to it.

Configuration (environment):

    TELEGRAM_WEBHOOK_SECRET  required — Telegram webhook secret_token
    TELEGRAM_HOST            optional — default 127.0.0.1 (loopback-only)
    TELEGRAM_PORT            optional — default 8030
    TELEGRAM_WEBHOOK_PATH    optional — default /telegram/webhook
    DATABASE_URL             required — canonical durable store

Secrets are never logged.  Public exposure / TLS termination / DNS / firewall
policy / ``setWebhook`` registration are a DEPLOYMENT concern and are OUT OF
SCOPE for this WO (WO-083 §30).
"""

from __future__ import annotations

import logging
import os
import sys

# --- import-path bootstrap ---------------------------------------------------
# ``app`` lives under ``backend/``; make ``python -m backend.app.telegram_ingress
# .entrypoint`` work from the repository root without an external PYTHONPATH.
_BACKEND_DIR = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

logger = logging.getLogger("app.telegram_ingress.entrypoint")


def main() -> int:
    """Start the Telegram ingress uvicorn server."""
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))

    import uvicorn

    from app.telegram_ingress.app import build_app_from_config
    from app.telegram_ingress.config import TelegramIngressConfig

    # Fail-closed configuration: raises (non-secret message) when a required
    # value is missing, before any durable or network resource is acquired.
    config = TelegramIngressConfig.from_env()

    app = build_app_from_config(config)
    wired = getattr(app.state, "telegram_ingress_runtime", None)

    logger.info(
        "telegram ingress binding %s:%s path=%s",
        config.host,
        config.port,
        config.webhook_path,
    )
    try:
        uvicorn.run(app, host=config.host, port=config.port)
    finally:
        if wired is not None:
            wired.stop()
    return 0


if __name__ == "__main__":  # pragma: no cover - process entrypoint
    raise SystemExit(main())
