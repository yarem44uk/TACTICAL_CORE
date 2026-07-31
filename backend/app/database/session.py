"""
Database Session Management.

This module provides session factory and scoped session management.
Supports both sync and async patterns with thread safety.

Architecture Rule: All module communication via Event Service.
No direct module-to-module coupling.

Author: Tactical Core Engineering Team
Version: 1.0
"""

import logging
from contextlib import contextmanager
from typing import Generator, Optional

from sqlalchemy import create_engine, Engine
from sqlalchemy.orm import Session, sessionmaker, SessionTransaction
from sqlalchemy.pool import StaticPool, QueuePool, NullPool

from app.database.base import Base

logger = logging.getLogger(__name__)


class DatabaseSessionManager:
    """
    Database session manager with connection pooling.

    Provides thread-safe session management for FastAPI dependency injection.
    Supports SQLite and future PostgreSQL migration.

    Attributes:
        engine: SQLAlchemy engine instance.
        session_factory: Session factory for creating new sessions.

    Usage:
        >>> manager = DatabaseSessionManager(database_url="sqlite:///./db.sqlite")
        >>> manager.initialize()
        >>> 
        >>> with manager.session() as session:
        ...     session.query(Event).all()
    """

    def __init__(
        self,
        database_url: str,
        echo: bool = False,
        pool_size: int = 5,
        max_overflow: int = 10,
        pool_recycle: int = 3600,
        pool_pre_ping: bool = True,
        connect_args: Optional[dict] = None,
    ) -> None:
        """
        Initialize the database session manager.

        Args:
            database_url: SQLAlchemy database URL.
            echo: Whether to log SQL statements.
            pool_size: Number of connections in pool.
            max_overflow: Max connections beyond pool_size.
            pool_recycle: Recycle connections after N seconds.
            pool_pre_ping: Test connections before use.
            connect_args: Additional connection arguments.
        """
        self.database_url = database_url
        self.echo = echo
        self.pool_size = pool_size
        self.max_overflow = max_overflow
        self.pool_recycle = pool_recycle
        self.pool_pre_ping = pool_pre_ping
        self.connect_args = connect_args or {}

        self._engine: Optional[Engine] = None
        self._session_factory: Optional[sessionmaker] = None
        self._initialized = False

        logger.info(
            "DatabaseSessionManager initialized",
            extra={
                "database_url": self._mask_password(database_url),
                "echo": echo,
                "pool_size": pool_size,
            }
        )

    def _mask_password(self, url: str) -> str:
        """
        Mask password in database URL for logging.

        Args:
            url: Database URL string.

        Returns:
            URL with password replaced by asterisk.
        """
        import re
        pattern = r"(://[^:]+:)[^@]+(@)"
        return re.sub(pattern, r"\1****\2", url)

    @property
    def engine(self) -> Engine:
        """
        Get the SQLAlchemy engine.

        Returns:
            The configured engine instance.

        Raises:
            RuntimeError: If manager not initialized.
        """
        if self._engine is None:
            raise RuntimeError(
                "DatabaseSessionManager not initialized. "
                "Call initialize() first."
            )
        return self._engine

    @property
    def session_factory(self) -> sessionmaker:
        """
        Get the session factory.

        Returns:
            Configured sessionmaker instance.

        Raises:
            RuntimeError: If manager not initialized.
        """
        if self._session_factory is None:
            raise RuntimeError(
                "DatabaseSessionManager not initialized. "
                "Call initialize() first."
            )
        return self._session_factory

    def initialize(self) -> None:
        """
        Initialize the database engine and session factory.

        Creates connection pool and prepares session factory.
        Should be called once at application startup.

        Raises:
            Exception: If database connection fails.
        """
        if self._initialized:
            logger.warning("DatabaseSessionManager already initialized")
            return

        logger.info("Initializing database connection...")

        # Detect database type
        is_sqlite = self.database_url.startswith("sqlite")

        # Configure connection arguments
        if is_sqlite:
            self.connect_args.setdefault("check_same_thread", False)
            # Enable foreign key support for SQLite
            self.connect_args.setdefault("connect_args", {"check_same_thread": False})

        # Create engine
        if is_sqlite:
            # SQLite uses StaticPool for in-memory or NullPool for file
            if ":memory:" in self.database_url:
                self._engine = create_engine(
                    self.database_url,
                    echo=self.echo,
                    poolclass=StaticPool,
                    future=True,
                )
            else:
                self._engine = create_engine(
                    self.database_url,
                    echo=self.echo,
                    poolclass=QueuePool,
                    pool_size=self.pool_size,
                    max_overflow=self.max_overflow,
                    pool_recycle=self.pool_recycle,
                    pool_pre_ping=self.pool_pre_ping,
                    future=True,
                    connect_args={"check_same_thread": False},
                )
        else:
            # PostgreSQL and other databases
            self._engine = create_engine(
                self.database_url,
                echo=self.echo,
                pool_size=self.pool_size,
                max_overflow=self.max_overflow,
                pool_recycle=self.pool_recycle,
                pool_pre_ping=self.pool_pre_ping,
                future=True,
            )

        # Create session factory
        self._session_factory = sessionmaker(
            bind=self._engine,
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )

        self._initialized = True
        logger.info("Database connection initialized successfully")

    def close(self) -> None:
        """
        Close the database engine and release connections.

        Should be called at application shutdown.
        """
        if self._engine is not None:
            logger.info("Closing database connections...")
            self._engine.dispose()
            self._engine = None
            self._session_factory = None
            self._initialized = False
            logger.info("Database connections closed")

    @contextmanager
    def session(self, commit: bool = True) -> Generator[Session, None, None]:
        """
        Context manager for database session.

        Automatically handles commit/rollback and cleanup.
        Thread-safe session management.

        Args:
            commit: Whether to commit on success (default True).

        Yields:
            SQLAlchemy session instance.

        Raises:
            Exception: Re-raises after rollback.

        Usage:
            >>> with manager.session() as session:
            ...     event = session.query(Event).first()
            ...     event.title = "Updated"
        """
        if not self._initialized:
            raise RuntimeError(
                "DatabaseSessionManager not initialized. "
                "Call initialize() first."
            )

        session: Session = self.session_factory()
        logger.debug(
            "Session created",
            extra={"session_id": id(session)}
        )

        try:
            yield session

            if commit:
                session.commit()
                logger.debug(
                    "Session committed",
                    extra={"session_id": id(session)}
                )
        except Exception as e:
            session.rollback()
            logger.error(
                "Session rollback due to error",
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
                "Session closed",
                extra={"session_id": id(session)}
            )

    def get_session(self) -> Session:
        """
        Create a new session instance.

        Caller is responsible for closing the session.
        Prefer using session() context manager when possible.

        Returns:
            New SQLAlchemy session instance.
        """
        if not self._initialized:
            raise RuntimeError(
                "DatabaseSessionManager not initialized. "
                "Call initialize() first."
            )
        return self.session_factory()


# Global session manager instance
_session_manager: Optional[DatabaseSessionManager] = None


def get_session_manager() -> DatabaseSessionManager:
    """
    Get the global session manager instance.

    Returns:
        The configured DatabaseSessionManager instance.

    Raises:
        RuntimeError: If session manager not configured.
    """
    global _session_manager
    if _session_manager is None:
        raise RuntimeError(
            "Session manager not configured. "
            "Call configure_session_manager() first."
        )
    return _session_manager


def configure_session_manager(
    database_url: str,
    echo: bool = False,
    pool_size: int = 5,
    max_overflow: int = 10,
    pool_recycle: int = 3600,
    pool_pre_ping: bool = True,
) -> DatabaseSessionManager:
    """
    Configure and initialize the global session manager.

    Args:
        database_url: SQLAlchemy database URL.
        echo: Whether to log SQL statements.
        pool_size: Number of connections in pool.
        max_overflow: Max connections beyond pool_size.
        pool_recycle: Recycle connections after N seconds.
        pool_pre_ping: Test connections before use.

    Returns:
        Configured DatabaseSessionManager instance.
    """
    global _session_manager

    _session_manager = DatabaseSessionManager(
        database_url=database_url,
        echo=echo,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_recycle=pool_recycle,
        pool_pre_ping=pool_pre_ping,
    )
    _session_manager.initialize()

    return _session_manager


# Backwards compatibility alias
SessionLocal = None


def get_session_local() -> sessionmaker:
    """
    Get the session factory for dependency injection.

    This is a compatibility function that returns the session factory
    from the global session manager.

    Returns:
        Sessionmaker instance.
    """
    return get_session_manager().session_factory
