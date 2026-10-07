"""TACTICAL CORE — Telegram Inbound Webhook Ingress (WO-083).

A SEPARATE, independently startable ingress process that terminates the public
Telegram Bot API webhook trust boundary and drives the EXISTING canonical
ingestion path:

    Telegram Bot API (setWebhook, HTTPS POST of a JSON Update)
      -> Telegram Webhook Ingress (this package; own process, own entrypoint)
      -> X-Telegram-Bot-Api-Secret-Token verification
      -> TelegramUpdateNormalizer  (Update envelope -> raw dict)
      -> TelegramSourceAdapter (existing WO-013 leaf; via AdapterFactory)
      -> AdapterRuntime.submit_raw()   (synchronous durable seam)
      -> EventFactory -> EventPipeline -> DurableCanonicalEventRepository
      -> Observation -> Operator Wall

This package is NOT ``backend/main.py`` and NOT the operator application.  No
second event architecture is introduced.  Legacy ``app.connectors.telegram``
(which imports ``app.core.event_bus``) is NOT used.
"""

from .app import build_app_from_config, create_telegram_ingress_app
from .config import TelegramIngressConfig, TelegramIngressConfigError
from .normalizer import (
    SUPPORTED_UPDATE_TYPE,
    TelegramUpdateError,
    TelegramUpdateNormalizer,
)
from .secret import SECRET_HEADER, verify_secret_token
from .service import IngressOutcome, TelegramIngressService

__all__ = [
    "build_app_from_config",
    "create_telegram_ingress_app",
    "TelegramIngressConfig",
    "TelegramIngressConfigError",
    "SUPPORTED_UPDATE_TYPE",
    "TelegramUpdateError",
    "TelegramUpdateNormalizer",
    "SECRET_HEADER",
    "verify_secret_token",
    "IngressOutcome",
    "TelegramIngressService",
]
