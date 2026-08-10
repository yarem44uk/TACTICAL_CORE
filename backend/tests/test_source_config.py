"""
TACTICAL CORE — Source Configuration Tests
WO-013-004
"""

from __future__ import annotations

import pytest

from app.event_sources.config import (
    ISourceConfigProvider,
    SourceConfigError,
    SourceDefinition,
    SourceDefinitionError,
    SourceNotFoundError,
)
from app.event_sources.config.errors import DuplicateSourceError
from app.event_sources.config.provider import ISourceConfigProvider as _I


def test_valid_source_definition() -> None:
    d = SourceDefinition(name="telegram-a", adapter_type="telegram")
    assert d.name == "telegram-a"
    assert d.adapter_type == "telegram"
    assert d.enabled is True
    assert d.config == {}
    assert d.credentials_ref is None


def test_missing_name_rejected() -> None:
    with pytest.raises(SourceDefinitionError):
        SourceDefinition(name="", adapter_type="telegram")
    with pytest.raises(SourceDefinitionError):
        SourceDefinition(name="   ", adapter_type="telegram")  # type: ignore[arg-type]


def test_missing_adapter_type_rejected() -> None:
    with pytest.raises(SourceDefinitionError):
        SourceDefinition(name="telegram-a", adapter_type="")


def test_credentials_only_by_reference() -> None:
    d = SourceDefinition(
        name="telegram-a",
        adapter_type="telegram",
        credentials_ref="vault:telegram-main",
    )
    assert d.credentials_ref == "vault:telegram-main"
    # No secret value is ever stored in the definition.
    assert "secret" not in d.__dict__ or "api_token" not in d.__dict__


def test_definition_is_immutable() -> None:
    d = SourceDefinition(name="a", adapter_type="b")
    with pytest.raises(Exception):
        d.name = "changed"  # type: ignore[misc]


class _DictProvider(ISourceConfigProvider):
    """Minimal in-memory provider for tests."""

    def __init__(self, definitions: list[SourceDefinition]) -> None:
        self._defs = definitions
        self._loaded = False

    def load(self) -> None:
        # Reject duplicates at load time.
        seen: set[str] = set()
        for d in self._defs:
            if d.name in seen:
                raise DuplicateSourceError(f"duplicate source name '{d.name}'")
            seen.add(d.name)
        self._loaded = True

    def list_sources(self) -> list[SourceDefinition]:
        return list(self._defs)

    def get_source(self, name: str) -> SourceDefinition:
        for d in self._defs:
            if d.name == name:
                return d
        raise SourceNotFoundError(f"source '{name}' not found")


def test_provider_load_list_get() -> None:
    defs = [
        SourceDefinition(name="a", adapter_type="x"),
        SourceDefinition(name="b", adapter_type="y", enabled=False),
    ]
    p = _DictProvider(defs)
    p.load()
    names = [d.name for d in p.list_sources()]
    assert names == ["a", "b"]
    assert p.get_source("a").adapter_type == "x"
    assert p.get_source("b").enabled is False


def test_provider_duplicate_rejected() -> None:
    defs = [
        SourceDefinition(name="a", adapter_type="x"),
        SourceDefinition(name="a", adapter_type="y"),
    ]
    p = _DictProvider(defs)
    with pytest.raises(DuplicateSourceError):
        p.load()


def test_provider_get_missing_raises() -> None:
    p = _DictProvider([SourceDefinition(name="a", adapter_type="x")])
    with pytest.raises(SourceNotFoundError):
        p.get_source("nope")


def test_provider_interface_is_abstract() -> None:
    # Cannot instantiate the abstract contract directly.
    with pytest.raises(TypeError):
        _I()  # type: ignore[abstract]
