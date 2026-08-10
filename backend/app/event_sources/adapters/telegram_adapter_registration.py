"""
TACTICAL CORE — Telegram Source Adapter Registration
WO-013-008

Adapter-specific wiring that makes TelegramSourceAdapter discoverable
through the existing WO-013 AdapterFactory plugin mechanism.

This module uses ONLY the existing public API:

    AdapterFactory.register_type(adapter_type, builder)

where `builder` has the contract `SourceDefinition -> IEventSourceAdapter`.

It does NOT modify AdapterFactory, SourceRegistry, or any protected file.
It does NOT add Telegram-specific protocol logic to the generic factory.

The Telegram adapter type is registered under the stable identifier:

    "telegram"
"""

from __future__ import annotations

import logging

from ..config.adapter_factory import AdapterFactory
from .telegram_source_adapter import make_telegram_adapter

logger = logging.getLogger(__name__)

# Stable adapter type identifier for the Telegram source adapter.
TELEGRAM_ADAPTER_TYPE = "telegram"


def register_telegram_adapter(factory: AdapterFactory) -> None:
    """Register the Telegram source adapter with an AdapterFactory.

    Idempotent-safe: if the type is already registered, the existing
    registration is left untouched (a duplicate registration would raise
    AdapterTypeError from the factory).

    Args:
        factory: The AdapterFactory instance to register with.

    Raises:
        AdapterTypeError: If "telegram" is already registered.
    """
    if factory.has_type(TELEGRAM_ADAPTER_TYPE):
        logger.debug(
            "Telegram adapter type '%s' already registered; skipping",
            TELEGRAM_ADAPTER_TYPE,
        )
        return
    factory.register_type(TELEGRAM_ADAPTER_TYPE, make_telegram_adapter)
    logger.info("Registered Telegram source adapter type '%s'", TELEGRAM_ADAPTER_TYPE)


def build_registered_factory() -> AdapterFactory:
    """Create an AdapterFactory with the Telegram adapter pre-registered.

    Convenience for embedding applications and tests that want a factory
    already able to resolve `adapter_type == "telegram"`.
    """
    factory = AdapterFactory()
    register_telegram_adapter(factory)
    return factory
