"""
TACTICAL CORE — Radio Source Adapter Registration
WO-013-007

Adapter-specific wiring that makes RadioSourceAdapter discoverable through
the existing WO-013 AdapterFactory plugin mechanism.

This module uses ONLY the existing public API:

    AdapterFactory.register_type(adapter_type, builder)

where `builder` has the contract `SourceDefinition -> IEventSourceAdapter`.

It does NOT modify AdapterFactory, SourceRegistry, or any protected file.
It does NOT add Radio-specific protocol logic to the generic factory.

The Radio adapter type is registered under the stable identifier:

    "radio"
"""

from __future__ import annotations

import logging

from ..config.adapter_factory import AdapterFactory
from .radio_source_adapter import make_radio_adapter

logger = logging.getLogger(__name__)

# Stable adapter type identifier for the Radio source adapter.
RADIO_ADAPTER_TYPE = "radio"


def register_radio_adapter(factory: AdapterFactory) -> None:
    """Register the Radio source adapter with an AdapterFactory.

    Idempotent-safe: if the type is already registered, the existing
    registration is left untouched (a duplicate registration would raise
    AdapterTypeError from the factory).

    Args:
        factory: The AdapterFactory instance to register with.

    Raises:
        AdapterTypeError: If "radio" is already registered.
    """
    if factory.has_type(RADIO_ADAPTER_TYPE):
        logger.debug(
            "Radio adapter type '%s' already registered; skipping",
            RADIO_ADAPTER_TYPE,
        )
        return
    factory.register_type(RADIO_ADAPTER_TYPE, make_radio_adapter)
    logger.info("Registered Radio source adapter type '%s'", RADIO_ADAPTER_TYPE)


def build_registered_factory() -> AdapterFactory:
    """Create an AdapterFactory with the Radio adapter pre-registered.

    Convenience for embedding applications and tests that want a factory
    already able to resolve `adapter_type == "radio"`.
    """
    factory = AdapterFactory()
    register_radio_adapter(factory)
    return factory
