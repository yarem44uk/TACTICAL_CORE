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


def __getattr__(name):
    """Lazy import of optional dependencies (FastAPI, Alembic).

    Avoids importing fastapi or alembic at package initialization time.
    Dependencies are only loaded when explicitly accessed.
    """
    if name in ("get_db", "get_db_session_manager", "get_db_manager", "get_db_context"):
        from app.database.dependencies import (
            get_db,
            get_db_session_manager,
            get_db_manager,
            get_db_context,
        )
        return {"get_db": get_db, "get_db_session_manager": get_db_session_manager,
                "get_db_manager": get_db_manager, "get_db_context": get_db_context}[name]
    if name in ("MigrationManager", "init_alembic", "run_migrations", "ensure_database_schema"):
        from app.database.migration import (
            MigrationManager,
            init_alembic,
            run_migrations,
            ensure_database_schema,
        )
        return {"MigrationManager": MigrationManager, "init_alembic": init_alembic,
                "run_migrations": run_migrations, "ensure_database_schema": ensure_database_schema}[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


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
    # Dependencies (lazy loaded — requires fastapi)
    "get_db",
    "get_db_session_manager",
    "get_db_manager",
    "get_db_context",
    # Migration (lazy loaded — requires alembic)
    "MigrationManager",
    "init_alembic",
    "run_migrations",
    "ensure_database_schema",
]
