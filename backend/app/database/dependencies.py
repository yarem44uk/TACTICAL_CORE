"""
Database Dependencies for FastAPI.

This module provides dependency injection functions for FastAPI.
Enables clean dependency injection pattern for database access.

Architecture Rule: All module communication via Event Service.
No direct module-to-module coupling.

Author: Tactical Core Engineering Team
Version: 1.0
"""

import logging
from typing import Generator, Optional

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database.session import (
    get_session_manager,
    get_session_local,
    DatabaseSessionManager,
)
from app.database.database import get_database_manager, DatabaseManager

logger = logging.getLogger(__name__)


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency for database session.

    Provides a database session for each request.
    Automatically handles commit/rollback and cleanup.

    Usage in FastAPI routes:
        >>> @app.get("/events")
        ... def get_events(db: Session = Depends(get_db)):
        ...     return db.query(Event).all()

    Yields:
        SQLAlchemy session instance.

    Raises:
        HTTPException: 500 if database not configured.
    """
    session_manager = get_session_local()

    if session_manager is None:
        logger.error("Database session manager not configured")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database not configured",
        )

    session = session_manager()
    logger.debug(
        "Database session created for request",
        extra={"session_id": id(session)}
    )

    try:
        yield session
        session.commit()
        logger.debug("Request completed, session committed")
    except Exception as e:
        session.rollback()
        logger.error(
            "Request failed, session rolled back",
            extra={
                "session_id": id(session),
                "error": str(e),
                "error_type": type(e).__name__,
            }
        )
        raise
    finally:
        session.close()
        logger.debug(
            "Database session closed",
            extra={"session_id": id(session)}
        )


def get_db_session_manager() -> DatabaseSessionManager:
    """
    FastAPI dependency for database session manager.

    Use when you need direct access to the session manager.

    Returns:
        DatabaseSessionManager instance.

    Raises:
        HTTPException: 500 if session manager not configured.
    """
    try:
        return get_session_manager()
    except RuntimeError as e:
        logger.error(f"Session manager not available: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database not configured",
        )


def get_db_manager() -> DatabaseManager:
    """
    FastAPI dependency for database manager.

    Use for database utility operations like health checks.

    Returns:
        DatabaseManager instance.

    Raises:
        HTTPException: 500 if database manager not configured.
    """
    try:
        return get_database_manager()
    except RuntimeError as e:
        logger.error(f"Database manager not available: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database not configured",
        )


def get_db_context() -> Generator:
    """
    Context manager for database operations outside FastAPI.

    Use for background tasks, scripts, and CLI commands.

    Usage:
        >>> with get_db_context() as db:
        ...     db.query(Event).all()

    Yields:
        SQLAlchemy session instance.
    """
    session_manager = get_session_local()

    if session_manager is None:
        raise RuntimeError("Database session manager not configured")

    with session_manager() as session:
        try:
            yield session
        except Exception as e:
            session.rollback()
            logger.error(f"Database context error: {e}")
            raise


class DatabaseDependency:
    """
    Database dependency class for advanced use cases.

    Provides a reusable database session for complex dependencies.

    Usage:
        >>> class EventService:
        ...     def __init__(self, db: Session = Depends()):
        ...         self.db = db
    """

    def __init__(self) -> None:
        """Initialize the database dependency."""
        self._session: Optional[Session] = None

    def __call__(self, db: Session = Depends(get_db)) -> Session:
        """
        Return the database session.

        Args:
            db: Injected database session.

        Returns:
            The database session.
        """
        return db

    @property
    def session(self) -> Session:
        """
        Get the current session.

        Returns:
            The current SQLAlchemy session.

        Raises:
            RuntimeError: If session not available.
        """
        if self._session is None:
            raise RuntimeError("Session not available outside request context")
        return self._session


# Convenience function for type hints
DBSession = Session
"""Type alias for database session dependency."""
