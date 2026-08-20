"""WO-014-025 — Deterministic Projection Catch-up Driver.

A deliberately-simple, deterministic catch-up mechanism over the durable
canonical Event log, projecting each un-checkpointed Event into Entity state
and advancing a durable checkpoint only after successful projection.

Algorithm (WO-014-025 §E):
  1. Read the durable checkpoint (last_seq).
  2. Query durable Events with ``seq > last_seq`` ordered by ``seq ASC``.
  3. Process each Event sequentially: project entity.
  4. ONLY after successful entity projection, advance the checkpoint to the
     Event's seq (and record its event_id).
  5. If projection fails, the checkpoint MUST NOT advance; the durable Event is
     left untouched; a later catch-up retries from the same checkpoint.
  6. Idempotent: reprojecting an already-projected Event is safe because
     Entity projection is deterministic + idempotent (upsert by Entity.id).

Invariants (WO-014-025):
  * EVENT PERSIST -> ENTITY PROJECTION/COMMIT -> CHECKPOINT ADVANCE/COMMIT.
  * The checkpoint NEVER advances before successful entity projection.
  * A crash between entity commit and checkpoint commit is safe: the checkpoint
    lags and deterministic idempotent reprojection repeats the event.
  * No queues, no background workers, no event bus, no DLQ, no concurrency.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Optional

from app.event_repository.durable.sqlalchemy_event_repository import (
    SQLAlchemyEventRepository,
)
from app.projection.checkpoint import ProjectionCheckpointRepository

logger = logging.getLogger(__name__)

# Default projection name for the current single-projection architecture.
DEFAULT_PROJECTION = "entity"


@dataclass
class CatchUpResult:
    """Deterministic outcome of one catch-up pass."""

    processed: int = 0
    failed: int = 0
    checkpoint_seq: int = 0
    last_event_id: Optional[str] = None

    @property
    def advanced_to(self) -> int:
        """The checkpoint seq after this pass."""
        return self.checkpoint_seq


class ProjectionCatchUp:
    """Deterministic sequential catch-up of durable Events into Entity state."""

    def __init__(
        self,
        event_repository: SQLAlchemyEventRepository,
        checkpoint_repository: ProjectionCheckpointRepository,
        projection: Callable[[Any], None],
        projection_name: str = DEFAULT_PROJECTION,
    ) -> None:
        self._events = event_repository
        self._checkpoints = checkpoint_repository
        self._projection = projection
        self._projection_name = projection_name

    def run(self) -> CatchUpResult:
        """Execute one deterministic catch-up pass.

        Returns:
            A :class:`CatchUpResult` summarising processed/failed events and the
            resulting checkpoint seq.
        """
        last_seq = self._checkpoints.get_last_seq(self._projection_name)
        # (seq, canonical Event) pairs, ordered seq ASC.
        pending = self._events.iter_after_seq(last_seq)

        result = CatchUpResult(checkpoint_seq=last_seq)
        for seq, event in pending:
            try:
                # 1. Project entity (deterministic + idempotent).
                self._projection(event)
                # 2. Advance checkpoint ONLY after successful projection.
                self._checkpoints.advance(
                    seq,
                    event.event_id,
                    self._projection_name,
                )
                result.checkpoint_seq = seq
                result.last_event_id = event.event_id
                result.processed += 1
                last_seq = seq
            except Exception:
                logger.exception(
                    "ProjectionCatchUp: projection failed for event_id=%s seq=%s — "
                    "checkpoint NOT advanced; event left durable for retry.",
                    event.event_id,
                    seq,
                )
                result.failed += 1
                break  # Deterministic: stop at first failure, retry later.

        return result
