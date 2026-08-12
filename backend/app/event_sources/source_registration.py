"""
TACTICAL CORE — Production Source Registration & Configuration
WO-014-005

The single authoritative mechanism by which production source adapters are
selected/registered for the existing ProductionRuntime.

This module bridges the WO-013 source-configuration layer
(``SourceDefinition`` + ``ISourceConfigProvider`` + ``AdapterFactory``) into
the WO-014 production runtime WITHOUT reimplementing any of them and WITHOUT
modifying any previous WO.

Reused contracts (unchanged):
    * ``SourceDefinition``            — immutable source configuration
    * ``ISourceConfigProvider``        — supplies source definitions
    * ``AdapterFactory``              — resolves adapter_type -> adapter
    * ``ProductionRuntime.add_source`` — routes into the EXISTING
                                          AdapterSupervisor / AdapterRuntime

It does NOT:
    * start/stop/restart adapters          (lifecycle belongs to the runtime)
    * spawn threads / poll sources
    * implement an EventBus or legacy path
    * reconstruct Events or inject raw dicts
    * implement plugin lifecycle / retry / failure isolation
    * invent a configuration schema, factory API, discovery mechanism,
      environment variables, YAML/JSON schema, or dynamic import
    * add networking / exec / shell behaviour

Canonical path (unchanged, preserved by this WO):

    SOURCE ADAPTER
        -> AdapterSupervisor / AdapterRuntime
        -> EventFactory
        -> canonical app.event.Event
        -> EventPipeline.process(event)      (create_event_runtime)
        -> PluginDispatcher.dispatch(event)  (WO-014-002)
        -> PluginManager.deliver_event(event)(WO-014-001)
        -> plugin.on_event(event)
"""

from __future__ import annotations

from typing import Any

from .config.adapter_factory import AdapterFactory
from .config.provider import ISourceConfigProvider
from .config.source_definition import SourceDefinition


class ProductionSourceRegistrar:
    """Authoritative production source-selection / registration path.

    Given an ``ISourceConfigProvider`` (supplying ``SourceDefinition`` objects)
    and an ``AdapterFactory`` (resolving ``adapter_type`` -> adapter), this
    registrar builds the configured adapters and registers them through the
    production runtime's existing ``add_source`` boundary (which routes into
    the existing ``AdapterSupervisor``).

    The registrar only creates and registers adapters.  Starting them is owned
    by the production runtime (``ProductionRuntime.start()`` ->
    ``AdapterSupervisor.start_all()``), preserving lifecycle separation.
    """

    def __init__(
        self,
        provider: ISourceConfigProvider,
        factory: AdapterFactory,
    ) -> None:
        if provider is None:
            raise TypeError("provider is required (ISourceConfigProvider)")
        if factory is None:
            raise TypeError("factory is required (AdapterFactory)")
        self._provider = provider
        self._factory = factory

    @property
    def provider(self) -> ISourceConfigProvider:
        """The source-configuration provider driving this registrar."""
        return self._provider

    @property
    def factory(self) -> AdapterFactory:
        """The AdapterFactory used to resolve source adapters."""
        return self._factory

    def load(self) -> None:
        """Load (or reload) the source configuration through the provider."""
        self._provider.load()

    def configured_sources(self) -> list[SourceDefinition]:
        """Return all enabled source definitions (already loaded).

        Disabled sources are excluded from production registration so the
        runtime only starts sources that are explicitly enabled.
        """
        return [d for d in self._provider.list_sources() if d.enabled]

    def register(self, runtime: Any) -> list[str]:
        """Register every enabled configured source into the runtime.

        Args:
            runtime: An object exposing the production ``add_source(adapter)``
                boundary (a ``ProductionRuntime``).  Adapters are routed into
                the existing ``AdapterSupervisor`` through this method.

        Returns:
            Sorted list of registered source names.

        Raises:
            AdapterTypeError: If a configured ``adapter_type`` is unknown to
                the AdapterFactory (the authoritative resolution failure).
        """
        definitions = self.configured_sources()
        registered: list[str] = []
        for definition in definitions:
            adapter = self._factory.create(definition)
            runtime.add_source(adapter)
            registered.append(definition.name)
        return sorted(registered)


def register_production_sources(
    runtime: Any,
    provider: ISourceConfigProvider,
    factory: AdapterFactory,
) -> list[str]:
    """One-call authoritative registration of configured sources into a runtime.

    This is the module-level convenience entry point for the WO-014-005
    registration path.  It loads the configuration, builds each enabled source
    adapter through the existing AdapterFactory, and registers it into the
    runtime through its existing ``add_source`` boundary.

    Args:
        runtime: A ``ProductionRuntime`` (or equivalent ``add_source`` sink).
        provider: Source-configuration provider.
        factory: AdapterFactory with the desired adapter types registered.

    Returns:
        Sorted list of registered source names.
    """
    registrar = ProductionSourceRegistrar(provider=provider, factory=factory)
    registrar.load()
    return registrar.register(runtime)
