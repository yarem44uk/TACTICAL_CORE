"""
Repository Factory.

Universal factory for creating repository instances with managed
database sessions. Serves as the Dependency Composition layer between
TransactionManager and Repository implementations.

Architecture Rule: All repository instances come from RepositoryFactory.
No direct repository construction with raw sessions.

Author: Tactical Core Engineering Team
Version: 1.0
"""

import logging
from contextlib import contextmanager
from enum import Enum
from typing import Any, Dict, Generator, Optional, Type

from sqlalchemy.orm import Session

from app.database.session import DatabaseSessionManager, get_session_manager
from app.database.transaction import TransactionManager

logger = logging.getLogger(__name__)


class RepositoryType(Enum):
    """Supported repository types."""

    EVENT = "event"


class RepositoryFactory:
    """
    Universal factory for creating repository instances with managed sessions.

    Sits between TransactionManager (session lifecycle) and Service layer
    (business orchestration). Maintains a registry of repository
    implementations keyed by RepositoryType.

    Usage:
        factory = RepositoryFactory()
        factory.register(RepositoryType.EVENT, SQLAlchemyEventRepository)
        event_repo = factory.create(RepositoryType.EVENT)
        event_id = event_repo.create({"event_type": "signal", ...})

    Raises:
        RuntimeError: if session manager is not configured.
        ValueError: if repository type is not registered.
    """

    # Default registry of repository implementations.
    # Extended by callers via register().
    _DEFAULT_REGISTRY: Dict[RepositoryType, Type] = {}

    def __init__(self, session_manager: Optional[DatabaseSessionManager] = None) -> None:
        """
        Initialize the factory.

        Args:
            session_manager: Optional session manager. Uses global if None.
        """
        self._session_manager = session_manager
        self._registry: Dict[RepositoryType, Type] = dict(self._DEFAULT_REGISTRY)

    @property
    def session_manager(self) -> DatabaseSessionManager:
        """Resolve the session manager, lazily loading the global one."""
        if self._session_manager is None:
            self._session_manager = get_session_manager()
        return self._session_manager

    def register(self, repo_type: RepositoryType, repo_cls: Type) -> None:
        """
        Register a repository implementation for a type.

        Args:
            repo_type: Repository type enum value.
            repo_cls: Repository class (must accept session as first arg).
        """
        self._registry[repo_type] = repo_cls
        logger.debug(f"RepositoryFactory: registered {repo_type.value} -> {repo_cls.__name__}")

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

    @contextmanager
    def managed_read_only_session(self) -> Generator[Session, None, None]:
        """
        Context manager for a read-only session.

        Wraps TransactionManager.read_only for convenience.

        Yields:
            SQLAlchemy Session.
        """
        with TransactionManager.read_only(self.session_manager) as session:
            yield session

    def create(self, repo_type: RepositoryType, session: Optional[Session] = None) -> Any:
        """
        Create a repository instance of the given type.

        If a session is provided, the repository uses it. Otherwise,
        the factory creates an independent session.

        Args:
            repo_type: Repository type enum value.
            session: Optional existing session. If None, a new one is created.

        Returns:
            Configured repository instance.

        Raises:
            ValueError: if repository type is not registered.
        """
        if repo_type not in self._registry:
            raise ValueError(
                f"RepositoryFactory: no implementation registered for "
                f"'{repo_type.value}'. Call register() first."
            )

        repo_cls = self._registry[repo_type]
        if session is None:
            session = self.session_manager.session_factory()
        repo = repo_cls(session)
        logger.debug(f"RepositoryFactory: created {repo_cls.__name__} for {repo_type.value}")
        return repo
