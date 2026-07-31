"""
Database Repositories Module.

This package contains repository implementations using the
Repository Pattern for data access abstraction.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from app.database.repositories.base_repository import (
    BaseRepository,
    DatabaseException,
    EntityNotFoundError,
    DuplicateEntityError,
    ConcurrentModificationError,
)

__all__ = [
    "BaseRepository",
    "DatabaseException",
    "EntityNotFoundError",
    "DuplicateEntityError",
    "ConcurrentModificationError",
]
