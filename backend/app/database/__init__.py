"""
Database Module.

This package provides the database layer for Tactical Core.
Includes connection management, session handling, migrations,
and repository implementations.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from app.database.base import (
    Base,
    BaseModel,
    AuditMixin,
    SoftDeleteMixin,
    TimestampMixin,
    UUIDMixin,
    VersionMixin,
)

from app.database.session import (
    DatabaseSessionManager,
    get_session_manager,
    configure_session_manager,
    get_session_local,
)

from app.database.database import (
    DatabaseManager,
    get_database_manager,
    initialize_database,
    shutdown_database,
)

from app.database.dependencies import (
    get_db,
    get_db_session_manager,
    get_db_manager,
    get_db_context,
)

from app.database.migration import (
    MigrationManager,
    init_alembic,
    run_migrations,
    ensure_database_schema,
)

from app.database.transaction import TransactionManager
from app.database.repository_factory import RepositoryFactory

__all__ = [
    # Base
    "Base",
    "BaseModel",
    "AuditMixin",
    "SoftDeleteMixin",
    "TimestampMixin",
    "UUIDMixin",
    "VersionMixin",
    # Session
    "DatabaseSessionManager",
    "get_session_manager",
    "configure_session_manager",
    "get_session_local",
    # Database
    "DatabaseManager",
    "get_database_manager",
    "initialize_database",
    "shutdown_database",
    # Dependencies
    "get_db",
    "get_db_session_manager",
    "get_db_manager",
    "get_db_context",
    # Migration
    "MigrationManager",
    "init_alembic",
    "run_migrations",
    "ensure_database_schema",
    # Transaction
    "TransactionManager",
    # Factory
    "RepositoryFactory",
]
