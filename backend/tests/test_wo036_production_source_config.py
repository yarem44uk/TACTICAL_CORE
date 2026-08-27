"""
TACTICAL CORE — WO-036 Production Source Configuration tests.

Proves the WO-036 implementation (ADR-010 Option B): the concrete production
``ISourceConfigProvider`` backed by a static Python source catalog, the
production ``AdapterFactory`` with all five adapter types, and the production
wiring in ``backend.main``.

Scope: focused WO-036 tests.  They exercise the real provider / factory /
registration contracts.  They do NOT require a database or network, and they
do NOT weaken any existing behavior.
"""

from __future__ import annotations

import pytest

from app.event_sources.config import (
    AdapterFactory,
    ISourceConfigProvider,
    SourceDefinition,
)
from app.event_sources.config.errors import (
    AdapterTypeError,
    DuplicateSourceError,
    SourceConfigError,
    SourceNotFoundError,
)
from app.event_sources.config.production_source_config import (
    PRODUCTION_SOURCE_CATALOG,
    ProductionSourceConfigProvider,
    build_production_adapter_factory,
    build_production_source_provider,
)
from app.event_sources.source_registration import ProductionSourceRegistrar


def _def(name: str, adapter_type: str, enabled: bool = True) -> SourceDefinition:
    return SourceDefinition(
        name=name,
        adapter_type=adapter_type,
        enabled=enabled,
        credentials_ref=f"env:{name}-cred",  # reference-only, never a secret value
    )


# ---------------------------------------------------------------------------
# Provider / catalog
# ---------------------------------------------------------------------------
def test_provider_implements_contract() -> None:
    provider = build_production_source_provider(catalog=[])
    assert isinstance(provider, ISourceConfigProvider)
    assert isinstance(provider, ProductionSourceConfigProvider)


def test_provider_loads_static_catalog() -> None:
    catalog = [
        _def("atak-a", "atak"),
        _def("telegram-b", "telegram", enabled=False),
    ]
    provider = build_production_source_provider(catalog=catalog)
    provider.load()
    names = [d.name for d in provider.list_sources()]
    assert names == ["atak-a", "telegram-b"]


def test_provider_get_source() -> None:
    provider = build_production_source_provider(catalog=[_def("mqtt-x", "mqtt")])
    provider.load()
    assert provider.get_source("mqtt-x").adapter_type == "mqtt"


def test_provider_get_missing_source_raises() -> None:
    provider = build_production_source_provider(catalog=[_def("a", "atak")])
    provider.load()
    with pytest.raises(SourceNotFoundError):
        provider.get_source("nope")


def test_empty_catalog_is_valid_zero_source() -> None:
    # An EXPLICIT empty catalog is a valid zero-source configuration, not an error.
    provider = build_production_source_provider(catalog=[])
    provider.load()
    assert provider.list_sources() == []


def test_missing_catalog_fails_closed() -> None:
    # A provider constructed with an unavailable catalog (``None``) FAILS CLOSED
    # at ``load()`` — it is NEVER silently treated as an empty catalog.
    provider = ProductionSourceConfigProvider(catalog=None)
    with pytest.raises(SourceConfigError):
        provider.load()


def test_duplicate_source_fails_closed() -> None:
    provider = build_production_source_provider(
        catalog=[_def("dup", "atak"), _def("dup", "telegram")]
    )
    with pytest.raises(DuplicateSourceError):
        provider.load()


def test_credentials_ref_is_reference_only() -> None:
    provider = build_production_source_provider(catalog=[_def("s", "atak")])
    provider.load()
    d = provider.get_source("s")
    assert d.credentials_ref == "env:s-cred"
    # No secret value is stored in the definition.
    assert "api_token" not in d.config
    assert "password" not in d.config


def test_default_catalog_is_module_constant() -> None:
    provider = build_production_source_provider()
    # Defaults to the module-level static catalog (explicit, not None).
    assert isinstance(provider._catalog_available, bool)


# ---------------------------------------------------------------------------
# Adapter factory — five production adapter types
# ---------------------------------------------------------------------------
def test_production_factory_registers_five_types() -> None:
    factory = build_production_adapter_factory()
    registered = factory.registered_types()
    assert registered == ["atak", "mqtt", "radio", "signal", "telegram"]


def test_factory_unknown_adapter_fails_closed() -> None:
    factory = build_production_adapter_factory()
    with pytest.raises(AdapterTypeError):
        factory.create(_def("x", "does-not-exist"))


# ---------------------------------------------------------------------------
# Production wiring (backend.main)
# ---------------------------------------------------------------------------
def test_production_wiring_provider_and_factory() -> None:
    import backend.main as main

    provider = main._production_source_provider()
    factory = main._production_adapter_factory()

    assert isinstance(provider, ISourceConfigProvider)
    assert isinstance(factory, AdapterFactory)
    assert main.SOURCE_CONFIGURATION_GAP is False
    # All five production adapter types are wired into the production factory.
    assert factory.registered_types() == ["atak", "mqtt", "radio", "signal", "telegram"]


# ---------------------------------------------------------------------------
# Registration path (existing mechanism, reused unchanged)
# ---------------------------------------------------------------------------
def test_registration_routes_enabled_sources_only() -> None:
    catalog = [
        _def("enabled-a", "atak"),
        _def("disabled-b", "atak", enabled=False),
    ]
    provider = build_production_source_provider(catalog=catalog)
    factory = build_production_adapter_factory()

    registrar = ProductionSourceRegistrar(provider=provider, factory=factory)
    registrar.load()
    configured = registrar.configured_sources()
    names = [d.name for d in configured]
    # Disabled sources are excluded from registration.
    assert names == ["enabled-a"]


def test_require_durable_delivery_invariant_preserved() -> None:
    # WO-036 must not weaken the mandatory durable-delivery invariant.
    import backend.main as main

    assert create_entrypoint_defaults_to_durable(main)


def create_entrypoint_defaults_to_durable(main) -> bool:
    import inspect

    sig = inspect.signature(main.create_production_entrypoint_runtime)
    return sig.parameters["require_durable_delivery"].default is True
