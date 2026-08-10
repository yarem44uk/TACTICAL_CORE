"""
TACTICAL CORE — Signal Source Adapter Registration
WO-013-005

Adapter-specific wiring that makes SignalSourceAdapter discoverable
through the existing WO-013 AdapterFactory plugin mechanism.

This module uses ONLY the existing public API:

    AdapterFactory.register_type(adapter_type, builder)

where `builder` has the contract `SourceDefinition -> IEventSourceAdapter`.

It does NOT modify AdapterFactory, SourceRegistry, or any protected file.
It does NOT add Signal-specific protocol logic to the generic factory.

The Signal adapter type is registered under the stable identifier:

    "signal"
"""

from __future__ import annotations

import logging

from ..config.adapter_factory import AdapterFactory
from .signal_source_adapter import make_signal_adapter

logger = logging.getLogger(__name__)

# Stable adapter type identifier for the Signal source adapter.
SIGNAL_ADAPTER_TYPE = "signal"


def register_signal_adapter(factory: AdapterFactory) -> None:
    """Register the Signal source adapter with an AdapterFactory.

    Idempotent-safe: if the type is already registered, the existing
    registration is left untouched (a duplicate registration would raise
    AdapterTypeError from the factory).

    Args:
        factory: The AdapterFactory instance to register with.

    Raises:
        AdapterTypeError: If "signal" is already registered.
    """
    if factory.has_type(SIGNAL_ADAPTER_TYPE):
        logger.debug(
            "Signal adapter type '%s' already registered; skipping",
            SIGNAL_ADAPTER_TYPE,
        )
        return
    factory.register_type(SIGNAL_ADAPTER_TYPE, make_signal_adapter)
    logger.info("Registered Signal source adapter type '%s'", SIGNAL_ADAPTER_TYPE)


def build_registered_factory() -> AdapterFactory:
    """Create an AdapterFactory with the Signal adapter pre-registered.

    Convenience for embedding applications and tests that want a factory
    already able to resolve `adapter_type == "signal"`.
    """
    factory = AdapterFactory()
    register_signal_adapter(factory)
    return factory
