"""
Database Transaction Management.

Provides context-managed transaction control for all database operations.
Handles session lifecycle, commit semantics, and rollback on failure.

Architecture Rule: All database access flows through TransactionManager.
No raw session creation outside this module.

Author: Tactical Core Engineering Team
Version: 1.0
"""

import logging
from contextlib import contextmanager
from typing import Generator, Optional

from sqlalchemy.orm import Session

from app.database.session import DatabaseSessionManager, get_session_manager

logger = logging.getLogger(__name__)


class TransactionManager:
    """
    Context-managed transaction control.

    Provides three transaction modes:
      - run(): yield session, rollback on exception, no auto-commit
      - commit(): yield session, auto-commit on success, rollback on exception
      - read_only(): yield session, always rollback (isolation)

    Usage:
        with TransactionManager.commit() as session:
            session.add(event)
        # committed on exit

    Raises:
        RuntimeError: if session manager is not configured.
    """

    @staticmethod
    @contextmanager
    def run(session_manager: Optional[DatabaseSessionManager] = None) -> Generator[Session, None, None]:
        """
        Open a session for manual control.

        Yields session without auto-commit. Caller must commit or
        rollback explicitly. On exception the session is always
        rolled back before re-raising.

        Args:
            session_manager: Optional session manager. Uses global if None.

        Yields:
            SQLAlchemy Session.
        """
        sm = session_manager or get_session_manager()
        with sm.session(commit=False) as session:
            yield session

    @staticmethod
    @contextmanager
    def commit(session_manager: Optional[DatabaseSessionManager] = None) -> Generator[Session, None, None]:
        """
        Open a session with auto-commit semantics.

        Commits on successful exit. Rolls back on exception.

        Args:
            session_manager: Optional session manager. Uses global if None.

        Yields:
            SQLAlchemy Session.
        """
        with (session_manager or get_session_manager()).session(commit=True) as session:
            yield session

    @staticmethod
    @contextmanager
    def read_only(session_manager: Optional[DatabaseSessionManager] = None) -> Generator[Session, None, None]:
        """
        Open a read-only session with transactional isolation.

        Always rolls back on exit to discard any accidental writes.

        Args:
            session_manager: Optional session manager. Uses global if None.

        Yields:
            SQLAlchemy Session.
        """
        with (session_manager or get_session_manager()).session(commit=False) as session:
            yield session
