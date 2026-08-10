"""
TACTICAL CORE — AtakSourceAdapter Registration tests
WO-013-009

Tests for AdapterFactory registration and resolution of the ATAK/TAK
source adapter, using ONLY the existing public API:

    AdapterFactory.register_type("atak", builder)
    AdapterFactory.create(SourceDefinition)
    AdapterFactory.has_type("atak")
"""

from __future__ import annotations

import pytest

from app.event_sources.adapters.atak_adapter_registration import (
    ATAK_ADAPTER_TYPE,
    build_registered_factory,
    register_atak_adapter,
)
from app.event_sources.adapters.atak_source_adapter import AtakSourceAdapter
from app.event_sources.config.adapter_factory import AdapterFactory
from app.event_sources.config.errors import AdapterTypeError
from app.event_sources.config.source_definition import SourceDefinition
from app.event_sources.interfaces.i_event_source_adapter import IEventSourceAdapter


def _definition(**overrides) -> SourceDefinition:
    base = {
        "name": "atak-source-1",
        "adapter_type": "atak",
        "enabled": True,
        "config": {"team": "blue-1"},
        "credentials_ref": "atak.production",
    }
    base.update(overrides)
    return SourceDefinition(**base)


def test_register_atak_adapter_registers_type():
    factory = AdapterFactory()
    register_atak_adapter(factory)
    assert factory.has_type("atak") is True


def test_register_atak_adapter_is_idempotent_safe():
    factory = AdapterFactory()
    register_atak_adapter(factory)
    register_atak_adapter(factory)  # should not raise
    assert factory.has_type("atak") is True


def test_create_resolves_atak_source_adapter():
    factory = AdapterFactory()
    register_atak_adapter(factory)
    adapter = factory.create(_definition())
    assert isinstance(adapter, AtakSourceAdapter)
    assert isinstance(adapter, IEventSourceAdapter)
    assert adapter.source_name() == "atak"


def test_create_without_registration_raises():
    factory = AdapterFactory()
    with pytest.raises(AdapterTypeError):
        factory.create(_definition())


def test_build_registered_factory_has_atak():
    factory = build_registered_factory()
    assert factory.has_type("atak") is True
    adapter = factory.create(_definition())
    assert isinstance(adapter, AtakSourceAdapter)


def test_atak_telegram_mqtt_signal_and_radio_adapters_coexist():
    """Registering all five adapters must not interfere."""
    factory = AdapterFactory()
    register_atak_adapter(factory)

    from app.event_sources.adapters.mqtt_adapter_registration import (
        register_mqtt_adapter,
    )
    from app.event_sources.adapters.radio_adapter_registration import (
        register_radio_adapter,
    )
    from app.event_sources.adapters.signal_adapter_registration import (
        register_signal_adapter,
    )
    from app.event_sources.adapters.telegram_adapter_registration import (
        register_telegram_adapter,
    )

    register_mqtt_adapter(factory)
    register_radio_adapter(factory)
    register_signal_adapter(factory)
    register_telegram_adapter(factory)
    assert factory.has_type("atak") is True
    assert factory.has_type("mqtt") is True
    assert factory.has_type("radio") is True
    assert factory.has_type("signal") is True
    assert factory.has_type("telegram") is True
