"""
TACTICAL CORE — WO-036 Production Source Configuration

Implements ADR-010 (Option B — Static Python source catalog module).

This module closes the documented production ``SOURCE_CONFIGURATION_GAP`` by
supplying the concrete production pieces mandated by ADR-010 while reusing the
existing source-configuration contracts unchanged:

    * ``ISourceConfigProvider``   (abstract contract, reused)
    * ``SourceDefinition``        (immutable definition, reused)
    * ``AdapterFactory``          (plugin registry, reused)
    * ``register_*_adapter()``    (existing adapter registration helpers, reused)

The production provider is backed by a static, deterministic Python catalog of
``SourceDefinition`` objects.  It is NOT YAML/JSON/TOML, NOT database-backed,
NOT plugin-discovered, and NOT dynamically imported from arbitrary modules.

ADR-010 fail-closed semantics:
    * missing / unreadable catalog  -> FAIL CLOSED (raises; never silently empty)
    * malformed catalog             -> FAIL CLOSED (raises)
    * duplicate source names        -> FAIL CLOSED (raises)
    * unknown adapter type          -> handled by AdapterFactory (AdapterTypeError)
    * empty catalog                 -> valid zero-source configuration
    * disabled-only catalog         -> valid zero active sources

``credentials_ref`` remains reference-only.  No secret value is ever stored in
the catalog; no new secret-management subsystem is introduced.
"""

from __future__ import annotations

import logging
from typing import Any

from .adapter_factory import AdapterFactory
from .errors import DuplicateSourceError, SourceConfigError, SourceNotFoundError
from .provider import ISourceConfigProvider
from .source_definition import SourceDefinition

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Static Python source catalog (ADR-010 Option B)
# ---------------------------------------------------------------------------
# The production source catalog is an explicit, deterministic list of
# ``SourceDefinition`` objects.  An embedding deployment edits THIS list to
# declare which real sources the production process should register.
#
# By default the catalog is empty (zero-source start).  A missing catalog is a
# hard error, NOT an empty catalog — that distinction is enforced by the
# provider (see ``ProductionSourceConfigProvider``).
PRODUCTION_SOURCE_CATALOG: list[SourceDefinition] = []


class ProductionSourceConfigProvider(ISourceConfigProvider):
    """Concrete production ``ISourceConfigProvider`` backed by a static catalog.

    Fail-closed: malformed or duplicate definitions are rejected at ``load()``.
    A catalog that cannot be read (e.g. the module is unavailable) raises a
    ``SourceConfigError`` rather than being silently treated as empty.
    """

    def __init__(self, catalog: list[SourceDefinition] | None = None) -> None:
        # ``None`` means "catalog unavailable" -> load() FAILS CLOSED.
        # An explicit empty list means "valid zero-source catalog".
        if catalog is None:
            self._catalog_available = False
            self._definitions: list[SourceDefinition] = []
        else:
            self._catalog_available = True
            self._definitions = list(catalog)
        self._loaded = False

    # -- ISourceConfigProvider contract ------------------------------------
    def load(self) -> None:
        """Load (or reload) the static catalog into memory (fail-closed).

        Raises:
            SourceConfigError: If the catalog is unavailable (missing/unreadable).
            DuplicateSourceError: If two sources share a name.
            SourceDefinitionError: If any definition is malformed (propagated
                from ``SourceDefinition`` validation).
        """
        if not self._catalog_available:
            raise SourceConfigError(
                "WO-036: production source catalog is unavailable; failing "
                "closed rather than silently starting with zero sources"
            )
        seen: set[str] = set()
        for definition in self._definitions:
            if not isinstance(definition, SourceDefinition):
                raise SourceConfigError(
                    "WO-036: malformed catalog entry (expected SourceDefinition)"
                )
            if definition.name in seen:
                raise DuplicateSourceError(
                    f"WO-036: duplicate source name '{definition.name}' in "
                    "production catalog"
                )
            seen.add(definition.name)
        self._loaded = True
        logger.info("WO-036: loaded %d production source definition(s).", len(self._definitions))

    def list_sources(self) -> list[SourceDefinition]:
        """Return all configured source definitions."""
        if not self._loaded:
            # Deterministic: a provider that has not been loaded yields nothing.
            return []
        return list(self._definitions)

    def get_source(self, name: str) -> SourceDefinition:
        """Return the source definition for the given name.

        Raises:
            SourceNotFoundError: If no such source exists.
        """
        for definition in self._definitions:
            if definition.name == name:
                return definition
        raise SourceNotFoundError(f"source '{name}' not found")


def build_production_source_provider(
    catalog: list[SourceDefinition] | None = None,
) -> ProductionSourceConfigProvider:
    """Construct the production source-configuration provider.

    Args:
        catalog: The static source catalog.  Defaults to the module-level
            ``PRODUCTION_SOURCE_CATALOG``.  Passing ``None`` explicitly marks
            the catalog as unavailable (fail-closed at ``load()``).

    Returns:
        A configured ``ProductionSourceConfigProvider``.
    """
    if catalog is None:
        catalog = PRODUCTION_SOURCE_CATALOG
    return ProductionSourceConfigProvider(catalog=catalog)


def build_production_adapter_factory() -> AdapterFactory:
    """Construct the production ``AdapterFactory`` with all five adapter types.

    Registers exactly the five known production adapter types through the
    existing registration helpers (ADR-010): atak, mqtt, signal, radio,
    telegram.  No dynamic plugin discovery, no new registry.

    Returns:
        An ``AdapterFactory`` able to resolve all five adapter types.
    """
    from ..adapters.atak_adapter_registration import register_atak_adapter
    from ..adapters.mqtt_adapter_registration import register_mqtt_adapter
    from ..adapters.radio_adapter_registration import register_radio_adapter
    from ..adapters.signal_adapter_registration import register_signal_adapter
    from ..adapters.telegram_adapter_registration import register_telegram_adapter

    factory = AdapterFactory()
    register_atak_adapter(factory)
    register_mqtt_adapter(factory)
    register_signal_adapter(factory)
    register_radio_adapter(factory)
    register_telegram_adapter(factory)
    return factory
