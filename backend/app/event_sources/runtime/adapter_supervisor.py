"""
TACTICAL CORE — Adapter Supervisor
WO-013-003

AdapterSupervisor owns N AdapterRuntimes and orchestrates them.

Responsibilities:
    - create/attach runtimes
    - start_all / stop_all
    - restart(name)
    - get_health() aggregate
    - shutdown

Boundary with SourceRegistry:
    SourceRegistry  = registration catalog (register/get/list/remove/start_all/stop_all/count)
    AdapterSupervisor = runtime/thread/poll-loop/restart/health orchestration

The supervisor may USE SourceRegistry as a source of adapters, but it does
NOT replace it. It never starts an adapter twice: SourceRegistry.start_all()
drives adapter lifecycle start; AdapterSupervisor drives runtime threads.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from ..registry.source_registry import SourceRegistry
from ..interfaces.i_event_source_adapter import IEventSourceAdapter
from ..interfaces.i_event_factory import IEventFactory
from ...event_pipeline.interfaces.i_event_pipeline import IEventPipeline
from .adapter_runtime import AdapterRuntime
from .lifecycle import AdapterState, LifecycleTransitionError

logger = logging.getLogger(__name__)


class AdapterSupervisor:
    """Orchestrates one AdapterRuntime per registered source adapter.

    Args:
        factory: Event factory shared by all runtimes.
        pipeline: Event pipeline shared by all runtimes.
        registry: Optional SourceRegistry to source adapters from.
    """

    def __init__(
        self,
        factory: IEventFactory,
        pipeline: IEventPipeline,
        registry: SourceRegistry | None = None,
    ) -> None:
        self._factory = factory
        self._pipeline = pipeline
        self._registry = registry
        self._runtimes: dict[str, AdapterRuntime] = {}
        self._lock = threading.Lock()

    # --- Registration ---

    def add_adapter(self, adapter: IEventSourceAdapter) -> AdapterRuntime:
        """Create and attach a runtime for a single adapter.

        If a SourceRegistry was provided, the adapter is also registered there.
        """
        name = adapter.source_name()
        with self._lock:
            if name in self._runtimes:
                raise ValueError(f"Runtime for adapter '{name}' already exists")
            runtime = AdapterRuntime(
                adapter=adapter,
                factory=self._factory,
                pipeline=self._pipeline,
                name=name,
            )
            self._runtimes[name] = runtime
            if self._registry is not None:
                try:
                    self._registry.register(adapter)
                except ValueError:
                    # adapter already registered; runtime still created
                    pass
            return runtime

    def add_runtime(self, runtime: AdapterRuntime) -> None:
        """Attach an already-constructed runtime directly."""
        with self._lock:
            if runtime.name in self._runtimes:
                raise ValueError(
                    f"Runtime for adapter '{runtime.name}' already exists"
                )
            self._runtimes[runtime.name] = runtime

    def remove_adapter(self, name: str) -> None:
        """Stop and remove a runtime by adapter name."""
        runtime = None
        with self._lock:
            runtime = self._runtimes.pop(name, None)
        if runtime is None:
            raise KeyError(f"Runtime '{name}' not found")
        runtime.stop()
        if self._registry is not None:
            try:
                self._registry.unregister(name)
            except KeyError:
                pass

    # --- Orchestration ---

    def start_all(self) -> None:
        """Start all managed runtimes."""
        with self._lock:
            runtimes = list(self._runtimes.values())
        for runtime in runtimes:
            try:
                runtime.start()
            except Exception as e:  # pragma: no cover - defensive
                logger.error("Failed to start runtime '%s': %s", runtime.name, e)

    def stop_all(self) -> None:
        """Stop all managed runtimes."""
        with self._lock:
            runtimes = list(self._runtimes.values())
        for runtime in runtimes:
            try:
                runtime.stop()
            except Exception as e:  # pragma: no cover - defensive
                logger.error("Failed to stop runtime '%s': %s", runtime.name, e)

    def shutdown(self) -> None:
        """Stop all runtimes and clear the supervisor. No threads remain."""
        self.stop_all()
        with self._lock:
            self._runtimes.clear()

    def restart(self, name: str) -> None:
        """Manually restart a FAILED runtime.

        Raises:
            KeyError: If no runtime with the given name exists.
            LifecycleTransitionError: If the runtime is not in FAILED state.
        """
        runtime = self._get_runtime(name)
        runtime.restart()

    def start(self, name: str) -> None:
        """Start a single named runtime, leaving all others untouched.

        Delegates to the existing ``AdapterRuntime.start()``; no new runtime,
        thread, or RestartPolicy is created here, and no other source is
        affected.  Idempotency and lifecycle-transition semantics are owned by
        ``AdapterRuntime.start()``.

        Raises:
            KeyError: If no runtime with the given name exists.
        """
        runtime = self._get_runtime(name)
        runtime.start()

    def stop(self, name: str) -> None:
        """Stop a single named runtime, leaving all others untouched.

        Delegates to the existing ``AdapterRuntime.stop()``; no new lifecycle
        mechanism is introduced and global shutdown semantics are unchanged.
        Only the authoritative runtime for this source is stopped.

        Raises:
            KeyError: If no runtime with the given name exists.
        """
        runtime = self._get_runtime(name)
        runtime.stop()

    # --- Introspection ---

    def get_runtime(self, name: str) -> AdapterRuntime:
        return self._get_runtime(name)

    def _get_runtime(self, name: str) -> AdapterRuntime:
        with self._lock:
            if name not in self._runtimes:
                raise KeyError(f"Runtime '{name}' not found")
            return self._runtimes[name]

    def list_runtimes(self) -> list[str]:
        with self._lock:
            return sorted(self._runtimes.keys())

    def get_health(self) -> list[dict[str, Any]]:
        """Return aggregate health snapshots for all runtimes."""
        with self._lock:
            runtimes = list(self._runtimes.values())
        return [r.health() for r in runtimes]

    def healthy_count(self) -> int:
        """Count runtimes currently in a healthy state."""
        with self._lock:
            runtimes = list(self._runtimes.values())
        return sum(
            1
            for r in runtimes
            if r.state in (AdapterState.RUNNING, AdapterState.DEGRADED)
        )

    def count(self) -> int:
        with self._lock:
            return len(self._runtimes)
