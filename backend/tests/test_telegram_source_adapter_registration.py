"""
TACTICAL CORE — TelegramSourceAdapter Registration tests
WO-013-008

Tests for AdapterFactory registration and resolution of the Telegram
source adapter, using ONLY the existing public API:

    AdapterFactory.register_type("telegram", builder)
    AdapterFactory.create(SourceDefinition)
    AdapterFactory.has_type("telegram")
"""

from __future__ import annotations

import pytest

from app.event_sources.adapters.telegram_adapter_registration import (
    TELEGRAM_ADAPTER_TYPE,
    build_registered_factory,
    register_telegram_adapter,
)
from app.event_sources.adapters.telegram_source_adapter import TelegramSourceAdapter
from app.event_sources.config.adapter_factory import AdapterFactory
from app.event_sources.config.errors import AdapterTypeError
from app.event_sources.config.source_definition import SourceDefinition
from app.event_sources.interfaces.i_event_source_adapter import IEventSourceAdapter


def _definition(**overrides) -> SourceDefinition:
    base = {
        "name": "telegram-source-1",
        "adapter_type": "telegram",
        "enabled": True,
        "config": {"chat": "tactical-ops"},
        "credentials_ref": "telegram.production",
    }
    base.update(overrides)
    return SourceDefinition(**base)


def test_register_telegram_adapter_registers_type():
    factory = AdapterFactory()
    register_telegram_adapter(factory)
    assert factory.has_type("telegram") is True


def test_register_telegram_adapter_is_idempotent_safe():
    factory = AdapterFactory()
    register_telegram_adapter(factory)
    register_telegram_adapter(factory)  # should not raise
    assert factory.has_type("telegram") is True


def test_create_resolves_telegram_source_adapter():
    factory = AdapterFactory()
    register_telegram_adapter(factory)
    adapter = factory.create(_definition())
    assert isinstance(adapter, TelegramSourceAdapter)
    assert isinstance(adapter, IEventSourceAdapter)
    assert adapter.source_name() == "telegram"


def test_create_without_registration_raises():
    factory = AdapterFactory()
    with pytest.raises(AdapterTypeError):
        factory.create(_definition())


def test_build_registered_factory_has_telegram():
    factory = build_registered_factory()
    assert factory.has_type("telegram") is True
    adapter = factory.create(_definition())
    assert isinstance(adapter, TelegramSourceAdapter)


def test_telegram_mqtt_signal_and_radio_adapters_coexist():
    """Registering all four adapters must not interfere."""
    factory = AdapterFactory()
    register_telegram_adapter(factory)

    from app.event_sources.adapters.mqtt_adapter_registration import (
        register_mqtt_adapter,
    )
    from app.event_sources.adapters.radio_adapter_registration import (
        register_radio_adapter,
    )
    from app.event_sources.adapters.signal_adapter_registration import (
        register_signal_adapter,
    )

    register_mqtt_adapter(factory)
    register_radio_adapter(factory)
    register_signal_adapter(factory)
    assert factory.has_type("telegram") is True
    assert factory.has_type("mqtt") is True
    assert factory.has_type("radio") is True
    assert factory.has_type("signal") is True
