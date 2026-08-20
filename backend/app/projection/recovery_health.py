"""WO-014-027 — Production Projection / Recovery Observability.

A deterministic, read-only production-facing health/state contract over the
durable Event -> Entity projection and its deterministic catch-up recovery
(WO-014-025 / WO-014-026).

The system must be able to answer, from the production runtime boundary:

    1. What is the current projection checkpoint?
    2. Is there a durable projection backlog?
    3. Has the latest catch-up/recovery succeeded?
    4. Did the latest recovery attempt fail?
    5. What is the latest recovery error/state, if any?
    6. How many events remain to be projected?
    7. Is the projection currently healthy, degraded, or recovering?

This contract reuses the EXISTING authoritative state objects and composes
them deterministically.  It does NOT introduce a second persistence plane, a
second checkpoint store, a second DB/session owner, or a second health owner.

Ownership / design rules:
  * The durable projection checkpoint (``ProjectionCheckpointRepository``) is
    the canonical source of projection progress.
  * The durable canonical Event log (``SQLAlchemyEventRepository.max_seq``) is
    the canonical source of "how far the log has advanced".
  * Backlog = ``max(0, latest_seq - checkpoint_seq)`` — events durably
    persisted but not yet projected.
  * The latest catch-up/recovery outcome is captured from each
    ``ProjectionCatchUp.run()`` invocation (recorded by the production
    composition wrapper, so BOTH the startup catch-up and any explicit
    catch-up are observed).  It is an in-memory, thread-safe diagnostic; the
    durable checkpoint remains the authoritative source of projection
    progress.
  * HEALTH INSPECTION IS READ-ONLY: it never advances the checkpoint, never
    persists events, never projects entities, and never mutates projection
    state.  It does NOT gate Event persistence (event persistence remains the
    source of truth and is independent of projection success).
  * No second ``create_engine`` / ``sessionmaker`` / DB owner is introduced.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional

from app.projection.checkpoint import ProjectionCheckpointRepository
from app.projection.catch_up import CatchUpResult


class RecoveryStatus(str, Enum):
    """Outcome of the most recent catch-up/recovery pass."""

    NEVER_RUN = "never_run"
    SUCCEEDED = "succeeded"
    FAILED = "failed"

    def __str__(self) -> str:
        return self.value


class ProjectionRecoveryState(str, Enum):
    """Deterministic operational classification of the projection/recovery
    mechanism, derived from the durable checkpoint, the durable event log and
    the latest recovery outcome."""

    HEALTHY = "healthy"
    RECOVERING = "recovering"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class ProjectionRecoveryHealthSnapshot:
    """Read-only deterministic snapshot of the projection/recovery health."""

    state: str  # ProjectionRecoveryState value
    checkpoint_seq: int
    checkpoint_event_id: Optional[str]
    latest_seq: int
    backlog_count: int
    recovery_status: str  # RecoveryStatus value
    last_recovery_processed: int
    last_recovery_failed: int
    last_recovery_error: Optional[str]
    last_recovery_at: Optional[str]
    persistence_active: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "state": self.state,
            "checkpoint_seq": self.checkpoint_seq,
            "checkpoint_event_id": self.checkpoint_event_id,
            "latest_seq": self.latest_seq,
            "backlog_count": self.backlog_count,
            "recovery_status": self.recovery_status,
            "last_recovery_processed": self.last_recovery_processed,
            "last_recovery_failed": self.last_recovery_failed,
            "last_recovery_error": self.last_recovery_error,
            "last_recovery_at": self.last_recovery_at,
            "persistence_active": self.persistence_active,
        }


class ProjectionRecoveryHealth:
    """Deterministic, read-only observability of the projection/recovery
    mechanism.

    Args:
        checkpoint_repository: The durable projection checkpoint repository
            (single canonical DB owner).
        event_repository: The durable canonical event repository exposing
            ``max_seq()`` (single canonical DB owner).  May be ``None`` when
            persistence is not active; the health contract then reports the
            projection state as ``UNAVAILABLE`` (persistence inactive) rather
            than inventing state.
        projection_name: The projection checkpoint name (``"entity"`` by
            default, matching the current single-projection architecture).
    """

    def __init__(
        self,
        checkpoint_repository: Optional[ProjectionCheckpointRepository] = None,
        event_repository: Optional[Any] = None,
        projection_name: str = "entity",
    ) -> None:
        self._checkpoints = checkpoint_repository
        self._events = event_repository
        self._projection_name = projection_name
        self._lock = threading.Lock()
        # In-memory, thread-safe record of the latest recovery outcome.  The
        # durable checkpoint remains the authoritative source of projection
        # progress; this only mirrors "what did the last recovery attempt do".
        self._recovery_status: RecoveryStatus = RecoveryStatus.NEVER_RUN
        self._last_processed: int = 0
        self._last_failed: int = 0
        self._last_error: Optional[str] = None
        self._last_at: Optional[datetime] = None

    # ------------------------------------------------------------------
    # Recovery outcome recording (called by the production catch-up wrapper
    # after each ProjectionCatchUp.run(); NOT on the pipeline hot path)
    # ------------------------------------------------------------------

    def record_recovery(
        self,
        result: Optional[CatchUpResult] = None,
        error: Optional[BaseException] = None,
    ) -> None:
        """Record the outcome of a catch-up/recovery pass.

        Called once per ``ProjectionCatchUp.run()`` invocation.  ``result`` is
        the returned ``CatchUpResult`` on success; ``error`` is set when the
        catch-up pass itself raised before returning a result.

        This is in-memory only — it NEVER opens a DB session, never advances
        the checkpoint, never persists events, and never projects entities.
        """
        with self._lock:
            self._last_at = datetime.now(timezone.utc)
            if error is not None:
                self._recovery_status = RecoveryStatus.FAILED
                self._last_processed = 0
                self._last_failed = 0
                self._last_error = f"{type(error).__name__}: {error}"
                return
            if result is None:
                self._recovery_status = RecoveryStatus.SUCCEEDED
                self._last_processed = 0
                self._last_failed = 0
                self._last_error = None
                return
            self._last_processed = int(getattr(result, "processed", 0) or 0)
            self._last_failed = int(getattr(result, "failed", 0) or 0)
            self._last_error = None
            self._recovery_status = (
                RecoveryStatus.FAILED
                if self._last_failed > 0
                else RecoveryStatus.SUCCEEDED
            )

    # ------------------------------------------------------------------
    # Read-only state derivation
    # ------------------------------------------------------------------

    def _durable_state(self) -> tuple:
        """Read the durable checkpoint seq + latest durable event seq.

        Returns ``(checkpoint_seq, checkpoint_event_id, latest_seq)``.  When
        persistence is inactive or a read fails, returns ``(0, None, 0)`` so
        the contract degrades to ``UNAVAILABLE`` rather than raising on the
        read path.
        """
        checkpoint_seq = 0
        checkpoint_event_id: Optional[str] = None
        latest_seq = 0
        try:
            if self._checkpoints is not None:
                checkpoint_seq = self._checkpoints.get_last_seq(
                    self._projection_name
                )
                checkpoint_event_id = self._checkpoints.get_last_event_id(
                    self._projection_name
                )
        except Exception:
            pass
        try:
            if self._events is not None and hasattr(self._events, "max_seq"):
                latest_seq = int(self._events.max_seq() or 0)
        except Exception:
            pass
        return checkpoint_seq, checkpoint_event_id, latest_seq

    def persistence_active(self) -> bool:
        """Whether the durable persistence/checkpoint plane is available.

        True only when both a checkpoint repository and a durable event
        repository are present (i.e. the production durable composition is
        active).  When False the projection state is ``UNAVAILABLE``.
        """
        return self._checkpoints is not None and self._events is not None

    def checkpoint_seq(self) -> int:
        return self._durable_state()[0]

    def latest_seq(self) -> int:
        return self._durable_state()[2]

    def backlog_count(self) -> int:
        """Number of durably persisted Events not yet projected."""
        checkpoint_seq, _, latest_seq = self._durable_state()
        return max(0, int(latest_seq) - int(checkpoint_seq))

    def recovery_status(self) -> RecoveryStatus:
        with self._lock:
            return self._recovery_status

    def last_recovery_error(self) -> Optional[str]:
        with self._lock:
            return self._last_error

    def classify(self) -> ProjectionRecoveryState:
        """Deterministic healthy / degraded / recovering / unavailable state.

        Precedence:
          * UNAVAILABLE  — durable persistence plane is not active.
          * DEGRADED     — the latest recovery attempt failed (checkpoint is
                           behind and could not advance due to a projection
                           failure).
          * HEALTHY      — zero backlog (checkpoint == latest durable seq).
          * RECOVERING   — backlog > 0 (events durably persisted but not yet
                           projected; recovery is in progress / pending).
        """
        if not self.persistence_active():
            return ProjectionRecoveryState.UNAVAILABLE
        with self._lock:
            status = self._recovery_status
        checkpoint_seq, _, latest_seq = self._durable_state()
        backlog = max(0, int(latest_seq) - int(checkpoint_seq))
        if status == RecoveryStatus.FAILED:
            return ProjectionRecoveryState.DEGRADED
        if backlog == 0:
            return ProjectionRecoveryState.HEALTHY
        return ProjectionRecoveryState.RECOVERING

    def snapshot(self) -> ProjectionRecoveryHealthSnapshot:
        """Deterministic read-only snapshot of the projection/recovery state.

        Safe to inspect at any time: it never mutates projection state, never
        advances the checkpoint, never persists events, never projects
        entities, and never opens a second DB owner.
        """
        checkpoint_seq, checkpoint_event_id, latest_seq = self._durable_state()
        with self._lock:
            status = self._recovery_status
            processed = self._last_processed
            failed = self._last_failed
            error = self._last_error
            last_at = self._last_at

        backlog = max(0, int(latest_seq) - int(checkpoint_seq))
        state = self.classify()

        return ProjectionRecoveryHealthSnapshot(
            state=str(state),
            checkpoint_seq=checkpoint_seq,
            checkpoint_event_id=checkpoint_event_id,
            latest_seq=latest_seq,
            backlog_count=backlog,
            recovery_status=str(status),
            last_recovery_processed=processed,
            last_recovery_failed=failed,
            last_recovery_error=error,
            last_recovery_at=(
                last_at.isoformat() if last_at is not None else None
            ),
            persistence_active=self.persistence_active(),
        )
