"""
TACTICAL CORE — RadioSourceAdapter Registration tests
WO-013-007

Tests for AdapterFactory registration and resolution of the Radio
source adapter, using ONLY the existing public API:

    AdapterFactory.register_type("radio", builder)
    AdapterFactory.create(SourceDefinition)
    AdapterFactory.has_type("radio")
"""

from __future__ import annotations

import pytest

from app.event_sources.adapters.radio_adapter_registration import (
    RADIO_ADAPTER_TYPE,
    build_registered_factory,
    register_radio_adapter,
)
from app.event_sources.adapters.radio_source_adapter import RadioSourceAdapter
from app.event_sources.config.adapter_factory import AdapterFactory
from app.event_sources.config.errors import AdapterTypeError
from app.event_sources.config.source_definition import SourceDefinition
from app.event_sources.interfaces.i_event_source_adapter import IEventSourceAdapter


def _definition(**overrides) -> SourceDefinition:
    base = {
        "name": "radio-source-1",
        "adapter_type": "radio",
        "enabled": True,
        "config": {"channel": "tactical-1"},
        "credentials_ref": "radio/credential-ref",
    }
    base.update(overrides)
    return SourceDefinition(**base)


def test_register_radio_adapter_registers_type():
    factory = AdapterFactory()
    register_radio_adapter(factory)
    assert factory.has_type("radio") is True


def test_register_radio_adapter_is_idempotent_safe():
    factory = AdapterFactory()
    register_radio_adapter(factory)
    register_radio_adapter(factory)  # should not raise
    assert factory.has_type("radio") is True


def test_create_resolves_radio_source_adapter():
    factory = AdapterFactory()
    register_radio_adapter(factory)
    adapter = factory.create(_definition())
    assert isinstance(adapter, RadioSourceAdapter)
    assert isinstance(adapter, IEventSourceAdapter)
    assert adapter.source_name() == "radio"


def test_create_without_registration_raises():
    factory = AdapterFactory()
    with pytest.raises(AdapterTypeError):
        factory.create(_definition())


def test_build_registered_factory_has_radio():
    factory = build_registered_factory()
    assert factory.has_type("radio") is True
    adapter = factory.create(_definition())
    assert isinstance(adapter, RadioSourceAdapter)


def test_radio_mqtt_and_signal_adapters_coexist():
    """Registering all three adapters must not interfere."""
    factory = AdapterFactory()
    register_radio_adapter(factory)

    from app.event_sources.adapters.mqtt_adapter_registration import (
        register_mqtt_adapter,
    )
    from app.event_sources.adapters.signal_adapter_registration import (
        register_signal_adapter,
    )

    register_mqtt_adapter(factory)
    register_signal_adapter(factory)
    assert factory.has_type("radio") is True
    assert factory.has_type("mqtt") is True
    assert factory.has_type("signal") is True
