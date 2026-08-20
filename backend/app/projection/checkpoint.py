"""WO-014-025 — Durable Projection Checkpoint.

The durable projection checkpoint is the canonical source of projection
progress. It records, per projection, the last durable event ``seq`` that has
been successfully projected, plus the corresponding canonical ``event_id``.

Ownership rules (WO-014-025):
  * The checkpoint is persisted through the single canonical
    :class:`DatabaseSessionManager` — NO second engine, NO second
    sessionmaker, NO independent DB owner.
  * The ``projection_checkpoint`` table is registered on the shared
    ``Base.metadata`` and created by the same ``create_all`` that brings up the
    durable events and entities tables.
  * Checkpoint advancement MUST NEVER precede successful entity projection
    (projection-first, checkpoint-second). The catch-up driver enforces this;
    the repository itself only persists whatever value it is asked to write.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.database.session import DatabaseSessionManager, get_session_manager


class ProjectionCheckpoint(Base):
    """Durable record of one projection's progress."""

    __tablename__ = "projection_checkpoint"

    # The single projection name for the current architecture ("entity").
    projection_name: Mapped[str] = mapped_column(String(64), primary_key=True)
    last_seq: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_event_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class ProjectionCheckpointRepository:
    """Durable repository for the projection checkpoint."""

    def __init__(
        self, session_manager: Optional[DatabaseSessionManager] = None
    ) -> None:
        self._session_manager = session_manager

    @property
    def session_manager(self) -> DatabaseSessionManager:
        if self._session_manager is None:
            return get_session_manager()
        return self._session_manager

    def initialize(self) -> None:
        """Ensure the checkpoint table exists via the shared metadata."""
        Base.metadata.create_all(bind=self.session_manager.engine)

    def get(
        self, projection_name: str = "entity"
    ) -> Optional[ProjectionCheckpoint]:
        with self.session_manager.session(commit=False) as session:
            return session.get(ProjectionCheckpoint, projection_name)

    def get_last_seq(self, projection_name: str = "entity") -> int:
        """Return the durable last-projected seq (0 if none yet)."""
        row = self.get(projection_name)
        return row.last_seq if row is not None else 0

    def get_last_event_id(
        self, projection_name: str = "entity"
    ) -> Optional[str]:
        row = self.get(projection_name)
        return row.last_event_id if row is not None else None

    def advance(
        self,
        last_seq: int,
        last_event_id: Optional[str],
        projection_name: str = "entity",
    ) -> None:
        """Persist the new checkpoint value (projection-first, checkpoint-second).

        Callers MUST only invoke this AFTER the corresponding entity projection
        has been successfully committed. The repository does not itself gate on
        projection success; the catch-up driver owns that ordering guarantee.
        """
        with self.session_manager.session(commit=True) as session:
            row = session.get(ProjectionCheckpoint, projection_name)
            if row is None:
                session.add(
                    ProjectionCheckpoint(
                        projection_name=projection_name,
                        last_seq=int(last_seq),
                        last_event_id=last_event_id,
                    )
                )
            else:
                row.last_seq = int(last_seq)
                row.last_event_id = last_event_id
                row.updated_at = datetime.now(timezone.utc)
