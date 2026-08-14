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

Failure model (corrected per independent audit B2/B3/B4/M1):

  read_events() failure (recoverable source/read failure):
      RUNNING -> DEGRADED
      log error
      retry in the SAME runtime thread
      does NOT consume the restart budget
      does NOT force FAILED
      on a later successful read -> DEGRADED -> RUNNING

  runtime-level failure (adapter.start() failure, or an unexpected
  exception escaping the polling loop):
      RUNNING/DEGRADED -> FAILED
      consume ONE restart-budget unit
      if budget remains -> FAILED -> STARTING -> create a NEW thread
      if budget exhausted -> remain FAILED (manual recovery via
      supervisor.restart(name))

The lifecycle state machine is authoritative: _set_state() never
force-assigns an illegal state (B2). No fallback path bypasses it.
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
        self._started_at: float | None = None
        self._events_processed: int = 0
        self._consecutive_failures: int = 0

    # --- Public lifecycle ---

    def start(self) -> None:
        """Start the runtime.

        Transitions STOPPED -> STARTING -> RUNNING.
        Idempotent for already-active states (STARTING/RUNNING/DEGRADED are
        no-ops). FAILED must be recovered via restart(), not start(). Does
        not start a runtime that is currently stopping.
        """
        with self._lock:
            if self._state in (
                AdapterState.STARTING,
                AdapterState.RUNNING,
                AdapterState.DEGRADED,
            ):
                return
            if self._state == AdapterState.STOPPING:
                logger.warning(
                    "Runtime '%s' is stopping; refusing to start concurrently",
                    self._name,
                )
                return
            if self._state == AdapterState.FAILED:
                raise LifecycleTransitionError(
                    f"Runtime '{self._name}' is FAILED; "
                    "use restart() for manual recovery"
                )
            # STOPPED -> STARTING
            self._set_state(AdapterState.STARTING)
            self._restart_policy.reset()
            self._stop_event.clear()
            self._spawn_thread()

    def stop(self) -> None:
        """Stop the runtime.

        Transitions RUNNING/DEGRADED -> STOPPING -> STOPPED.
        Idempotent and thread-safe. Always joins the runtime thread so no
        background thread is left behind. Never force-assigns state.
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
            # Reach STOPPED through a legal path regardless of the state the
            # thread left behind (STARTING -> STOPPED; RUNNING/DEGRADED ->
            # STOPPING -> STOPPED; STOPPING -> STOPPED; FAILED -> STOPPED).
            if self._state in (AdapterState.RUNNING, AdapterState.DEGRADED):
                self._set_state(AdapterState.STOPPING)
            self._set_state(AdapterState.STOPPED)

    def restart(self) -> None:
        """Manual restart of a FAILED runtime.

        Transitions FAILED -> STARTING -> RUNNING (new thread). Manual
        recovery resets the restart budget.
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
            self._spawn_thread()

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

        ``uptime`` is an observational projection derived from the runtime's
        own ``_started_at`` timestamp (owned by this runtime, matching the
        existing ``_last_success_at`` pattern).  It introduces no timer,
        thread, scheduler, or additional lifecycle owner.
        """
        with self._lock:
            uptime = (
                (time.time() - self._started_at)
                if self._started_at is not None
                else 0.0
            )
            return {
                "name": self._name,
                "state": str(self._state),
                "healthy": self._state in (AdapterState.RUNNING, AdapterState.DEGRADED),
                "restarts": self._restarts,
                "restart_budget_remaining": self._restart_policy.remaining,
                "last_error": self._last_error,
                "last_success_at": self._last_success_at,
                "started_at": self._started_at,
                "uptime": max(0.0, uptime),
                "events_processed": self._events_processed,
            }

    # --- Internal ---

    def _set_state(self, target: AdapterState) -> None:
        """Set state with transition validation.

        The lifecycle state machine is authoritative. If the transition is
        illegal, LifecycleTransitionError propagates — the state is NEVER
        force-assigned (audit B2).
        """
        self._state = transition(self._state, target)

    def _spawn_thread(self) -> None:
        """Create and start a brand-new runtime thread."""
        self._started_at = time.time()
        self._thread = threading.Thread(
            target=self._run_loop,
            name=f"adapter-runtime-{self._name}",
            daemon=True,
        )
        self._thread.start()

    def _run_loop(self) -> None:
        """Main polling loop. Runs on the dedicated runtime thread."""
        restarted = False
        try:
            try:
                self._adapter.start()
            except Exception as e:
                restarted = self._handle_runtime_failure(f"adapter.start failed: {e}")
                return

            with self._lock:
                if self._state == AdapterState.STARTING:
                    self._set_state(AdapterState.RUNNING)
                self._last_success_at = time.time()

            try:
                self._poll_forever()
            except Exception as e:
                # An unexpected exception escaping the polling loop is a
                # runtime-level failure -> bounded auto-restart (audit B4).
                restarted = self._handle_runtime_failure(
                    f"runtime loop crashed: {e}"
                )
        finally:
            # Only stop the adapter when we are NOT handing off to a newly
            # spawned restart thread (avoids the old-thread stop racing the
            # new-thread start).
            if not restarted:
                try:
                    self._adapter.stop()
                except Exception as e:  # pragma: no cover - defensive
                    logger.error(
                        "Runtime '%s' adapter stop error: %s", self._name, e
                    )

    def _poll_forever(self) -> None:
        """Read events and forward them until stop is signalled."""
        while not self._stop_event.is_set():
            try:
                raw_events = self._adapter.read_events()
            except Exception as e:
                # Recoverable read failure (audit B3): DEGRADED, log, retry in
                # the SAME thread. Does NOT consume the restart budget and does
                # NOT force FAILED.
                self._record_error(f"read_events failed: {e}")
                self._mark_degraded()
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

    def _handle_runtime_failure(self, message: str) -> bool:
        """Handle a runtime-level failure.

        Transitions to FAILED. If restart budget remains, performs a REAL
        automatic restart by creating a brand-new runtime thread; otherwise
        the runtime stays FAILED (manual recovery only).

        Returns:
            True if a new restart thread was spawned, False if the runtime
            stayed FAILED (budget exhausted or shutdown in progress).
        """
        with self._lock:
            self._last_error = message
            self._set_state(AdapterState.FAILED)

        if self._restart_policy.exhausted or self._stop_event.is_set():
            logger.error("Runtime '%s' FAILED: %s", self._name, message)
            return False

        # Consume one budget unit for THIS actual restart (off-by-one safe:
        # with max_restarts=N, N restarts occur before the (N+1)th failure).
        self._restart_policy.record_failure()
        with self._lock:
            self._restarts += 1
            self._set_state(AdapterState.STARTING)
            self._spawn_thread()
        logger.warning(
            "Runtime '%s' auto-restarting (attempt %d): %s",
            self._name,
            self._restart_policy.restart_count,
            message,
        )
        return True
