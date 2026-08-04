"""
Event Repository.

Repository implementations for Event persistence.
Supports both InMemory and SQLAlchemy backends.

Architecture Rule: All module communication via Event Service.
No direct module-to-module coupling.

Author: Tactical Core Engineering Team
Version: 1.0
"""

import uuid
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import desc
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class EventRepository(ABC):
    """
    Abstract Event Repository interface.

    Defines the contract for event persistence operations.
    All implementations must support soft delete semantics.
    """

    @abstractmethod
    def create(self, event_data: Dict[str, Any]) -> Optional[str]:
        """
        Create a new event and persist it.

        Args:
            event_data: Event data dictionary with at minimum:
                - id (str or UUID)
                - event_type (str)
                - source (str)
                - status (str, default 'new')
                - priority (str, default 'medium')

        Returns:
            str: Event ID if created, None if creation failed.
        """
        pass

    @abstractmethod
    def get(self, event_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve an event by ID.

        Args:
            event_id: Event identifier.

        Returns:
            Dict: Event data if found, None otherwise.
        """
        pass

    @abstractmethod
    def find_by_status(self, status: str) -> List[Dict[str, Any]]:
        """
        Find all events with a given status.

        Args:
            status: Status string to filter by.

        Returns:
            List of event data dictionaries.
        """
        pass

    @abstractmethod
    def count(self) -> int:
        """
        Count total events.

        Returns:
            int: Total number of non-deleted events.
        """
        pass

    @abstractmethod
    def update_status(self, event_id: str, new_status: str) -> bool:
        """
        Update the status of an event.

        Args:
            event_id: Event identifier.
            new_status: New status string.

        Returns:
            bool: True if updated, False if event not found.
        """
        pass

    @abstractmethod
    def soft_delete(self, event_id: str) -> bool:
        """
        Soft delete an event (CV2 compliant).

        Args:
            event_id: Event identifier.

        Returns:
            bool: True if marked as deleted, False if not found.
        """
        pass


class InMemoryEventRepository(EventRepository):
    """
    In-memory Event Repository implementation.

    Used for testing and non-persistent deployments.
    Supports soft delete semantics matching SQLAlchemy backend.
    """

    def __init__(self) -> None:
        self._store: Dict[str, Dict[str, Any]] = {}

    def create(self, event_data: Dict[str, Any]) -> Optional[str]:
        event_id = str(event_data.get("id", uuid.uuid4()))
        self._store[event_id] = {
            "id": event_id,
            "event_type": event_data.get("event_type", "unknown"),
            "source": event_data.get("source", "unknown"),
            "title": event_data.get("title"),
            "description": event_data.get("description"),
            "payload": event_data.get("payload"),
            "status": event_data.get("status", "new"),
            "priority": event_data.get("priority", "medium"),
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            "is_deleted": False,
        }
        logger.debug(f"InMemoryEvent: created {event_id}")
        return event_id

    def get(self, event_id: str) -> Optional[Dict[str, Any]]:
        event = self._store.get(event_id)
        if event is None or event.get("is_deleted"):
            return None
        return event

    def find_by_status(self, status: str) -> List[Dict[str, Any]]:
        return [
            e for e in self._store.values()
            if e["status"] == status and not e["is_deleted"]
        ]

    def count(self) -> int:
        return sum(1 for e in self._store.values() if not e["is_deleted"])

    def update_status(self, event_id: str, new_status: str) -> bool:
        if event_id not in self._store:
            return False
        self._store[event_id]["status"] = new_status
        self._store[event_id]["updated_at"] = datetime.now(timezone.utc)
        logger.debug(f"InMemoryEvent: updated {event_id} status={new_status}")
        return True

    def soft_delete(self, event_id: str) -> bool:
        if event_id not in self._store:
            return False
        self._store[event_id]["is_deleted"] = True
        self._store[event_id]["updated_at"] = datetime.now(timezone.utc)
        logger.debug(f"InMemoryEvent: soft_deleted {event_id}")
        return True


class SQLAlchemyEventRepository(EventRepository):
    """
    SQLAlchemy-backed Event Repository implementation.

    Persists to SQLite (or PostgreSQL) with soft delete support.
    Requires Event model to be imported from app.models.event.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, event_data: Dict[str, Any]) -> Optional[str]:
        from app.models.event import Event
        try:
            event = Event.from_dict(event_data)
            self._session.add(event)
            self._session.commit()
            self._session.refresh(event)
            logger.debug(f"SQLAlchemyEvent: created {event.id}")
            return str(event.id)
        except Exception as e:
            self._session.rollback()
            logger.error(f"SQLAlchemyEvent: create failed: {e}")
            return None

    def get(self, event_id: str) -> Optional[Dict[str, Any]]:
        from app.models.event import Event
        event = self._session.query(Event).filter(
            Event.id == uuid.UUID(event_id),
            Event.is_deleted == False
        ).first()
        return event.to_dict() if event else None

    def find_by_status(self, status: str) -> List[Dict[str, Any]]:
        from app.models.event import Event
        events = self._session.query(Event).filter(
            Event.status == status,
            Event.is_deleted == False
        ).order_by(desc(Event.created_at)).all()
        return [e.to_dict() for e in events]

    def count(self) -> int:
        from app.models.event import Event
        return self._session.query(Event).filter(
            Event.is_deleted == False
        ).count()

    def update_status(self, event_id: str, new_status: str) -> bool:
        from app.models.event import Event
        event = self._session.query(Event).filter(
            Event.id == uuid.UUID(event_id),
            Event.is_deleted == False
        ).first()
        if not event:
            return False
        event.status = new_status
        event.increment_version()
        self._session.commit()
        logger.debug(f"SQLAlchemyEvent: updated {event_id} status={new_status}")
        return True

    def soft_delete(self, event_id: str) -> bool:
        from app.models.event import Event
        event = self._session.query(Event).filter(
            Event.id == uuid.UUID(event_id),
            Event.is_deleted == False
        ).first()
        if not event:
            return False
        event.is_deleted = True
        event.increment_version()
        self._session.commit()
        logger.debug(f"SQLAlchemyEvent: soft_deleted {event_id}")
        return True
