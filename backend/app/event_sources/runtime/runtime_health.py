"""
TACTICAL CORE — Production Runtime Health & Operational State
WO-014-007

A read-only operational view of the existing production source runtime.

This module COMPOSES the authoritative state already owned by the WO-013-003
AdapterSupervisor / AdapterRuntime lifecycle.  It does NOT introduce a second
source-state field, a second lifecycle authority, a second supervisor, a
second pipeline, a second dispatcher, or a second PluginManager.

Authoritative state sources (reused, never duplicated):
    * ``ProductionRuntime.started``  — whether production start() was called
    * ``AdapterSupervisor.list_runtimes()`` / ``get_runtime()`` — the
      registered source runtimes
    * ``AdapterRuntime.state``       — the WO-013-003 authoritative lifecycle
      state (STOPPED/STARTING/RUNNING/DEGRADED/STOPPING/FAILED)
    * ``AdapterRuntime.health()``    — per-source health snapshot

Canonical event path is UNAFFECTED:
    Source Adapter
        -> AdapterSupervisor / AdapterRuntime
        -> EventFactory
        -> canonical app.event.Event
        -> EventPipeline.process(event)
        -> PluginDispatcher.dispatch(event)
        -> PluginManager.deliver_event(event)
        -> RUNNING plugin.on_event(event)

This module is OBSERVABILITY/STATE only.  It never:
    * starts/stops/restarts adapters
    * changes a source lifecycle state
    * starts/stops plugins or touches plugin lifecycle
    * creates an EventPipeline / PluginDispatcher / PluginManager
    * introduces an EventBus or a legacy app.core event path
    * reconstructs Events or injects raw dicts

Classification is derived deterministically from the authoritative
AdapterState:

    RUNNING   -> running  (active, healthy)
    DEGRADED  -> degraded (active, healthy)
    FAILED    -> failed   (inactive, unhealthy)
    STOPPED / STARTING / STOPPING -> inactive (not active, unhealthy)

Aggregate runtime health is a deterministic function of the per-source
classifications with explicit precedence (justified by the real state model:
a FAILED source is worse than a DEGRADED source, which is worse than a
HEALTHY one):

    not started                 -> STOPPED
    any source FAILED           -> FAILED
    any source DEGRADED         -> DEGRADED
    all registered RUNNING      -> HEALTHY
    no sources registered       -> HEALTHY
    otherwise (transitional
      STARTING / STOPPING)      -> DEGRADED
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable

from .adapter_runtime import AdapterRuntime
from .lifecycle import AdapterState


class SourceState(str, Enum):
    """Operational classification of a single registered source.

    Derived from the authoritative AdapterState; never stored independently.
    """

    RUNNING = "running"
    DEGRADED = "degraded"
    FAILED = "failed"
    INACTIVE = "inactive"

    def __str__(self) -> str:
        return self.value


class RuntimeState(str, Enum):
    """Aggregate production-runtime health.

    Deterministic function of the per-source classifications.
    """

    STOPPED = "stopped"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILED = "failed"

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class SourceStatus:
    """Read-only snapshot of one registered source's operational state."""

    name: str
    adapter_state: str  # authoritative AdapterState value
    classification: SourceState
    active: bool
    healthy: bool
    last_error: str | None
    events_processed: int
    restarts: int


@dataclass(frozen=True)
class RuntimeHealth:
    """Read-only aggregate operational view of the production runtime."""

    started: bool
    registered: int
    running: int
    degraded: int
    failed: int
    inactive: int
    state: RuntimeState
    sources: tuple[SourceStatus, ...]

    @property
    def healthy_sources(self) -> int:
        """Number of sources currently active and healthy (running+degraded)."""
        return self.running + self.degraded


def _classify(adapter_state: AdapterState) -> SourceState:
    """Map the authoritative AdapterState to an operational classification."""
    if adapter_state == AdapterState.RUNNING:
        return SourceState.RUNNING
    if adapter_state == AdapterState.DEGRADED:
        return SourceState.DEGRADED
    if adapter_state == AdapterState.FAILED:
        return SourceState.FAILED
    return SourceState.INACTIVE


def _aggregate(
    started: bool,
    classifications: Iterable[SourceState],
) -> RuntimeState:
    """Deterministic aggregate health from per-source classifications."""
    if not started:
        return RuntimeState.STOPPED
    states = list(classifications)
    if any(s == SourceState.FAILED for s in states):
        return RuntimeState.FAILED
    if any(s == SourceState.DEGRADED for s in states):
        return RuntimeState.DEGRADED
    if not states:
        return RuntimeState.HEALTHY
    if all(s == SourceState.RUNNING for s in states):
        return RuntimeState.HEALTHY
    # Started but some sources are in a transitional STARTING/STOPPING state.
    return RuntimeState.DEGRADED


def runtime_health(runtime: Any) -> RuntimeHealth:
    """Return the read-only operational state of a production runtime.

    Args:
        runtime: A ``ProductionRuntime`` (WO-014-004).  Only its public
            ``started`` attribute and its ``supervisor`` (WO-013-003
            AdapterSupervisor) are read.

    Returns:
        A ``RuntimeHealth`` snapshot composed from the authoritative
        AdapterRuntime state.  No state is created or mutated.
    """
    started: bool = bool(runtime.started)
    supervisor = runtime.supervisor
    names = sorted(supervisor.list_runtimes())

    sources: list[SourceStatus] = []
    classifications: list[SourceState] = []
    running = degraded = failed = inactive = 0

    for name in names:
        rt: AdapterRuntime = supervisor.get_runtime(name)
        adapter_state: AdapterState = rt.state
        classification = _classify(adapter_state)
        health = rt.health()

        if classification == SourceState.RUNNING:
            running += 1
        elif classification == SourceState.DEGRADED:
            degraded += 1
        elif classification == SourceState.FAILED:
            failed += 1
        else:
            inactive += 1
        classifications.append(classification)

        sources.append(
            SourceStatus(
                name=name,
                adapter_state=str(adapter_state),
                classification=classification,
                active=adapter_state
                in (AdapterState.RUNNING, AdapterState.DEGRADED),
                healthy=adapter_state
                in (AdapterState.RUNNING, AdapterState.DEGRADED),
                last_error=health.get("last_error"),
                events_processed=int(health.get("events_processed", 0) or 0),
                restarts=int(health.get("restarts", 0) or 0),
            )
        )

    return RuntimeHealth(
        started=started,
        registered=len(sources),
        running=running,
        degraded=degraded,
        failed=failed,
        inactive=inactive,
        state=_aggregate(started, classifications),
        sources=tuple(sources),
    )
