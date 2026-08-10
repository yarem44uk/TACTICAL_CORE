"""
TACTICAL CORE — ATAK/TAK Source Adapter Registration
WO-013-009

Adapter-specific wiring that makes AtakSourceAdapter discoverable through
the existing WO-013 AdapterFactory plugin mechanism.

This module uses ONLY the existing public API:

    AdapterFactory.register_type(adapter_type, builder)

where `builder` has the contract `SourceDefinition -> IEventSourceAdapter`.

It does NOT modify AdapterFactory, SourceRegistry, or any protected file.
It does NOT add ATAK-specific protocol logic to the generic factory.

The ATAK adapter type is registered under the stable identifier:

    "atak"
"""

from __future__ import annotations

import logging

from ..config.adapter_factory import AdapterFactory
from .atak_source_adapter import make_atak_adapter

logger = logging.getLogger(__name__)

# Stable adapter type identifier for the ATAK/TAK source adapter.
ATAK_ADAPTER_TYPE = "atak"


def register_atak_adapter(factory: AdapterFactory) -> None:
    """Register the ATAK/TAK source adapter with an AdapterFactory.

    Idempotent-safe: if the type is already registered, the existing
    registration is left untouched (a duplicate registration would raise
    AdapterTypeError from the factory).

    Args:
        factory: The AdapterFactory instance to register with.

    Raises:
        AdapterTypeError: If "atak" is already registered.
    """
    if factory.has_type(ATAK_ADAPTER_TYPE):
        logger.debug(
            "ATAK adapter type '%s' already registered; skipping",
            ATAK_ADAPTER_TYPE,
        )
        return
    factory.register_type(ATAK_ADAPTER_TYPE, make_atak_adapter)
    logger.info("Registered ATAK/TAK source adapter type '%s'", ATAK_ADAPTER_TYPE)


def build_registered_factory() -> AdapterFactory:
    """Create an AdapterFactory with the ATAK adapter pre-registered.

    Convenience for embedding applications and tests that want a factory
    already able to resolve `adapter_type == "atak"`.
    """
    factory = AdapterFactory()
    register_atak_adapter(factory)
    return factory
