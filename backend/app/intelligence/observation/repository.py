"""Observation Repository.

Repository pattern implementation for observation persistence.
Thread-safe, supports concurrent access.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence
from uuid import UUID

from sqlalchemy import select, func, and_, or_
from sqlalchemy.orm import Session

from app.database.repositories.base_repository import BaseRepository
from app.database.session import DatabaseSessionManager, get_session_manager
from app.intelligence.observation.model import Observation


class ObservationRepository(BaseRepository[Observation]):
    """Repository for Observation persistence and retrieval.

    Implements the Repository Pattern for clean data access.
    All methods are thread-safe.

    Constitution Compliance:
    - Observations are immutable after creation
    - No update methods expose mutation
    - Query methods preserve immutability
    """

    def __init__(self, session: Session):
        """Initialize repository with database session.

        Args:
            session: SQLAlchemy database session.
        """
        super().__init__(Observation, session)

    def get_by_immutable_id(self, immutable_id: str) -> Optional[Observation]:
        """Get observation by immutable_id.

        Args:
            immutable_id: The original immutable ID.

        Returns:
            Observation if found, None otherwise.
        """
        stmt = select(Observation).where(
            and_(
                Observation.immutable_id == immutable_id,
                Observation.is_deleted == False  # noqa: E712
            )
        )
        result = self.session.execute(stmt)
        return result.scalar_one_or_none()

    def exists_by_immutable_id(self, immutable_id: str) -> bool:
        """Check if observation with immutable_id exists.

        Args:
            immutable_id: The immutable ID to check.

        Returns:
            True if exists, False otherwise.
        """
        stmt = select(func.count(Observation.id)).where(
            and_(
                Observation.immutable_id == immutable_id,
                Observation.is_deleted == False  # noqa: E712
            )
        )
        result = self.session.execute(stmt)
        count = result.scalar_one()
        return count > 0

    def get_by_source(
        self,
        source: str,
        limit: int = 100,
        offset: int = 0
    ) -> List[Observation]:
        """Get observations by source.

        Args:
            source: Source identifier.
            limit: Maximum number to return.
            offset: Number to skip.

        Returns:
            List of observations from source.
        """
        stmt = select(Observation).where(
            and_(
                Observation.source == source,
                Observation.is_deleted == False  # noqa: E712
            )
        ).order_by(
            Observation.timestamp.desc()
        ).limit(limit).offset(offset)

        result = self.session.execute(stmt)
        return list(result.scalars().all())

    def get_by_type(
        self,
        observation_type: str,
        limit: int = 100,
        offset: int = 0
    ) -> List[Observation]:
        """Get observations by type.

        Args:
            observation_type: Type classification.
            limit: Maximum number to return.
            offset: Number to skip.

        Returns:
            List of observations of type.
        """
        stmt = select(Observation).where(
            and_(
                Observation.observation_type == observation_type,
                Observation.is_deleted == False  # noqa: E712
            )
        ).order_by(
            Observation.timestamp.desc()
        ).limit(limit).offset(offset)

        result = self.session.execute(stmt)
        return list(result.scalars().all())

    def get_by_status(
        self,
        status: str,
        limit: int = 100,
        offset: int = 0
    ) -> List[Observation]:
        """Get observations by processing status.

        Args:
            status: Processing status.
            limit: Maximum number to return.
            offset: Number to skip.

        Returns:
            List of observations with status.
        """
        stmt = select(Observation).where(
            and_(
                Observation.processing_status == status,
                Observation.is_deleted == False  # noqa: E712
            )
        ).order_by(
            Observation.timestamp.desc()
        ).limit(limit).offset(offset)

        result = self.session.execute(stmt)
        return list(result.scalars().all())

    def get_by_time_range(
        self,
        start_time: datetime,
        end_time: datetime,
        limit: int = 1000,
        offset: int = 0
    ) -> List[Observation]:
        """Get observations within time range.

        Args:
            start_time: Start of time range (UTC).
            end_time: End of time range (UTC).
            limit: Maximum number to return.
            offset: Number to skip.

        Returns:
            List of observations in time range.
        """
        stmt = select(Observation).where(
            and_(
                Observation.timestamp >= start_time,
                Observation.timestamp <= end_time,
                Observation.is_deleted == False  # noqa: E712
            )
        ).order_by(
            Observation.timestamp.desc()
        ).limit(limit).offset(offset)

        result = self.session.execute(stmt)
        return list(result.scalars().all())

    def count_by_source(self, source: str) -> int:
        """Count observations by source.

        Args:
            source: Source identifier.

        Returns:
            Count of observations.
        """
        stmt = select(func.count(Observation.id)).where(
            and_(
                Observation.source == source,
                Observation.is_deleted == False  # noqa: E712
            )
        )
        result = self.session.execute(stmt)
        return result.scalar_one()

    def count_by_type(self, observation_type: str) -> int:
        """Count observations by type.

        Args:
            observation_type: Type classification.

        Returns:
            Count of observations.
        """
        stmt = select(func.count(Observation.id)).where(
            and_(
                Observation.observation_type == observation_type,
                Observation.is_deleted == False  # noqa: E712
            )
        )
        result = self.session.execute(stmt)
        return result.scalar_one()

    def count_total(self) -> int:
        """Count total non-deleted observations.

        Returns:
            Total observation count.
        """
        stmt = select(func.count(Observation.id)).where(
            Observation.is_deleted == False  # noqa: E712
        )
        result = self.session.execute(stmt)
        return result.scalar_one()

    def list_recent(self, limit: int = 100) -> List[Observation]:
        """List recent observations.

        Args:
            limit: Maximum number to return.

        Returns:
            List of recent observations.
        """
        stmt = select(Observation).where(
            Observation.is_deleted == False  # noqa: E712
        ).order_by(
            Observation.timestamp.desc()
        ).limit(limit)

        result = self.session.execute(stmt)
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    # WO-060 — deterministic, event-time (occurred_at) chronology read model.
    # ------------------------------------------------------------------
    # The operator read path must order observations by EVENT time
    # (``occurred_at``), not ingestion time (``timestamp``).  Ordering is fully
    # deterministic: ``occurred_at`` DESC, then ``timestamp`` DESC, then
    # ``id`` DESC (the UUID id is a unique tie-breaker, so ties on event time
    # never produce a non-deterministic order).  NULL ``occurred_at`` (rows
    # created before the WO-060 column existed) sorts last in DESC (SQLite
    # treats NULL as smallest), so pre-existing rows never mask newer events.

    def list_chronological(
        self,
        *,
        source: Optional[str] = None,
        observation_type: Optional[str] = None,
        from_time: Optional[datetime] = None,
        to_time: Optional[datetime] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Observation]:
        """Return observations ordered by event time (``occurred_at`` DESC).

        Args:
            source: optional source filter.
            observation_type: optional observation-type filter.
            from_time: optional lower bound on ``occurred_at`` (inclusive).
            to_time: optional upper bound on ``occurred_at`` (inclusive).
            limit: maximum number to return.
            offset: number to skip (offset pagination; deterministic ordering).

        Returns:
            List of observations in deterministic event-time order.
        """
        stmt = select(Observation).where(
            Observation.is_deleted == False  # noqa: E712
        )
        if source is not None:
            stmt = stmt.where(Observation.source == source)
        if observation_type is not None:
            stmt = stmt.where(Observation.observation_type == observation_type)
        if from_time is not None:
            stmt = stmt.where(Observation.occurred_at >= from_time)
        if to_time is not None:
            stmt = stmt.where(Observation.occurred_at <= to_time)
        stmt = stmt.order_by(
            Observation.occurred_at.desc(),
            Observation.timestamp.desc(),
            Observation.id.desc(),
        ).offset(offset).limit(limit)
        result = self.session.execute(stmt)
        return list(result.scalars().all())

    def count_chronological(
        self,
        *,
        source: Optional[str] = None,
        observation_type: Optional[str] = None,
        from_time: Optional[datetime] = None,
        to_time: Optional[datetime] = None,
    ) -> int:
        """Count observations matching the WO-060 chronological filters.

        Args:
            source: optional source filter.
            observation_type: optional observation-type filter.
            from_time: optional lower bound on ``occurred_at`` (inclusive).
            to_time: optional upper bound on ``occurred_at`` (inclusive).

        Returns:
            Count of matching non-deleted observations.
        """
        stmt = select(func.count(Observation.id)).where(
            Observation.is_deleted == False  # noqa: E712
        )
        if source is not None:
            stmt = stmt.where(Observation.source == source)
        if observation_type is not None:
            stmt = stmt.where(Observation.observation_type == observation_type)
        if from_time is not None:
            stmt = stmt.where(Observation.occurred_at >= from_time)
        if to_time is not None:
            stmt = stmt.where(Observation.occurred_at <= to_time)
        result = self.session.execute(stmt)
        return int(result.scalar_one())


class SessionManagerObservationRepository:
    """Thread-safe, session-manager-backed read repository for the operator
    observation feed (WO-060).

    The production ``ObservationRepository`` holds a single ``Session`` and is
    used by the single-threaded production observation pipeline.  The operator
    process (ADR-011) is a separate, multi-threaded read-only consumer and MUST
    NOT share that single session.  This repository mirrors the established
    session-manager-backed pattern (``SQLAlchemyEventRepository`` /
    ``SQLAlchemyEntityRepository``): it creates a fresh ``Session`` per read via
    ``session_manager.session(commit=False)``, so it is safe to use from any
    thread and never leaks a session.

    Read-only: no insert / update / delete / commit of application state.
    """

    def __init__(
        self,
        session_manager: Optional[DatabaseSessionManager] = None,
    ) -> None:
        self._session_manager = session_manager

    @property
    def session_manager(self) -> DatabaseSessionManager:
        if self._session_manager is None:
            return get_session_manager()
        return self._session_manager

    def list_chronological(
        self,
        *,
        source: Optional[str] = None,
        observation_type: Optional[str] = None,
        from_time: Optional[datetime] = None,
        to_time: Optional[datetime] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Observation]:
        """Return observations ordered by event time (``occurred_at`` DESC).

        Deterministic tie-breaking (``occurred_at`` DESC, ``timestamp`` DESC,
        ``id`` DESC); NULL ``occurred_at`` sorts last.  Filters by source /
        observation_type / occurred_at time range.  Each read uses a fresh
        session (thread-safe).
        """
        stmt = select(Observation).where(
            Observation.is_deleted == False  # noqa: E712
        )
        if source is not None:
            stmt = stmt.where(Observation.source == source)
        if observation_type is not None:
            stmt = stmt.where(Observation.observation_type == observation_type)
        if from_time is not None:
            stmt = stmt.where(Observation.occurred_at >= from_time)
        if to_time is not None:
            stmt = stmt.where(Observation.occurred_at <= to_time)
        stmt = stmt.order_by(
            Observation.occurred_at.desc(),
            Observation.timestamp.desc(),
            Observation.id.desc(),
        ).offset(offset).limit(limit)
        with self.session_manager.session(commit=False) as session:
            result = session.execute(stmt)
            return list(result.scalars().all())

    def count_chronological(
        self,
        *,
        source: Optional[str] = None,
        observation_type: Optional[str] = None,
        from_time: Optional[datetime] = None,
        to_time: Optional[datetime] = None,
    ) -> int:
        """Count observations matching the WO-060 chronological filters."""
        stmt = select(func.count(Observation.id)).where(
            Observation.is_deleted == False  # noqa: E712
        )
        if source is not None:
            stmt = stmt.where(Observation.source == source)
        if observation_type is not None:
            stmt = stmt.where(Observation.observation_type == observation_type)
        if from_time is not None:
            stmt = stmt.where(Observation.occurred_at >= from_time)
        if to_time is not None:
            stmt = stmt.where(Observation.occurred_at <= to_time)
        with self.session_manager.session(commit=False) as session:
            result = session.execute(stmt)
            return int(result.scalar_one())
