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
