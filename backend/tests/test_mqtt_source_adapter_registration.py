"""
TACTICAL CORE — MQTTSourceAdapter Registration tests
WO-013-006

Tests for AdapterFactory registration and resolution of the MQTT
source adapter, using ONLY the existing public API:

    AdapterFactory.register_type("mqtt", builder)
    AdapterFactory.create(SourceDefinition)
    AdapterFactory.has_type("mqtt")
"""

from __future__ import annotations

import pytest

from app.event_sources.adapters.mqtt_adapter_registration import (
    MQTT_ADAPTER_TYPE,
    build_registered_factory,
    register_mqtt_adapter,
)
from app.event_sources.adapters.mqtt_source_adapter import MQTTSourceAdapter
from app.event_sources.config.adapter_factory import AdapterFactory
from app.event_sources.config.errors import AdapterTypeError
from app.event_sources.config.source_definition import SourceDefinition
from app.event_sources.interfaces.i_event_source_adapter import IEventSourceAdapter


def _definition(**overrides) -> SourceDefinition:
    base = {
        "name": "mqtt-source-1",
        "adapter_type": "mqtt",
        "enabled": True,
        "config": {"topics": ["tactical/telemetry"]},
        "credentials_ref": "mqtt/credential-ref",
    }
    base.update(overrides)
    return SourceDefinition(**base)


def test_register_mqtt_adapter_registers_type():
    factory = AdapterFactory()
    register_mqtt_adapter(factory)
    assert factory.has_type("mqtt") is True


def test_register_mqtt_adapter_is_idempotent_safe():
    factory = AdapterFactory()
    register_mqtt_adapter(factory)
    register_mqtt_adapter(factory)  # should not raise
    assert factory.has_type("mqtt") is True


def test_create_resolves_mqtt_source_adapter():
    factory = AdapterFactory()
    register_mqtt_adapter(factory)
    adapter = factory.create(_definition())
    assert isinstance(adapter, MQTTSourceAdapter)
    assert isinstance(adapter, IEventSourceAdapter)
    assert adapter.source_name() == "mqtt"


def test_create_without_registration_raises():
    factory = AdapterFactory()
    with pytest.raises(AdapterTypeError):
        factory.create(_definition())


def test_build_registered_factory_has_mqtt():
    factory = build_registered_factory()
    assert factory.has_type("mqtt") is True
    adapter = factory.create(_definition())
    assert isinstance(adapter, MQTTSourceAdapter)


def test_mqtt_and_signal_adapters_coexist():
    """Registering both adapters must not interfere."""
    factory = AdapterFactory()
    register_mqtt_adapter(factory)

    from app.event_sources.adapters.signal_adapter_registration import (
        register_signal_adapter,
    )

    register_signal_adapter(factory)
    assert factory.has_type("mqtt") is True
    assert factory.has_type("signal") is True
