"""
Repository Factory.

Creates properly-configured repository instances with independent
database sessions. Ensures thread-safe session management across
all repository operations.

Architecture Rule: All repository instances come from RepositoryFactory.
No direct repository construction with raw sessions.

Author: Tactical Core Engineering Team
Version: 1.0
"""

import logging
from contextlib import contextmanager
from typing import Generator, Optional

from sqlalchemy.orm import Session

from app.database.session import DatabaseSessionManager, get_session_manager
from app.database.transaction import TransactionManager
from app.repositories.event_repository import (
    EventRepository,
    SQLAlchemyEventRepository,
)

logger = logging.getLogger(__name__)


class RepositoryFactory:
    """
    Factory for creating repository instances with managed sessions.

    Each call produces a new independent session. Thread-safe by design.

    Usage:
        factory = RepositoryFactory()
        repo = factory.create_event_repository()
        event_id = repo.create({"event_type": "test", "source": "test"})
    """

    def __init__(self, session_manager: Optional[DatabaseSessionManager] = None) -> None:
        """
        Initialize the factory.

        Args:
            session_manager: Optional session manager. Uses global if None.
        """
        self._session_manager = session_manager

    @property
    def session_manager(self) -> DatabaseSessionManager:
        if self._session_manager is None:
            self._session_manager = get_session_manager()
        return self._session_manager

    @contextmanager
    def managed_session(self) -> Generator[Session, None, None]:
        """
        Context manager for a committed session.

        Wraps TransactionManager.commit for convenience.

        Yields:
            SQLAlchemy Session.
        """
        with TransactionManager.commit(self.session_manager) as session:
            yield session

    def create_event_repository(self) -> EventRepository:
        """
        Create an EventRepository with a new independent session.

        Returns:
            Configured SQLAlchemyEventRepository instance.
        """
        session = self.session_manager.session_factory()
        repo = SQLAlchemyEventRepository(session)
        logger.debug("RepositoryFactory: created EventRepository")
        return repo
