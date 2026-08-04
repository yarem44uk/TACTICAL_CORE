"""
Database Transaction Manager.

Provides transaction management for SQLAlchemy sessions.
Handles commit/rollback patterns with automatic error recovery.

Architecture Rule: All module communication via Event Service.
No direct module-to-module coupling.

Author: Tactical Core Engineering Team
Version: 1.0
"""

import logging
from contextlib import contextmanager
from typing import Generator, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class TransactionManager:
    """
    Transaction manager for SQLAlchemy sessions.

    Provides structured transaction handling with automatic
    rollback on failure and explicit commit control.

    Usage:
        >>> with transaction.commit(session) as txn:
        ...     session.add(event)
        ...     txn.commit()  # or let context auto-commit
    """

    @staticmethod
    @contextmanager
    def run(session: Session) -> Generator[Session, None, None]:
        """
        Execute a transaction with automatic rollback on exception.

        Args:
            session: Active SQLAlchemy session.

        Yields:
            The session within the transaction context.

        Raises:
            Exception: Re-raises after rollback.
        """
        try:
            yield session
        except Exception as e:
            session.rollback()
            logger.error(
                "Transaction rolled back due to error",
                extra={
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "session_id": id(session),
                },
            )
            raise

    @staticmethod
    @contextmanager
    def commit(session: Session) -> Generator[Session, None, None]:
        """
        Execute a transaction with automatic commit on success.

        On exception, performs rollback and re-raises.
        On success, commits and logs.

        Args:
            session: Active SQLAlchemy session.

        Yields:
            The session within the transaction context.

        Raises:
            Exception: Re-raises after rollback.
        """
        try:
            yield session
            session.commit()
            logger.debug(
                "Transaction committed",
                extra={"session_id": id(session)},
            )
        except Exception as e:
            session.rollback()
            logger.error(
                "Transaction rolled back due to error",
                extra={
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "session_id": id(session),
                },
            )
            raise

    @staticmethod
    @contextmanager
    def read_only(session: Session) -> Generator[Session, None, None]:
        """
        Execute a read-only transaction.

        Never commits. Always rolls back on exit.
        Use for queries that should not modify state.

        Args:
            session: Active SQLAlchemy session.

        Yields:
            The session within the read-only context.
        """
        try:
            yield session
        finally:
            session.rollback()
            logger.debug(
                "Read-only transaction rolled back",
                extra={"session_id": id(session)},
            )
