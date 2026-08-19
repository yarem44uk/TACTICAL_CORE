"""WO-014-024 — Projection Observability (G3).

A deterministic, thread-safe health/observability signal for the canonical
Event -> Entity projection.

The signal reports, at minimum:
  * last successfully projected ``event_id``
  * current Entity count (derived live from the authoritative EntityManager)
  * projection failure count

Design / ownership rules:
  * Observability is DIAGNOSTIC only.  It is NEVER authoritative over Event
    persistence.  A projection failure does NOT fail Event persistence.
  * This recorder wraps the projection callable.  On success it records the
    projected event_id and re-computes the Entity count.  On failure it
    increments the failure counter and RE-RAISES, so the EventPipeline keeps
    its existing WO-014-023 best-effort semantics (the pipeline's own
    try/except swallows the projection exception without touching the
    already-durable Event).
  * No second database / session / persistence owner is introduced.
  * Counters are deterministic and safe under repeated / concurrent Events
    (guarded by a lock).

The signal is also surfaced through the existing global HealthManager as the
``entity_projection`` component, distinguishing projection health from event
persistence health and source runtime health.
"""

from __future__ import annotations

import threading
from typing import Any, Callable, Dict, Optional

from app.core.health.health import HealthManager, HealthStatus, get_health_manager
from app.entity_manager.interfaces.i_entity_manager import IEntityManager

HEALTH_COMPONENT = "entity_projection"


class ProjectionObservability:
    """Tracks projection health signals around a projection callable."""

    def __init__(
        self,
        entity_manager: IEntityManager,
        health_manager: Optional[HealthManager] = None,
    ) -> None:
        self._entity_manager = entity_manager
        self._health_manager = health_manager or get_health_manager()
        self._lock = threading.Lock()
        self._last_projected_event_id: Optional[str] = None
        self._projection_failure_count: int = 0

    # ------------------------------------------------------------------
    # Projection wrapping
    # ------------------------------------------------------------------

    def wrap(self, projection: Callable[[Any], None]) -> Callable[[Any], None]:
        """Return a projection callable that also records observability.

        The wrapped callable preserves the original projection's control flow:
        on failure it re-raises so the EventPipeline's best-effort handling
        (WO-014-023) remains unchanged.
        """

        def observed(event: Any) -> None:
            try:
                projection(event)
            except Exception:
                self._record_failure()
                raise
            self._record_success(getattr(event, "event_id", None))

        return observed

    # ------------------------------------------------------------------
    # Internal recorders
    # ------------------------------------------------------------------

    def _record_success(self, event_id: Any) -> None:
        with self._lock:
            self._last_projected_event_id = str(event_id) if event_id is not None else None
        self._publish_health()

    def _record_failure(self) -> None:
        with self._lock:
            self._projection_failure_count += 1
        self._publish_health()

    def _publish_health(self) -> None:
        snapshot = self.snapshot()
        failing = self._projection_failure_count > 0
        status = HealthStatus.WARNING if failing else HealthStatus.HEALTHY
        message = (
            "projection failures detected"
            if failing
            else "projection healthy"
        )
        try:
            self._health_manager.update_status(
                HEALTH_COMPONENT,
                status,
                message=message,
                details=snapshot,
            )
        except Exception:
            # Observability must never break the pipeline or persistence.
            pass

    # ------------------------------------------------------------------
    # Read API
    # ------------------------------------------------------------------

    @property
    def last_projected_event_id(self) -> Optional[str]:
        with self._lock:
            return self._last_projected_event_id

    @property
    def projection_failure_count(self) -> int:
        with self._lock:
            return self._projection_failure_count

    def entity_count(self) -> int:
        """Current Entity count derived live from the authoritative owner."""
        return len(self._entity_manager.list_entities())

    def snapshot(self) -> Dict[str, Any]:
        """Deterministic snapshot of the projection health signal."""
        with self._lock:
            return {
                "last_projected_event_id": self._last_projected_event_id,
                "entity_count": self.entity_count(),
                "projection_failure_count": self._projection_failure_count,
            }
