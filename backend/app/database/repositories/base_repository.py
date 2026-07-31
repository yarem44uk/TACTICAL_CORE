"""
Base Repository Module.

This module provides a generic repository implementation using the
Repository Pattern for data access abstraction.

Architecture Rule: All module communication via Event Service.
No direct module-to-module coupling.

Author: Tactical Core Engineering Team
Version: 1.0
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import (
    Any,
    Callable,
    Generic,
    Iterator,
    List,
    Optional,
    Sequence,
    Type,
    TypeVar,
    Union,
)

from sqlalchemy import (
    Column,
    and_,
    func,
    or_,
    select,
    update,
    delete,
)
from sqlalchemy.exc import (
    IntegrityError,
    OperationalError,
    ProgrammingError,
)
from sqlalchemy.orm import Session, Query

from app.database.base import BaseModel

logger = logging.getLogger(__name__)

# Generic type for ORM models
ModelType = TypeVar("ModelType", bound=BaseModel)


class DatabaseException(Exception):
    """
    Base exception for database operations.

    All database errors should be wrapped with this exception
    to avoid exposing raw SQLAlchemy errors.
    """

    def __init__(
        self,
        message: str,
        original_error: Optional[Exception] = None,
    ) -> None:
        """
        Initialize the database exception.

        Args:
            message: Human-readable error message.
            original_error: The original exception that caused this error.
        """
        super().__init__(message)
        self.original_error = original_error
        self.message = message


class EntityNotFoundError(DatabaseException):
    """
    Exception raised when an entity is not found.
    """

    def __init__(
        self,
        entity_type: str,
        entity_id: Any,
    ) -> None:
        """
        Initialize the not found error.

        Args:
            entity_type: Name of the entity type.
            entity_id: ID of the entity that was not found.
        """
        message = f"{entity_type} with id {entity_id} not found"
        super().__init__(message)
        self.entity_type = entity_type
        self.entity_id = entity_id


class DuplicateEntityError(DatabaseException):
    """
    Exception raised when attempting to create a duplicate entity.
    """

    def __init__(
        self,
        entity_type: str,
        field: str,
        value: Any,
    ) -> None:
        """
        Initialize the duplicate entity error.

        Args:
            entity_type: Name of the entity type.
            field: Field that caused the duplicate.
            value: Value that was duplicated.
        """
        message = f"{entity_type} with {field}={value} already exists"
        super().__init__(message)
        self.entity_type = entity_type
        self.field = field
        self.value = value


class ConcurrentModificationError(DatabaseException):
    """
    Exception raised when concurrent modification is detected.
    """

    def __init__(
        self,
        entity_type: str,
        entity_id: Any,
    ) -> None:
        """
        Initialize the concurrent modification error.

        Args:
            entity_type: Name of the entity type.
            entity_id: ID of the entity.
        """
        message = f"{entity_type} with id {entity_id} was modified by another process"
        super().__init__(message)
        self.entity_type = entity_type
        self.entity_id = entity_id


class BaseRepository(Generic[ModelType]):
    """
    Generic repository implementation for CRUD operations.

    Provides a reusable CRUD interface for any SQLAlchemy ORM model.
    Uses the Repository Pattern to abstract data access.

    Type Parameters:
        ModelType: The ORM model type this repository handles.

    Attributes:
        model_class: The SQLAlchemy model class.
        session: The database session.

    Usage:
        >>> class EventRepository(BaseRepository[Event]):
        ...     def __init__(self, session: Session):
        ...         super().__init__(Event, session)
        >>> 
        >>> repo = EventRepository(session)
        >>> events = repo.list(limit=10)
    """

    def __init__(
        self,
        model_class: Type[ModelType],
        session: Session,
    ) -> None:
        """
        Initialize the repository.

        Args:
            model_class: The SQLAlchemy model class.
            session: The database session.
        """
        self.model_class = model_class
        self.session = session
        self._query: Optional[Query] = None

        logger.debug(
            f"Repository initialized for {model_class.__name__}",
            extra={"session_id": id(session)}
        )

    @property
    def query(self) -> Query:
        """
        Get a base query for the model.

        Returns:
            SQLAlchemy Query object.
        """
        return self.session.query(self.model_class)

    def _apply_soft_delete_filter(self, query: Query) -> Query:
        """
        Apply soft delete filter to query.

        Args:
            query: The query to filter.

        Returns:
            Query with soft delete filter applied.
        """
        if hasattr(self.model_class, "is_deleted"):
            return query.filter(self.model_class.is_deleted == False)
        return query

    def create(self, **kwargs) -> ModelType:
        """
        Create a new entity.

        Args:
            **kwargs: Entity attributes.

        Returns:
            The created entity.

        Raises:
            DuplicateEntityError: If entity already exists.
            DatabaseException: For other database errors.
        """
        try:
            entity = self.model_class(**kwargs)
            self.session.add(entity)
            self.session.flush()

            logger.info(
                f"Created {self.model_class.__name__}",
                extra={"id": str(entity.id)}
            )

            return entity
        except IntegrityError as e:
            logger.error(f"Integrity error creating {self.model_class.__name__}: {e}")
            raise DuplicateEntityError(
                entity_type=self.model_class.__name__,
                field="unique_constraint",
                value="values",
            )
        except Exception as e:
            logger.error(f"Error creating {self.model_class.__name__}: {e}")
            raise DatabaseException(
                message=f"Failed to create {self.model_class.__name__}",
                original_error=e,
            )

    def get(
        self,
        id: Union[uuid.UUID, str],
        raise_not_found: bool = False,
    ) -> Optional[ModelType]:
        """
        Get an entity by ID.

        Args:
            id: Entity UUID or string ID.
            raise_not_found: Whether to raise exception if not found.

        Returns:
            The entity, or None if not found and raise_not_found is False.

        Raises:
            EntityNotFoundError: If raise_not_found is True and entity not found.
        """
        query = self._apply_soft_delete_filter(self.query)
        entity = query.filter(self.model_class.id == id).first()

        if entity is None and raise_not_found:
            raise EntityNotFoundError(
                entity_type=self.model_class.__name__,
                entity_id=id,
            )

        return entity

    def get_by(
        self,
        field: str,
        value: Any,
        raise_not_found: bool = False,
    ) -> Optional[ModelType]:
        """
        Get an entity by a specific field.

        Args:
            field: Name of the field to filter by.
            value: Value to match.
            raise_not_found: Whether to raise exception if not found.

        Returns:
            The entity, or None if not found.

        Raises:
            EntityNotFoundError: If raise_not_found is True and entity not found.
        """
        query = self._apply_soft_delete_filter(self.query)

        column = getattr(self.model_class, field)
        entity = query.filter(column == value).first()

        if entity is None and raise_not_found:
            raise EntityNotFoundError(
                entity_type=self.model_class.__name__,
                entity_id=value,
            )

        return entity

    def list(
        self,
        limit: int = 100,
        offset: int = 0,
        order_by: Optional[str] = None,
        order_desc: bool = True,
        filters: Optional[dict] = None,
    ) -> List[ModelType]:
        """
        List entities with pagination and filtering.

        Args:
            limit: Maximum number of entities to return.
            offset: Number of entities to skip.
            order_by: Field to order by.
            order_desc: Sort in descending order if True.
            filters: Dictionary of field:value filters (AND logic).

        Returns:
            List of entities.
        """
        query = self._apply_soft_delete_filter(self.query)

        if filters:
            filter_conditions = []
            for field, value in filters.items():
                if hasattr(self.model_class, field):
                    column = getattr(self.model_class, field)
                    if isinstance(value, (list, tuple)):
                        filter_conditions.append(column.in_(value))
                    else:
                        filter_conditions.append(column == value)

            if filter_conditions:
                query = query.filter(and_(*filter_conditions))

        if order_by and hasattr(self.model_class, order_by):
            column = getattr(self.model_class, order_by)
            if order_desc:
                query = query.order_by(column.desc())
            else:
                query = query.order_by(column.asc())

        query = query.offset(offset).limit(limit)

        return query.all()

    def update(
        self,
        id: Union[uuid.UUID, str],
        **kwargs,
    ) -> Optional[ModelType]:
        """
        Update an entity.

        Args:
            id: Entity ID.
            **kwargs: Fields to update.

        Returns:
            The updated entity, or None if not found.

        Raises:
            ConcurrentModificationError: If version conflict detected.
        """
        entity = self.get(id, raise_not_found=True)

        if entity is None:
            return None

        try:
            for key, value in kwargs.items():
                if hasattr(entity, key) and key not in ("id", "created_at"):
                    setattr(entity, key, value)

            if hasattr(entity, "updated_at"):
                entity.updated_at = datetime.now(timezone.utc)

            if hasattr(entity, "increment_version"):
                entity.increment_version()

            self.session.flush()

            logger.info(
                f"Updated {self.model_class.__name__}",
                extra={"id": str(id)}
            )

            return entity
        except Exception as e:
            logger.error(f"Error updating {self.model_class.__name__}: {e}")
            raise DatabaseException(
                message=f"Failed to update {self.model_class.__name__}",
                original_error=e,
            )

    def delete(
        self,
        id: Union[uuid.UUID, str],
        hard: bool = False,
    ) -> bool:
        """
        Delete an entity.

        Args:
            id: Entity ID.
            hard: If True, permanently delete. If False, soft delete.

        Returns:
            True if deleted, False if not found.
        """
        entity = self.get(id)

        if entity is None:
            return False

        if hard:
            self.session.delete(entity)
            logger.info(
                f"Hard deleted {self.model_class.__name__}",
                extra={"id": str(id)}
            )
        else:
            if hasattr(entity, "is_deleted"):
                entity.is_deleted = True
                self.session.flush()
                logger.info(
                    f"Soft deleted {self.model_class.__name__}",
                    extra={"id": str(id)}
                )

        return True

    def soft_delete(self, id: Union[uuid.UUID, str]) -> bool:
        """
        Soft delete an entity.

        Args:
            id: Entity ID.

        Returns:
            True if deleted, False if not found.
        """
        return self.delete(id, hard=False)

    def exists(self, id: Union[uuid.UUID, str]) -> bool:
        """
        Check if an entity exists.

        Args:
            id: Entity ID.

        Returns:
            True if entity exists, False otherwise.
        """
        query = self._apply_soft_delete_filter(self.query)
        return query.filter(self.model_class.id == id).count() > 0

    def count(self, filters: Optional[dict] = None) -> int:
        """
        Count entities matching filters.

        Args:
            filters: Optional filter conditions.

        Returns:
            Number of matching entities.
        """
        query = self._apply_soft_delete_filter(self.session.query(func.count(self.model_class.id)))

        if filters:
            filter_conditions = []
            for field, value in filters.items():
                if hasattr(self.model_class, field):
                    column = getattr(self.model_class, field)
                    if isinstance(value, (list, tuple)):
                        filter_conditions.append(column.in_(value))
                    else:
                        filter_conditions.append(column == value)

            if filter_conditions:
                query = query.filter(and_(*filter_conditions))

        return query.scalar() or 0

    def find_one(
        self,
        filters: dict,
        order_by: Optional[str] = None,
        order_desc: bool = True,
    ) -> Optional[ModelType]:
        """
        Find a single entity matching filters.

        Args:
            filters: Filter conditions.
            order_by: Field to order by.
            order_desc: Sort in descending order if True.

        Returns:
            The first matching entity, or None.
        """
        query = self._apply_soft_delete_filter(self.query)

        filter_conditions = []
        for field, value in filters.items():
            if hasattr(self.model_class, field):
                column = getattr(self.model_class, field)
                if isinstance(value, (list, tuple)):
                    filter_conditions.append(column.in_(value))
                else:
                    filter_conditions.append(column == value)

        if filter_conditions:
            query = query.filter(and_(*filter_conditions))

        if order_by and hasattr(self.model_class, order_by):
            column = getattr(self.model_class, order_by)
            if order_desc:
                query = query.order_by(column.desc())
            else:
                query = query.order_by(column.asc())

        return query.first()

    def find_many(
        self,
        filters: Optional[dict] = None,
        order_by: Optional[str] = None,
        order_desc: bool = True,
        limit: Optional[int] = None,
    ) -> List[ModelType]:
        """
        Find multiple entities matching filters.

        Args:
            filters: Filter conditions.
            order_by: Field to order by.
            order_desc: Sort in descending order if True.
            limit: Maximum number of results.

        Returns:
            List of matching entities.
        """
        query = self._apply_soft_delete_filter(self.query)

        if filters:
            filter_conditions = []
            for field, value in filters.items():
                if hasattr(self.model_class, field):
                    column = getattr(self.model_class, field)
                    if isinstance(value, (list, tuple)):
                        filter_conditions.append(column.in_(value))
                    else:
                        filter_conditions.append(column == value)

            if filter_conditions:
                query = query.filter(and_(*filter_conditions))

        if order_by and hasattr(self.model_class, order_by):
            column = getattr(self.model_class, order_by)
            if order_desc:
                query = query.order_by(column.desc())
            else:
                query = query.order_by(column.asc())

        if limit:
            query = query.limit(limit)

        return query.all()

    def search(
        self,
        query_text: str,
        search_fields: Optional[List[str]] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[ModelType]:
        """
        Search entities by text in specified fields.

        Args:
            query_text: Text to search for.
            search_fields: Fields to search in. Defaults to all string fields.
            limit: Maximum results.
            offset: Results to skip.

        Returns:
            List of matching entities.
        """
        query = self._apply_soft_delete_filter(self.query)

        if search_fields is None:
            search_fields = self._get_searchable_fields()

        if not search_fields:
            return []

        search_conditions = []
        for field in search_fields:
            if hasattr(self.model_class, field):
                column = getattr(self.model_class, field)
                search_conditions.append(
                    column.ilike(f"%{query_text}%")
                )

        if search_conditions:
            query = query.filter(or_(*search_conditions))

        return query.offset(offset).limit(limit).all()

    def _get_searchable_fields(self) -> List[str]:
        """
        Get list of string fields that can be searched.

        Returns:
            List of field names.
        """
        searchable = []
        for column in self.model_class.__table__.columns:
            if str(column.type) in ("VARCHAR", "TEXT", "STRING"):
                searchable.append(column.name)
        return searchable

    def paginate(
        self,
        page: int = 1,
        per_page: int = 20,
        order_by: Optional[str] = None,
        order_desc: bool = True,
        filters: Optional[dict] = None,
    ) -> dict:
        """
        Get paginated results with metadata.

        Args:
            page: Page number (1-indexed).
            per_page: Items per page.
            order_by: Field to order by.
            order_desc: Sort in descending order if True.
            filters: Filter conditions.

        Returns:
            Dictionary with items, total, page, per_page, pages.
        """
        total = self.count(filters)
        offset = (page - 1) * per_page

        items = self.list(
            limit=per_page,
            offset=offset,
            order_by=order_by,
            order_desc=order_desc,
            filters=filters,
        )

        pages = (total + per_page - 1) // per_page if per_page > 0 else 0

        return {
            "items": items,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": pages,
            "has_next": page < pages,
            "has_prev": page > 1,
        }

    def bulk_create(self, entities: List[dict]) -> List[ModelType]:
        """
        Create multiple entities in bulk.

        Args:
            entities: List of entity dictionaries.

        Returns:
            List of created entities.
        """
        created = []

        for entity_data in entities:
            entity = self.create(**entity_data)
            created.append(entity)

        logger.info(
            f"Bulk created {len(created)} {self.model_class.__name__} entities"
        )

        return created

    def bulk_update(
        self,
        ids: List[Union[uuid.UUID, str]],
        updates: dict,
    ) -> int:
        """
        Update multiple entities at once.

        Args:
            ids: List of entity IDs.
            updates: Fields to update.

        Returns:
            Number of updated entities.
        """
        filter_conditions = [self.model_class.id.in_(ids)]

        if hasattr(self.model_class, "is_deleted"):
            filter_conditions.append(self.model_class.is_deleted == False)

        update_values = {k: v for k, v in updates.items() if k not in ("id", "created_at")}

        if hasattr(self.model_class, "updated_at"):
            update_values["updated_at"] = datetime.now(timezone.utc)

        if hasattr(self.model_class, "version") and "version" not in update_values:
            update_values["version"] = self.model_class.version + 1

        result = self.session.execute(
            update(self.model_class)
            .where(and_(*filter_conditions))
            .values(**update_values)
        )

        logger.info(
            f"Bulk updated {result.rowcount} {self.model_class.__name__} entities"
        )

        return result.rowcount

    def refresh(self, entity: ModelType) -> ModelType:
        """
        Refresh an entity from the database.

        Args:
            entity: Entity to refresh.

        Returns:
            The refreshed entity.
        """
        self.session.refresh(entity)
        return entity

    def expire(self, entity: ModelType) -> None:
        """
        Expire an entity, forcing reload on next access.

        Args:
            entity: Entity to expire.
        """
        self.session.expire(entity)
