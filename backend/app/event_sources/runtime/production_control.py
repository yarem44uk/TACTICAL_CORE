"""
TACTICAL CORE — Production Runtime Control Plane
WO-014-008

A thin, explicit application-level control facade over the EXISTING
``ProductionRuntime`` (WO-014-004).

This module is an ADAPTER/FACADE.  It is NOT a new runtime, NOT a new
lifecycle manager, NOT a supervisor, NOT an event dispatcher, NOT an event
pipeline, and NOT a plugin manager.

It receives an already-composed ``ProductionRuntime`` instance via dependency
injection and exposes only four safe operations to an embedding application:

    start()   -> delegate to ProductionRuntime.start()
    stop()    -> delegate to ProductionRuntime.stop()
    state()   -> derived read-only projection of runtime/source state
    health()  -> delegate to the WO-014-007 runtime-health observer

Canonical event path is UNAFFECTED:

    Source Adapter
        -> AdapterSupervisor / AdapterRuntime
        -> EventFactory
        -> canonical app.event.Event
        -> EventPipeline.process(event)
        -> PluginDispatcher.dispatch(event)
        -> PluginManager.deliver_event(event)
        -> RUNNING plugin.on_event(event)

This control plane is OUTSIDE that path.  It never:
    * constructs a ProductionRuntime / AdapterSupervisor / EventPipeline /
      PluginDispatcher / PluginManager
    * creates / transforms / serializes / dispatches Events
    * calls pipeline.process() / dispatcher.dispatch() /
      manager.deliver_event()
    * starts / stops / restarts individual sources
    * starts / stops plugins or touches the plugin lifecycle
    * introduces an EventBus or a legacy app.core event path
    * maintains a shadow copy of runtime / source / plugin / health state
    * creates threads, timers, event loops, queues, or network listeners

Lifecycle ownership is preserved:
    * source lifecycle  -> AdapterSupervisor (owned by ProductionRuntime)
    * plugin lifecycle  -> PluginManager
The facade only delegates to ``ProductionRuntime.start()`` / ``stop()``; it
never reaches into the supervisor for per-source control.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .runtime_health import RuntimeHealth, RuntimeState, runtime_health

if TYPE_CHECKING:  # pragma: no cover - typing only, avoids runtime import cycle
    from app.bootstrap import ProductionRuntime


class ProductionRuntimeController:
    """Thin application-level control facade over an existing ProductionRuntime.

    The controller receives an already-composed ``ProductionRuntime`` through
    dependency injection.  It does NOT construct any runtime, supervisor,
    pipeline, dispatcher, or plugin manager.

    It stores ONLY the injected runtime reference (no shadow state).
    """

    def __init__(self, runtime: "ProductionRuntime") -> None:
        self._runtime = runtime

    # --- Lifecycle control (delegated to the authoritative runtime) --------

    def start(self) -> None:
        """Start the production source runtime.

        Delegates directly to ``ProductionRuntime.start()``.  Idempotency and
        lifecycle semantics are owned by the runtime itself.  Exceptions from
        the runtime propagate unchanged.
        """
        self._runtime.start()

    def stop(self) -> None:
        """Stop the production source runtime.

        Delegates directly to ``ProductionRuntime.stop()``.  Exceptions from
        the runtime propagate unchanged.
        """
        self._runtime.stop()

    # --- Targeted per-source control (WO-014-010) -------------------------
    #
    # The controller remains a stateless facade.  These operations delegate
    # straight to the authoritative ProductionRuntime -> AdapterSupervisor ->
    # AdapterRuntime path.  The controller does NOT construct or own any
    # runtime, supervisor, thread, timer, or RestartPolicy.

    def start_source(self, name: str) -> None:
        """Start a single named source, leaving all others untouched.

        Delegates to ``ProductionRuntime.start_source(name)`` (and therefore
        to AdapterSupervisor -> AdapterRuntime).  Exceptions (e.g. ``KeyError``
        for an unknown source) propagate unchanged.

        Args:
            name: The source/runtime name.
        """
        self._runtime.start_source(name)

    def stop_source(self, name: str) -> None:
        """Stop a single named source, leaving all others untouched.

        Delegates to ``ProductionRuntime.stop_source(name)`` (and therefore to
        AdapterSupervisor -> AdapterRuntime).  Global shutdown semantics are
        unchanged.

        Args:
            name: The source/runtime name.
        """
        self._runtime.stop_source(name)

    def restart_source(self, name: str) -> None:
        """Restart a single FAILED source through the existing supervisor.

        Delegates to ``ProductionRuntime.restart_source(name)`` and therefore
        to the authoritative ``AdapterSupervisor.restart(name)`` /
        ``AdapterRuntime.restart()``.  Restart-budget semantics remain the
        exclusive property of the existing RestartPolicy.

        Args:
            name: The source/runtime name.
        """
        self._runtime.restart_source(name)

    # --- Observation (derived / delegated, never stored) -------------------

    def state(self) -> RuntimeState:
        """Return the derived aggregate runtime state.

        A pure read-only projection: when the runtime has not been started it
        is ``STOPPED``; otherwise the aggregate state is derived from the
        authoritative per-source lifecycle via the WO-014-007 health observer.
        No state is stored on the controller.
        """
        if not self._runtime.started:
            return RuntimeState.STOPPED
        return runtime_health(self._runtime).state

    def health(self) -> RuntimeHealth:
        """Return the authoritative runtime health snapshot.

        Delegates to the WO-014-007 ``runtime_health()`` observer.  Health
        semantics are owned by that module and are never duplicated here.
        """
        return runtime_health(self._runtime)

    # --- Introspection -----------------------------------------------------

    @property
    def runtime(self) -> Any:
        """The bound authoritative ProductionRuntime (read-only access)."""
        return self._runtime
