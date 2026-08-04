"""
Repository Factory.

Creates repository instances with proper session lifecycle management.
Thread-safe: each call produces an independent session.

Architecture Rule: All module communication via Event Service.
No direct module-to-module coupling.

Author: Tactical Core Engineering Team
Version: 1.0
"""

import logging
from contextlib import contextmanager
from typing import Optional

from sqlalchemy.orm import Session

from app.database.session import (
    DatabaseSessionManager,
    get_session_manager,
)
from app.database.transaction import TransactionManager

logger = logging.getLogger(__name__)


class RepositoryFactory:
    """
    Factory for creating repository instances with proper session management.

    Each repository instance gets its own independent session,
    ensuring thread safety and proper transaction isolation.

    Usage:
        >>> factory = RepositoryFactory(database_url="sqlite:///./db.sqlite")
        >>> factory.initialize()
        >>> with factory.create_event_repository() as repo:
        ...     repo.create({...})
    """

    def __init__(self, session_manager: Optional[DatabaseSessionManager] = None) -> None:
        """
        Initialize the repository factory.

        Args:
            session_manager: Optional session manager. Uses global if not provided.
        """
        self._session_manager = session_manager
        self._initialized = False

    @property
    def session_manager(self) -> DatabaseSessionManager:
        """
        Get the session manager.

        Returns:
            The configured DatabaseSessionManager instance.

        Raises:
            RuntimeError: If session manager not configured.
        """
        if self._session_manager is None:
            self._session_manager = get_session_manager()
        return self._session_manager

    def initialize(self) -> None:
        """
        Mark factory as initialized.

        The session manager must already be configured.
        """
        if not self._initialized:
            try:
                _ = self.session_manager.engine
                self._initialized = True
                logger.info("RepositoryFactory initialized")
            except Exception as e:
                logger.error(f"RepositoryFactory initialization failed: {e}")
                raise

    def create_session(self) -> Session:
        """
        Create a new independent session.

        Thread-safe: each call produces a new session.

        Returns:
            New SQLAlchemy Session instance.
        """
        if not self._initialized:
            self.initialize()
        return self.session_manager.get_session()

    def create_event_repository(self):
        """
        Create an EventRepository with a managed session.

        Returns:
            SQLAlchemyEventRepository instance bound to a new session.

        Usage:
            >>> repo = factory.create_event_repository()
            >>> repo.create({...})
            >>> # caller must commit/rollback the session
        """
        from app.repositories.event_repository import SQLAlchemyEventRepository
        session = self.create_session()
        return SQLAlchemyEventRepository(session=session)

    @contextmanager
    def managed_session(self) -> Session:
        """
        Context manager for a repository session with automatic commit/rollback.

        Yields:
            SQLAlchemy Session within transaction context.
        """
        session = self.create_session()
        with TransactionManager.commit(session):
            yield session
