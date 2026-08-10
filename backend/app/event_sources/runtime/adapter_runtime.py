"""
TACTICAL CORE — Adapter Runtime
WO-013-003

AdapterRuntime owns exactly ONE source adapter.

It receives its collaborators through dependency injection and coordinates
the data flow:

    adapter.read_events()
        -> raw dict
        -> IEventFactory.create_event(...)
        -> canonical Event
        -> IEventPipeline.process(event)

The runtime is protocol-agnostic: it only depends on interfaces
(IEventSourceAdapter, IEventFactory, IEventPipeline). It knows nothing
about Signal, MQTT, Telegram, Radio, REST, ATAK or any concrete source.

Threading model: one AdapterRuntime == one dedicated thread. No asyncio,
no shared worker pool, no global executor.

Failure isolation:
    - a single malformed event is dropped and processing continues
    - a single bad event does NOT restart the adapter
    - runtime-level failures (start/poll-loop) drive bounded auto-restart
    - when the restart budget is exhausted the runtime -> FAILED (no
      automatic infinite restart; recovery is manual via supervisor.restart)
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

from ..interfaces.i_event_source_adapter import IEventSourceAdapter
from ..interfaces.i_event_factory import IEventFactory
from ...event_pipeline.interfaces.i_event_pipeline import IEventPipeline
from .lifecycle import AdapterState, LifecycleTransitionError, transition
from .restart_policy import RestartPolicy

logger = logging.getLogger(__name__)


class AdapterRuntime:
    """Executes a single source adapter and forwards canonical events.

    Args:
        adapter: The source adapter to run.
        factory: Event factory used to convert raw data into canonical Events.
        pipeline: Event processing pipeline (WO-012) to receive canonical Events.
        name: Optional runtime name. Defaults to adapter.source_name().
        poll_interval: Seconds to sleep between polling loops.
        restart_policy: Bounded restart policy. A default finite policy is used
            when none is provided.
        stop_timeout: Seconds to wait for the runtime thread to join on stop.
    """

    def __init__(
        self,
        adapter: IEventSourceAdapter,
        factory: IEventFactory,
        pipeline: IEventPipeline,
        name: str | None = None,
        poll_interval: float = 0.1,
        restart_policy: RestartPolicy | None = None,
        stop_timeout: float = 5.0,
    ) -> None:
        self._adapter = adapter
        self._factory = factory
        self._pipeline = pipeline
        self._name = name or adapter.source_name()
        self._poll_interval = max(0.0, poll_interval)
        self._restart_policy = restart_policy or RestartPolicy()
        self._stop_timeout = max(0.0, stop_timeout)

        self._state = AdapterState.STOPPED
        self._lock = threading.RLock()
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

        # health snapshot
        self._restarts: int = 0
        self._last_error: str | None = None
        self._last_success_at: float | None = None
        self._events_processed: int = 0
        self._consecutive_failures: int = 0

    # --- Public lifecycle ---

    def start(self) -> None:
        """Start the runtime.

        Transitions STOPPED -> STARTING -> RUNNING.
        Idempotent: starting an already-running runtime is a no-op.
        """
        with self._lock:
            if self._state in (AdapterState.STARTING, AdapterState.RUNNING):
                return
            if self._state == AdapterState.STOPPING:
                logger.warning(
                    "Runtime '%s' is stopping; refusing to start concurrently",
                    self._name,
                )
                return
            # FAILED and STOPPED both pass through STARTING on (re)start
            self._set_state(AdapterState.STARTING)
            self._restart_policy.reset()
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._run_loop,
                name=f"adapter-runtime-{self._name}",
                daemon=True,
            )
            self._thread.start()

    def stop(self) -> None:
        """Stop the runtime.

        Transitions RUNNING/DEGRADED -> STOPPING -> STOPPED.
        Idempotent and thread-safe. Always joins the runtime thread so no
        background thread is left behind.
        """
        thread: threading.Thread | None = None
        with self._lock:
            if self._state == AdapterState.STOPPED:
                return
            if self._state in (AdapterState.RUNNING, AdapterState.DEGRADED):
                self._set_state(AdapterState.STOPPING)
            self._stop_event.set()
            thread = self._thread

        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=self._stop_timeout)
            if thread.is_alive():
                logger.warning(
                    "Runtime '%s' thread did not stop within timeout", self._name
                )

        with self._lock:
            # stop adapter (idempotent)
            try:
                self._adapter.stop()
            except Exception as e:  # pragma: no cover - defensive
                logger.error("Runtime '%s' adapter stop error: %s", self._name, e)
            self._thread = None
            self._set_state(AdapterState.STOPPED)

    def restart(self) -> None:
        """Manual restart of a FAILED runtime.

        Transitions FAILED -> STARTING -> RUNNING.
        """
        with self._lock:
            if self._state != AdapterState.FAILED:
                raise LifecycleTransitionError(
                    f"Runtime '{self._name}' is in state {self._state}; "
                    "manual restart is only allowed from FAILED"
                )
            self._restart_policy.reset()
            self._set_state(AdapterState.STARTING)
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._run_loop,
                name=f"adapter-runtime-{self._name}",
                daemon=True,
            )
            self._thread.start()

    # --- Introspection ---

    @property
    def name(self) -> str:
        return self._name

    @property
    def state(self) -> AdapterState:
        with self._lock:
            return self._state

    def health(self) -> dict[str, Any]:
        """Return a structured health snapshot.

        This is runtime health, distinct from IEventSourceAdapter.health()
        (which returns a plain bool and is left unchanged).
        """
        with self._lock:
            return {
                "name": self._name,
                "state": str(self._state),
                "healthy": self._state in (AdapterState.RUNNING, AdapterState.DEGRADED),
                "restarts": self._restarts,
                "restart_budget_remaining": self._restart_policy.remaining,
                "last_error": self._last_error,
                "last_success_at": self._last_success_at,
                "events_processed": self._events_processed,
            }

    # --- Internal ---

    def _set_state(self, target: AdapterState) -> None:
        """Set state with transition validation."""
        try:
            self._state = transition(self._state, target)
        except LifecycleTransitionError:
            # Allow forced cleanup transitions during shutdown
            logger.warning(
                "Runtime '%s' forced state %s -> %s",
                self._name,
                self._state,
                target,
            )
            self._state = target

    def _run_loop(self) -> None:
        """Main polling loop. Runs on the dedicated runtime thread."""
        logger.info("Runtime '%s' starting adapter", self._name)
        try:
            self._adapter.start()
        except Exception as e:
            self._record_failure(f"adapter.start failed: {e}")
            return

        with self._lock:
            if self._state == AdapterState.STARTING:
                self._set_state(AdapterState.RUNNING)
            self._last_success_at = time.time()

        try:
            self._poll_forever()
        finally:
            self._adapter.stop()

    def _poll_forever(self) -> None:
        """Read events and forward them until stop is signalled."""
        while not self._stop_event.is_set():
            try:
                raw_events = self._adapter.read_events()
            except Exception as e:
                self._record_error(f"read_events failed: {e}")
                self._restart_policy.record_failure()
                self._mark_degraded()
                if self._restart_policy.exhausted:
                    self._record_failure(f"restart budget exhausted: {e}")
                    return
                # sleep then continue polling (DEGRADED)
                self._restart_policy.wait_delay()
                continue

            # healthy read: reset consecutive-failure counter and health timer
            self._consecutive_failures = 0
            self._restart_policy.record_health()
            with self._lock:
                if self._state == AdapterState.DEGRADED:
                    self._set_state(AdapterState.RUNNING)
                self._last_success_at = time.time()

            for raw in raw_events:
                if self._stop_event.is_set():
                    return
                self._process_raw(raw)

            if self._poll_interval > 0:
                self._stop_event.wait(self._poll_interval)

    def _process_raw(self, raw: dict[str, Any]) -> None:
        """Convert a single raw event and forward it to the pipeline.

        Errors are isolated per event: a bad event is logged, dropped, and
        processing continues. The runtime stays alive.
        """
        try:
            event = self._factory.create_event(
                raw_data=raw,
                source_name=self._name,
            )
        except Exception as e:
            logger.warning(
                "Runtime '%s' dropped event: factory error: %s", self._name, e
            )
            return

        try:
            self._pipeline.process(event)
        except Exception as e:
            logger.warning(
                "Runtime '%s' dropped event: pipeline error: %s", self._name, e
            )
            return

        with self._lock:
            self._events_processed += 1

    def _mark_degraded(self) -> None:
        with self._lock:
            if self._state == AdapterState.RUNNING:
                self._set_state(AdapterState.DEGRADED)

    def _record_error(self, message: str) -> None:
        self._consecutive_failures += 1
        with self._lock:
            self._last_error = message

    def _record_failure(self, message: str) -> None:
        """Record a runtime-level failure. Drives bounded restart."""
        self._restarts += 1
        with self._lock:
            self._last_error = message
            self._set_state(AdapterState.FAILED)
        logger.error("Runtime '%s' FAILED: %s", self._name, message)
