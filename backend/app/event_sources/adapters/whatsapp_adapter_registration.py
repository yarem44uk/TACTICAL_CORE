"""TACTICAL CORE — WhatsApp Source Adapter Registration
WO-080

Adapter-specific wiring that makes ``WhatsAppSourceAdapter`` discoverable
through the existing WO-013 ``AdapterFactory`` plugin mechanism.

This module uses ONLY the existing public API:

    AdapterFactory.register_type(adapter_type, builder)

where ``builder`` has the contract ``SourceDefinition -> IEventSourceAdapter``.

It does NOT modify ``AdapterFactory``, ``SourceRegistry``, or any protected
file.  It does NOT add WhatsApp-specific protocol logic to the generic factory.
It does NOT create a second adapter registry.

The WhatsApp adapter type is registered under the stable identifier:

    "whatsapp"

Note (WO-080): the whatsapp type is deliberately NOT added to the default
production adapter factory (``build_production_adapter_factory``).  The
WhatsApp ingress is a SEPARATE process with its OWN composition (ADR-015 §5);
its composition registers the whatsapp type on top of the existing production
factory via this helper.  This keeps the durable-core production process
(``backend/main.py``) unchanged and avoids registering a producer-less source
into it.
"""

from __future__ import annotations

import logging

from ..config.adapter_factory import AdapterFactory
from .whatsapp_source_adapter import make_whatsapp_adapter

logger = logging.getLogger(__name__)

# Stable adapter type identifier for the WhatsApp source adapter.
WHATSAPP_ADAPTER_TYPE = "whatsapp"


def register_whatsapp_adapter(factory: AdapterFactory) -> None:
    """Register the WhatsApp source adapter with an AdapterFactory.

    Idempotent-safe: if the type is already registered, the existing
    registration is left untouched (a duplicate registration would raise
    ``AdapterTypeError`` from the factory).

    Args:
        factory: The ``AdapterFactory`` instance to register with.

    Raises:
        AdapterTypeError: If "whatsapp" is already registered.
    """
    if factory.has_type(WHATSAPP_ADAPTER_TYPE):
        logger.debug(
            "WhatsApp adapter type '%s' already registered; skipping",
            WHATSAPP_ADAPTER_TYPE,
        )
        return
    factory.register_type(WHATSAPP_ADAPTER_TYPE, make_whatsapp_adapter)
    logger.info(
        "Registered WhatsApp source adapter type '%s'", WHATSAPP_ADAPTER_TYPE
    )


def build_registered_factory() -> AdapterFactory:
    """Create an AdapterFactory with the WhatsApp adapter pre-registered.

    Convenience for embedding applications and tests that want a factory
    already able to resolve ``adapter_type == "whatsapp"``.
    """
    factory = AdapterFactory()
    register_whatsapp_adapter(factory)
    return factory
