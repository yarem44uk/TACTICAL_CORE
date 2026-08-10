"""
TACTICAL CORE — MQTT Source Adapter Registration
WO-013-006

Adapter-specific wiring that makes MQTTSourceAdapter discoverable through
the existing WO-013 AdapterFactory plugin mechanism.

This module uses ONLY the existing public API:

    AdapterFactory.register_type(adapter_type, builder)

where `builder` has the contract `SourceDefinition -> IEventSourceAdapter`.

It does NOT modify AdapterFactory, SourceRegistry, or any protected file.
It does NOT add MQTT-specific protocol logic to the generic factory.

The MQTT adapter type is registered under the stable identifier:

    "mqtt"
"""

from __future__ import annotations

import logging

from ..config.adapter_factory import AdapterFactory
from .mqtt_source_adapter import make_mqtt_adapter

logger = logging.getLogger(__name__)

# Stable adapter type identifier for the MQTT source adapter.
MQTT_ADAPTER_TYPE = "mqtt"


def register_mqtt_adapter(factory: AdapterFactory) -> None:
    """Register the MQTT source adapter with an AdapterFactory.

    Idempotent-safe: if the type is already registered, the existing
    registration is left untouched (a duplicate registration would raise
    AdapterTypeError from the factory).

    Args:
        factory: The AdapterFactory instance to register with.

    Raises:
        AdapterTypeError: If "mqtt" is already registered.
    """
    if factory.has_type(MQTT_ADAPTER_TYPE):
        logger.debug(
            "MQTT adapter type '%s' already registered; skipping",
            MQTT_ADAPTER_TYPE,
        )
        return
    factory.register_type(MQTT_ADAPTER_TYPE, make_mqtt_adapter)
    logger.info("Registered MQTT source adapter type '%s'", MQTT_ADAPTER_TYPE)


def build_registered_factory() -> AdapterFactory:
    """Create an AdapterFactory with the MQTT adapter pre-registered.

    Convenience for embedding applications and tests that want a factory
    already able to resolve `adapter_type == "mqtt"`.
    """
    factory = AdapterFactory()
    register_mqtt_adapter(factory)
    return factory
