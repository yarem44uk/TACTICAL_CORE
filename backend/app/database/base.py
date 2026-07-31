"""
Database Base Module.

This module defines the SQLAlchemy Declarative Base and reusable mixins
for all ORM models in Tactical Core.

Architecture Rule: All module communication via Event Service.
No direct module-to-module coupling.

Author: Tactical Core Engineering Team
Version: 1.0
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Integer,
    String,
    Index,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    declared_attr,
)


class Base(DeclarativeBase):
    """
    SQLAlchemy Declarative Base for all ORM models.

    All models must inherit from this base class.
    Provides common functionality through mixins.

    Usage:
        >>> class User(Base):
        ...     __tablename__ = "users"
        ...     id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
        ...     name: Mapped[str] = mapped_column(String(255))
    """

    pass


class TimestampMixin:
    """
    Mixin providing created_at and updated_at timestamp fields.

    Automatically manages timestamps for record lifecycle.
    All timezone-aware timestamps stored in UTC.

    Attributes:
        created_at: When the record was first created.
        updated_at: When the record was last modified.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    """Timestamp when the record was created."""

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    """Timestamp when the record was last modified."""


class UUIDMixin:
    """
    Mixin providing UUID primary key field.

    Uses UUID4 for unique identification.
    Store as String(36) for cross-database compatibility.

    Attributes:
        id: Unique identifier (UUID4).
    """

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )
    """Unique identifier using UUID4."""


class VersionMixin:
    """
    Mixin providing optimistic locking version field.

    Version increments on each update.
    Used to detect concurrent modification conflicts.

    Attributes:
        version: Incremental version number.
    """

    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
    )
    """Optimistic locking version number."""

    def increment_version(self) -> None:
        """
        Increment the version number.

        Called automatically before persisting updates.
        """
        self.version += 1


class SoftDeleteMixin:
    """
    Mixin providing soft delete functionality.

    Records are not physically deleted.
    is_deleted flag hides records from normal queries.

    Attributes:
        is_deleted: Soft delete flag.
    """

    is_deleted: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        index=True,
    )
    """Soft delete flag. Deleted records are hidden but not removed."""


class AuditMixin(TimestampMixin, UUIDMixin, VersionMixin):
    """
    Combined mixin for complete audit trail.

    Provides:
    - UUID primary key
    - Created/updated timestamps
    - Version for optimistic locking

    Usage:
        >>> class Event(Base, AuditMixin):
        ...     __tablename__ = "events"
    """

    pass


class BaseModel(Base, AuditMixin, SoftDeleteMixin):
    """
    Complete base model with all common mixins.

    Provides:
    - UUID primary key
    - Created/updated timestamps
    - Version for optimistic locking
    - Soft delete functionality

    This is the recommended base class for all Tactical Core models.

    Usage:
        >>> class Event(BaseModel):
        ...     __tablename__ = "events"
        ...     title: Mapped[str] = mapped_column(String(500))
    """

    __abstract__ = True
    """This class is abstract and cannot be instantiated directly."""
