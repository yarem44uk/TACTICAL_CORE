"""
TACTICAL CORE — Signal Source Adapter Registration
WO-013-005 (extended WO-075)

Adapter-specific wiring that makes SignalSourceAdapter discoverable
through the existing WO-013 AdapterFactory plugin mechanism.

This module uses ONLY the existing public API:

    AdapterFactory.register_type(adapter_type, builder)

where `builder` has the contract `SourceDefinition -> IEventSourceAdapter`.

It does NOT modify AdapterFactory, SourceRegistry, or any protected file.
It does NOT add Signal-specific protocol logic to the generic factory.

The Signal adapter type is registered under the stable identifier:

    "signal"

WO-075 — injectable transport:

    ``register_signal_adapter(factory, transport=...)`` binds an injectable
    ``SignalTransport`` to every Signal adapter the factory builds.  The
    transport is handed to ``SignalSourceAdapter`` through the SAME existing
    registration mechanism (a builder closure with the unchanged
    ``SourceDefinition -> adapter`` contract); no parallel registry, factory
    API, or runtime is introduced.  With no transport supplied the registered
    builder is byte-for-byte the pre-WO-075 behaviour (passive queue).
"""

from __future__ import annotations

import logging

from ..config.adapter_factory import AdapterFactory
from .signal_source_adapter import (
    make_signal_adapter,
    make_signal_adapter_with_transport,
)
from .signal_transport import SignalTransport

logger = logging.getLogger(__name__)

# Stable adapter type identifier for the Signal source adapter.
SIGNAL_ADAPTER_TYPE = "signal"


def register_signal_adapter(
    factory: AdapterFactory,
    transport: SignalTransport | None = None,
) -> None:
    """Register the Signal source adapter with an AdapterFactory.

    Idempotent-safe: if the type is already registered, the existing
    registration is left untouched (a duplicate registration would raise
    AdapterTypeError from the factory).

    Args:
        factory: The AdapterFactory instance to register with.
        transport: Optional injectable ``SignalTransport`` (WO-075).  When
            supplied, every Signal adapter built by this factory receives it
            and drives its lifecycle (start/stop).  When None (default), the
            registered builder is the unchanged passive-queue builder.

    Raises:
        AdapterTypeError: If "signal" is already registered.
    """
    if factory.has_type(SIGNAL_ADAPTER_TYPE):
        logger.debug(
            "Signal adapter type '%s' already registered; skipping",
            SIGNAL_ADAPTER_TYPE,
        )
        return
    builder = (
        make_signal_adapter
        if transport is None
        else make_signal_adapter_with_transport(transport)
    )
    factory.register_type(SIGNAL_ADAPTER_TYPE, builder)
    logger.info(
        "Registered Signal source adapter type '%s' (transport=%s)",
        SIGNAL_ADAPTER_TYPE,
        type(transport).__name__ if transport is not None else None,
    )


def build_registered_factory(
    transport: SignalTransport | None = None,
) -> AdapterFactory:
    """Create an AdapterFactory with the Signal adapter pre-registered.

    Convenience for embedding applications and tests that want a factory
    already able to resolve `adapter_type == "signal"`.

    Args:
        transport: Optional injectable ``SignalTransport`` (WO-075).
    """
    factory = AdapterFactory()
    register_signal_adapter(factory, transport=transport)
    return factory
