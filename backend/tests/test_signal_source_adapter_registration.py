"""
TACTICAL CORE — Signal adapter factory/registry registration tests
WO-013-005

Verifies that SignalSourceAdapter is discoverable through the existing
AdapterFactory plugin mechanism using only public API, without modifying
AdapterFactory or SourceRegistry.

Covers test-plan items 16 (factory/registry resolution).
"""

from __future__ import annotations

import pytest

from app.event_sources.adapters.signal_adapter_registration import (
    SIGNAL_ADAPTER_TYPE,
    build_registered_factory,
    register_signal_adapter,
)
from app.event_sources.adapters.signal_source_adapter import SignalSourceAdapter
from app.event_sources.config.adapter_factory import AdapterFactory
from app.event_sources.config.errors import AdapterTypeError
from app.event_sources.config.source_definition import SourceDefinition
from app.event_sources.interfaces.i_event_source_adapter import IEventSourceAdapter


def _definition(**overrides) -> SourceDefinition:
    base = {
        "name": "signal-source-1",
        "adapter_type": "signal",
        "enabled": True,
        "config": {},
        "credentials_ref": "signal/credential-ref",
    }
    base.update(overrides)
    return SourceDefinition(**base)


def test_register_signal_adapter_via_public_api():
    factory = AdapterFactory()
    register_signal_adapter(factory)
    assert factory.has_type(SIGNAL_ADAPTER_TYPE)
    assert SIGNAL_ADAPTER_TYPE in factory.registered_types()


def test_register_is_idempotent_safe():
    factory = AdapterFactory()
    register_signal_adapter(factory)
    # second registration must not raise / must skip
    register_signal_adapter(factory)
    assert factory.has_type(SIGNAL_ADAPTER_TYPE)


def test_factory_resolves_signal_source_definition():
    factory = build_registered_factory()
    adapter = factory.create(_definition())
    assert isinstance(adapter, IEventSourceAdapter)
    assert isinstance(adapter, SignalSourceAdapter)
    assert adapter.source_name() == "signal"


def test_factory_resolves_unstarted_adapter():
    factory = build_registered_factory()
    adapter = factory.create(_definition())
    # create() must return an unstarted adapter (never starts it)
    assert adapter.is_running is False


def test_unknown_adapter_type_raises():
    factory = AdapterFactory()
    with pytest.raises(AdapterTypeError):
        factory.create(_definition(adapter_type="unknown"))


def test_duplicate_manual_registration_raises():
    factory = AdapterFactory()
    register_signal_adapter(factory)

    def other_builder(defn: SourceDefinition) -> IEventSourceAdapter:
        return SignalSourceAdapter(defn)

    with pytest.raises(AdapterTypeError):
        factory.register_type(SIGNAL_ADAPTER_TYPE, other_builder)
