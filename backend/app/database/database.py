"""
Database Module.

This module provides the main database interface for Tactical Core.
Exports common components and provides high-level database operations.

Architecture Rule: All module communication via Event Service.
No direct module-to-module coupling.

Author: Tactical Core Engineering Team
Version: 1.0
"""

import logging
from typing import Optional, List, Type, TypeVar

from sqlalchemy import text, inspect
from sqlalchemy.engine import Engine

from app.database.base import Base, BaseModel
from app.database.session import (
    DatabaseSessionManager,
    get_session_manager,
    configure_session_manager,
    get_session_local,
)

logger = logging.getLogger(__name__)

# Generic type for ORM models
ModelType = TypeVar("ModelType", bound=BaseModel)


class DatabaseManager:
    """
    High-level database manager for Tactical Core.

    Provides utility methods for database operations including
    table creation, schema verification, and health checks.

    Usage:
        >>> db = DatabaseManager()
        >>> db.initialize()
        >>> db.health_check()
    """

    def __init__(self, session_manager: Optional[DatabaseSessionManager] = None) -> None:
        """
        Initialize the database manager.

        Args:
            session_manager: Optional session manager instance.
                Uses global session manager if not provided.
        """
        self._session_manager = session_manager
        self._initialized = False

    @property
    def session_manager(self) -> DatabaseSessionManager:
        """
        Get the session manager.

        Returns:
            The configured DatabaseSessionManager instance.
        """
        if self._session_manager is None:
            self._session_manager = get_session_manager()
        return self._session_manager

    @property
    def engine(self) -> Engine:
        """
        Get the SQLAlchemy engine.

        Returns:
            The configured engine instance.
        """
        return self.session_manager.engine

    def initialize(self, create_tables: bool = True) -> None:
        """
        Initialize the database.

        Creates all tables if they do not exist.
        Should be called once at application startup.

        Args:
            create_tables: Whether to create tables automatically.
                Set to False in production to use migrations.
        """
        if self._initialized:
            logger.warning("Database already initialized")
            return

        logger.info("Initializing database...")

        if create_tables:
            self.create_tables()

        self._initialized = True
        logger.info("Database initialized successfully")

    def create_tables(self) -> None:
        """
        Create all database tables.

        Uses SQLAlchemy metadata to create tables.
        Does not modify existing tables (use migrations for that).
        """
        logger.info("Creating database tables...")

        # Import all models to register them with Base.metadata
        self._import_models()

        # Create tables
        Base.metadata.create_all(bind=self.engine)

        # Log created tables
        inspector = inspect(self.engine)
        tables = inspector.get_table_names()
        logger.info(
            "Database tables created",
            extra={"tables": tables, "count": len(tables)}
        )

    def _import_models(self) -> None:
        """
        Import all ORM models to register them with Base.metadata.

        Models must be imported before create_all() is called.
        """
        try:
            # Import Event model (required for all operations)
            from app.models.event import Event
            logger.debug("Event model registered")
        except ImportError as e:
            logger.warning(f"Could not import models: {e}")

    def drop_tables(self, confirm: bool = True) -> None:
        """
        Drop all database tables.

        WARNING: This will delete all data.
        Should only be used in development or testing.

        Args:
            confirm: Safety flag. Must be True to proceed.
        """
        if not confirm:
            logger.warning("Drop tables cancelled: confirm=False")
            return

        logger.warning("Dropping all database tables...")
        Base.metadata.drop_all(bind=self.engine)
        logger.warning("All database tables dropped")

    def health_check(self) -> dict:
        """
        Perform database health check.

        Returns:
            Dictionary with health status and details.
        """
        try:
            # Check connection
            with self.session_manager.session(commit=False) as session:
                session.execute(text("SELECT 1"))

            # Check Event table
            inspector = inspect(self.engine)
            tables = inspector.get_table_names()

            return {
                "status": "healthy",
                "connected": True,
                "tables": tables,
                "table_count": len(tables),
                "database_url_masked": self._mask_url(
                    str(self.engine.url)
                ),
            }
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return {
                "status": "unhealthy",
                "connected": False,
                "error": str(e),
                "error_type": type(e).__name__,
            }

    def get_table_info(self, table_name: str) -> Optional[dict]:
        """
        Get information about a database table.

        Args:
            table_name: Name of the table.

        Returns:
            Dictionary with table information or None if not found.
        """
        try:
            inspector = inspect(self.engine)

            # Check if table exists
            if table_name not in inspector.get_table_names():
                return None

            # Get columns
            columns = inspector.get_columns(table_name)

            # Get primary keys
            pk = inspector.get_pk_constraint(table_name)

            # Get foreign keys
            fks = inspector.get_foreign_keys(table_name)

            # Get indexes
            indexes = inspector.get_indexes(table_name)

            return {
                "table_name": table_name,
                "columns": columns,
                "primary_key": pk,
                "foreign_keys": fks,
                "indexes": indexes,
                "column_count": len(columns),
            }
        except Exception as e:
            logger.error(f"Failed to get table info for {table_name}: {e}")
            return None

    def get_all_tables(self) -> List[str]:
        """
        Get list of all database table names.

        Returns:
            List of table name strings.
        """
        inspector = inspect(self.engine)
        return inspector.get_table_names()

    def table_exists(self, table_name: str) -> bool:
        """
        Check if a table exists in the database.

        Args:
            table_name: Name of the table to check.

        Returns:
            True if table exists, False otherwise.
        """
        inspector = inspect(self.engine)
        return table_name in inspector.get_table_names()

    def vacuum(self) -> None:
        """
        Run VACUUM on the database.

        Reclaims storage and optimizes database file.
        Only works with SQLite.
        """
        if not str(self.engine.url).startswith("sqlite"):
            logger.warning("VACUUM only supported on SQLite")
            return

        logger.info("Running database VACUUM...")
        with self.session_manager.session(commit=False) as session:
            session.execute(text("VACUUM"))
        logger.info("Database VACUUM completed")

    def get_database_size(self) -> Optional[int]:
        """
        Get the database file size in bytes.

        Only works with SQLite.

        Returns:
            Database size in bytes or None if not supported.
        """
        if not str(self.engine.url).startswith("sqlite"):
            return None

        # Get database file path
        db_path = self.engine.url.database
        if not db_path:
            return None

        import os
        try:
            return os.path.getsize(db_path)
        except OSError:
            return None

    @staticmethod
    def _mask_url(url: str) -> str:
        """
        Mask password in database URL for logging.

        Args:
            url: Database URL string.

        Returns:
            URL with password replaced.
        """
        import re
        pattern = r"(://[^:]+:)[^@]+(@)"
        return re.sub(pattern, r"\1****\2", url)


# Global database manager instance
_database_manager: Optional[DatabaseManager] = None


def get_database_manager() -> DatabaseManager:
    """
    Get the global database manager instance.

    Returns:
        The configured DatabaseManager instance.

    Raises:
        RuntimeError: If database manager not initialized.
    """
    global _database_manager
    if _database_manager is None:
        _database_manager = DatabaseManager()
    return _database_manager


def initialize_database(
    database_url: str,
    echo: bool = False,
    create_tables: bool = True,
) -> DatabaseManager:
    """
    Initialize the database with the given configuration.

    This is the main entry point for database initialization.
    Should be called once at application startup.

    Args:
        database_url: SQLAlchemy database URL.
        echo: Whether to log SQL statements.
        create_tables: Whether to create tables automatically.

    Returns:
        Configured DatabaseManager instance.
    """
    global _database_manager

    # Configure session manager
    configure_session_manager(
        database_url=database_url,
        echo=echo,
    )

    # Create database manager
    _database_manager = DatabaseManager()
    _database_manager.initialize(create_tables=create_tables)

    logger.info(
        "Database initialized",
        extra={
            "url_masked": DatabaseManager._mask_url(database_url),
            "tables_created": create_tables,
        }
    )

    return _database_manager


def shutdown_database() -> None:
    """
    Shutdown the database and release resources.

    Should be called at application shutdown.
    """
    global _database_manager, _session_manager

    if _database_manager is not None:
        logger.info("Shutting down database...")
        _database_manager = None

    from app.database.session import _session_manager
    if _session_manager is not None:
        _session_manager.close()
        _session_manager = None

    logger.info("Database shutdown complete")
