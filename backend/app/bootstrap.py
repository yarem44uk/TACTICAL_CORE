"""WO-014-004 — Production Bootstrap & Source → Canonical Event Runtime.

Single authoritative production entry point.  It composes the already-built
components into a running ``Source -> canonical Event -> Plugin`` runtime:

    Source Adapter
        |
        v
    AdapterSupervisor / AdapterRuntime
        |
        v
    EventFactory
        |
        v
    canonical app.event.Event
        |
        v
    EventPipeline.process(event)          <-- wired by create_event_runtime()
        |
        v
    PluginDispatcher.dispatch(event)      <-- WO-014-002
        |
        v
    PluginManager.deliver_event(event)    <-- WO-014-001
        |
        v
    RUNNING plugin.on_event(event)

This module REUSES (never reimplements):
  * ``create_event_runtime()``  — the WO-014-003 authoritative composition root
  * ``EventFactory``            — WO-013-002 canonical Event construction
  * ``AdapterSupervisor``       — WO-013-003 source runtime orchestration
  * ``PluginManager``           — plugin lifecycle + delivery authority

It is wiring only.  It does NOT create / transform / publish events, implement
an EventBus, plugin lifecycle, retry, failure isolation, middleware or
persistence, and it does NOT modify any protected file.

Lifecycle authority: the plugin registry's ``RUNNING`` state (as driven by
``PluginManager.startup_all()``) remains the authoritative delivery state for
``deliver_event``.  This module does not introduce a competing state machine;
source lifecycle (``AdapterSupervisor``) is kept separate from plugin
lifecycle (``PluginManager``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.composition import EventRuntime, create_event_runtime
from app.event_pipeline.event_pipeline import EventPipeline
from app.event_sources.factory.event_factory import EventFactory
from app.event_sources.interfaces.i_event_source_adapter import IEventSourceAdapter
from app.event_sources.runtime.adapter_supervisor import AdapterSupervisor
from app.event_sources.runtime.runtime_health import SourceSnapshot, source_snapshot
from app.plugins.manager.plugin_manager import PluginManager, get_plugin_manager


@dataclass
class ProductionRuntime:
    """A wired, startable production runtime handle.

    Exposes the assembled canonical ``Event -> Plugin`` path (from the
    WO-014-003 composition root) together with the source side
    (``EventFactory`` + ``AdapterSupervisor``) that feeds canonical Events
    into the pipeline.
    """

    event_runtime: EventRuntime
    event_factory: EventFactory
    supervisor: AdapterSupervisor
    started: bool = False

    # --- Convenience access to the canonical Event -> Plugin path ---------

    @property
    def pipeline(self) -> EventPipeline:
        """The wired EventPipeline (from the composition root)."""
        return self.event_runtime.pipeline

    @property
    def plugin_manager(self) -> PluginManager:
        """The authoritative PluginManager (delivery authority)."""
        return self.event_runtime.plugin_manager

    @property
    def plugin_dispatcher(self) -> "object":
        """The WO-014-002 PluginDispatcher wired into the pipeline."""
        return self.event_runtime.plugin_dispatcher

    # --- Source registration ----------------------------------------------

    def add_source(self, adapter: IEventSourceAdapter):
        """Attach a source adapter to the runtime.

        The adapter is wrapped by the existing ``AdapterSupervisor`` /
        ``AdapterRuntime`` and, once ``start()`` is called, its raw events
        flow through ``EventFactory`` into the canonical pipeline.

        Args:
            adapter: A passive ``IEventSourceAdapter`` implementation.

        Returns:
            The created ``AdapterRuntime`` handle.
        """
        return self.supervisor.add_adapter(adapter)

    # --- Lifecycle ---------------------------------------------------------

    def start(self) -> None:
        """Start source processing (the production source runtime).

        Starts all source adapters via ``AdapterSupervisor.start_all()``.
        Idempotent for a running runtime.

        Plugin lifecycle is intentionally kept SEPARATE and is owned by
        ``PluginManager`` (the delivery authority).  An embedding application
        brings plugins to the authoritative ``RUNNING`` state through the
        manager (``startup_all()`` / registry) — this bootstrap does not
        conflate the source lifecycle with the plugin lifecycle.
        """
        if self.started:
            return
        self.supervisor.start_all()
        self.started = True

    def stop(self) -> None:
        """Stop source processing deterministically.

        Shuts down the source supervisor (joins runtime threads so no source
        worker is left behind).  After this no new source events are accepted.

        Plugin lifecycle is owned by ``PluginManager`` (``shutdown_all()``);
        it is not driven here so that the source lifecycle and the plugin
        lifecycle remain independent.
        """
        self.supervisor.shutdown()
        self.started = False

    # --- Targeted per-source lifecycle (WO-014-010) -----------------------

    def start_source(self, name: str) -> None:
        """Start a single named source, leaving all others untouched.

        Delegates to ``AdapterSupervisor.start(name)`` and therefore to the
        existing ``AdapterRuntime.start()``.  No new runtime, thread, or
        RestartPolicy is created here.

        Raises:
            KeyError: If no runtime with the given name exists.
        """
        self.supervisor.start(name)

    def stop_source(self, name: str) -> None:
        """Stop a single named source, leaving all others untouched.

        Delegates to ``AdapterSupervisor.stop(name)`` and therefore to the
        existing ``AdapterRuntime.stop()``.  Global shutdown semantics are
        unchanged.

        Raises:
            KeyError: If no runtime with the given name exists.
        """
        self.supervisor.stop(name)

    def restart_source(self, name: str) -> None:
        """Restart a single FAILED source through the existing supervisor.

        Delegates to the authoritative ``AdapterSupervisor.restart(name)`` /
        ``AdapterRuntime.restart()``.  Restart-budget semantics remain the
        exclusive property of the existing RestartPolicy.

        Raises:
            KeyError: If no runtime with the given name exists.
            LifecycleTransitionError: If the runtime is not in FAILED state.
        """
        self.supervisor.restart(name)

    # --- Observability (WO-014-011) ---------------------------------------

    def source_snapshot(self, name: str) -> SourceSnapshot:
        """Return the canonical read-only observability snapshot for one source.

        Read-only projection composed from the authoritative
        ``AdapterSupervisor.get_runtime(name)`` and the existing
        ``AdapterRuntime`` state/health.  It never mutates lifecycle, restart
        budget, or configuration, and never starts/stops/restarts the source.

        Args:
            name: The registered source name.

        Raises:
            KeyError: If no runtime with the given name exists (existing
                supervisor lookup semantics).
        """
        return source_snapshot(self, name)


def create_production_runtime(
    plugin_manager: Optional[PluginManager] = None,
) -> ProductionRuntime:
    """Build the authoritative production runtime.

    Single production entry point.  It composes the canonical
    ``Event -> Plugin`` path via ``create_event_runtime()`` and attaches the
    source side (``EventFactory`` + ``AdapterSupervisor``) that feeds real
    source adapter events into that pipeline.

    Args:
        plugin_manager: Optional ``PluginManager``.  Defaults to the global
            singleton from ``get_plugin_manager()`` (kept as the single
            authoritative instance).

    Returns:
        A ``ProductionRuntime`` handle ready for ``add_source`` / ``start``.
    """
    event_runtime = create_event_runtime(plugin_manager=plugin_manager)
    factory = EventFactory()
    supervisor = AdapterSupervisor(factory, event_runtime.pipeline)
    return ProductionRuntime(
        event_runtime=event_runtime,
        event_factory=factory,
        supervisor=supervisor,
    )
