"""WO-014-024/025 — Projection Observability (G3).

A deterministic, thread-safe health/observability signal for the canonical
Event -> Entity projection.

The signal reports, at minimum:
  * last successfully projected ``event_id``
  * current Entity count (derived live from the authoritative EntityManager)
  * projection failure count

WO-014-025 change: ``last_projected_event_id`` is now a READ-THROUGH of the
durable projection checkpoint, not an independent source of truth. After a
process restart it is recovered from the durable checkpoint, so the signal is
consistent with durable projection progress. ``projection_failure_count``
remains an in-memory diagnostic counter for the current process.

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
from app.projection.checkpoint import ProjectionCheckpointRepository

HEALTH_COMPONENT = "entity_projection"


class ProjectionObservability:
    """Tracks projection health signals around a projection callable."""

    def __init__(
        self,
        entity_manager: IEntityManager,
        checkpoint_repository: Optional[ProjectionCheckpointRepository] = None,
        health_manager: Optional[HealthManager] = None,
    ) -> None:
        self._entity_manager = entity_manager
        self._checkpoint = checkpoint_repository
        self._health_manager = health_manager or get_health_manager()
        self._lock = threading.Lock()
        # In-memory fallback/cache for last_projected_event_id. The AUTHORITATIVE
        # source is the durable projection checkpoint (WO-014-025 read-through);
        # on construction we recover the durable value so the signal is consistent
        # after a process restart. The hot path (inside pipeline.process) uses the
        # non-blocking in-memory cache — it must NOT open a DB session mid-pipeline
        # (would deadlock the shared owner).
        self._last_projected_event_id: Optional[str] = self._recover_last_event_id()
        self._projection_failure_count: int = 0
        # WO-014-025 deadlock gate: the synchronous projection-observability HOT
        # PATH (pipeline.process -> observed -> _record_success -> _publish_health
        # -> snapshot) MUST perform ZERO database access. `entity_count()` is a
        # durable/diagnostic value that would otherwise open a DB session
        # mid-pipeline (deadlock on the shared :memory: StaticPool connection).
        # We therefore keep an in-memory entity count + seen-entity-id set,
        # recovered ONCE at construction (off the hot path) and updated
        # in-memory on each successful projection. Explicit off-hot-path callers
        # may still query the live durable count via `durable_entity_count()`.
        self._cached_entity_count: int = 0
        self._seen_entity_ids: set = set()
        self._recover_entity_state()

    def _recover_entity_state(self) -> None:
        """Recover entity count + seen ids once at construction (off hot path).

        Best-effort: any error yields an empty baseline so observability never
        breaks the pipeline. This is the ONLY DB read for entity-count purposes;
        after construction the hot path uses the in-memory cache only.
        """
        try:
            entities = self._entity_manager.list_entities()
            self._cached_entity_count = len(entities)
            self._seen_entity_ids = {
                str(e.get("entity_id")) for e in entities
            }
        except Exception:
            self._cached_entity_count = 0
            self._seen_entity_ids = set()

    def _recover_last_event_id(self) -> Optional[str]:
        """Recover the last projected event_id from the durable checkpoint.

        Called once at construction (startup recovery). Best-effort: any error
        yields ``None`` — observability must never break the pipeline.
        """
        if self._checkpoint is None:
            return None
        try:
            return self._checkpoint.get_last_event_id()
        except Exception:
            return None

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
            self._record_success(
                getattr(event, "event_id", None),
                getattr(event, "entity_id", None),
            )

        return observed

    # ------------------------------------------------------------------
    # Internal recorders
    # ------------------------------------------------------------------

    def _record_success(self, event_id: Any, entity_id: Any = None) -> None:
        with self._lock:
            self._last_projected_event_id = (
                str(event_id) if event_id is not None else None
            )
            # Update the in-memory entity count. A projection of a NEW
            # entity_id creates a new Entity (count +1); an update to an
            # already-seen entity_id does not. This is memory-only — never a DB
            # query — so it is safe on the hot path.
            if entity_id is not None:
                eid = str(entity_id)
                if eid not in self._seen_entity_ids:
                    self._seen_entity_ids.add(eid)
                    self._cached_entity_count += 1
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
        """Last successfully projected event_id (WO-014-025 read-through).

        The value is recovered from the durable projection checkpoint at
        construction (startup recovery) and updated in-memory on each successful
        projection. The hot path is non-blocking: it does NOT open a DB session
        mid-pipeline. The durable checkpoint remains the authoritative source of
        projection progress.
        """
        with self._lock:
            return self._last_projected_event_id

    def durable_checkpoint_event_id(self) -> Optional[str]:
        """Explicit durable checkpoint read (diagnostic, not on the hot path)."""
        if self._checkpoint is None:
            return None
        try:
            return self._checkpoint.get_last_event_id()
        except Exception:
            return None

    @property
    def projection_failure_count(self) -> int:
        with self._lock:
            return self._projection_failure_count

    def entity_count(self) -> int:
        """Current Entity count (in-memory, hot-path safe — no DB access).

        Recovered from the authoritative EntityManager once at construction and
        updated in-memory on each successful projection. Off-hot-path callers
        that need the live durable count may use :meth:`durable_entity_count`.
        """
        with self._lock:
            return self._cached_entity_count

    def durable_entity_count(self) -> int:
        """Live durable Entity count (explicit, off the hot path).

        Opens a DB session via the authoritative EntityManager, so this MUST
        NOT be called from ``process()``/``observed()``/``_publish_health()``.
        """
        try:
            return len(self._entity_manager.list_entities())
        except Exception:
            return self._cached_entity_count

    def snapshot(self) -> Dict[str, Any]:
        """Deterministic snapshot of the projection health signal.

        Hot-path safe: builds the snapshot from the in-memory cache only and
        performs ZERO database access. ``entity_count`` is the in-memory value;
        use :meth:`durable_entity_count` for the live durable count.
        """
        with self._lock:
            return {
                "last_projected_event_id": self._last_projected_event_id,
                "entity_count": self._cached_entity_count,
                "projection_failure_count": self._projection_failure_count,
            }
