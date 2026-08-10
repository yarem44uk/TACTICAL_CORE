"""
TACTICAL CORE — Adapter Factory Tests
WO-013-004

Verify the registry/plugin pattern for resolving adapter types.
"""

from __future__ import annotations

import pytest

from app.event_sources.adapters.base_adapter import BaseEventSourceAdapter
from app.event_sources.config import AdapterFactory, SourceDefinition
from app.event_sources.config.errors import AdapterTypeError, SourceDefinitionError
from app.event_sources.interfaces.i_event_source_adapter import IEventSourceAdapter


class _FakeAdapter(BaseEventSourceAdapter):
    """A concrete test adapter (not started by the factory)."""

    def __init__(self, name: str, tag: str = "fake") -> None:
        super().__init__()
        self._name = name
        self.tag = tag

    def source_name(self) -> str:
        return self._name

    def read_events(self) -> list[dict]:
        return []


def _fake_builder(definition: SourceDefinition) -> _FakeAdapter:
    return _FakeAdapter(name=definition.name)


@pytest.fixture
def factory() -> AdapterFactory:
    return AdapterFactory()


def test_adapter_registration_and_creation(factory: AdapterFactory) -> None:
    factory.register_type("fake", _fake_builder)
    assert factory.has_type("fake") is True
    assert factory.registered_types() == ["fake"]

    adapter = factory.create(SourceDefinition(name="s1", adapter_type="fake"))
    assert isinstance(adapter, IEventSourceAdapter)
    assert adapter.source_name() == "s1"


def test_factory_returns_ieventsourceadapter(factory: AdapterFactory) -> None:
    factory.register_type("fake", _fake_builder)
    adapter = factory.create(SourceDefinition(name="s1", adapter_type="fake"))
    assert isinstance(adapter, IEventSourceAdapter)


def test_unknown_adapter_type_raises(factory: AdapterFactory) -> None:
    with pytest.raises(AdapterTypeError):
        factory.create(SourceDefinition(name="s1", adapter_type="nope"))


def test_duplicate_adapter_type_registration_raises(factory: AdapterFactory) -> None:
    factory.register_type("fake", _fake_builder)
    with pytest.raises(AdapterTypeError):
        factory.register_type("fake", _fake_builder)


def test_factory_does_not_start_adapter(factory: AdapterFactory) -> None:
    factory.register_type("fake", _fake_builder)
    adapter = factory.create(SourceDefinition(name="s1", adapter_type="fake"))
    # Factory must not start the adapter (BaseEventSourceAdapter.is_running is False).
    assert adapter.is_running is False  # type: ignore[attr-defined]


def test_factory_does_not_create_threads(factory: AdapterFactory) -> None:
    factory.register_type("fake", _fake_builder)
    before = len(__import__("threading").enumerate())
    factory.create(SourceDefinition(name="s1", adapter_type="fake"))
    after = len(__import__("threading").enumerate())
    assert after == before


def test_invalid_definition_rejected(factory: AdapterFactory) -> None:
    factory.register_type("fake", _fake_builder)
    with pytest.raises(SourceDefinitionError):
        factory.create("not-a-definition")  # type: ignore[arg-type]


def test_register_invalid_type_raises(factory: AdapterFactory) -> None:
    with pytest.raises(AdapterTypeError):
        factory.register_type("", _fake_builder)  # type: ignore[arg-type]
    with pytest.raises(AdapterTypeError):
        factory.register_type("fake", None)  # type: ignore[arg-type]


def test_builder_wrong_return_type_raises(factory: AdapterFactory) -> None:
    def bad_builder(definition: SourceDefinition):
        return object()  # not an IEventSourceAdapter

    factory.register_type("bad", bad_builder)  # type: ignore[arg-type]
    with pytest.raises(AdapterTypeError):
        factory.create(SourceDefinition(name="s1", adapter_type="bad"))


def test_unregister_type(factory: AdapterFactory) -> None:
    factory.register_type("fake", _fake_builder)
    assert factory.has_type("fake")
    factory.unregister_type("fake")
    assert factory.has_type("fake") is False
    # Idempotent.
    factory.unregister_type("fake")
