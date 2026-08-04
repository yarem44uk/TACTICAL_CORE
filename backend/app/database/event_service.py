"""
Event Persistence Service.

Service layer that orchestrates event persistence operations.
Uses RepositoryFactory and TransactionManager — no direct SQLAlchemy access.

Architecture Rule: All event persistence flows through this service.
No direct repository construction outside this module.

Author: Tactical Core Engineering Team
Version: 1.0
"""

import logging
from typing import Any, Dict, List, Optional

from app.database.repository_factory import RepositoryFactory
from app.database.session import DatabaseSessionManager, get_session_manager
from app.database.transaction import TransactionManager

logger = logging.getLogger(__name__)


class EventPersistenceService:
    """
    Service layer for event persistence operations.

    Orchestrates all event CRUD through RepositoryFactory and
    TransactionManager. Provides a stable API for consumers.

    Usage:
        service = EventPersistenceService()
        event_id = service.create_event({"event_type": "signal.message", "source": "signal"})
        event = service.get_event(event_id)
        service.update_status(event_id, "processed")
        service.soft_delete(event_id)
    """

    def __init__(self, session_manager: Optional[DatabaseSessionManager] = None) -> None:
        """
        Initialize the service.

        Args:
            session_manager: Optional session manager. Uses global if None.
        """
        self._session_manager = session_manager
        self._factory = None

    @property
    def session_manager(self) -> DatabaseSessionManager:
        if self._session_manager is None:
            self._session_manager = get_session_manager()
        return self._session_manager

    @property
    def factory(self) -> RepositoryFactory:
        if self._factory is None:
            self._factory = RepositoryFactory(self.session_manager)
        return self._factory

    def create_event(self, event_data: Dict[str, Any]) -> Optional[str]:
        """
        Create and persist a new event.

        Args:
            event_data: Event data dictionary with fields:
                - event_type (str)
                - source (str)
                - title (str, optional)
                - description (str, optional)
                - payload (dict, optional)
                - status (str, default 'new')
                - priority (str, default 'medium')

        Returns:
            str: Event ID if created, None if creation failed.
        """
        with self.factory.managed_session() as session:
            from app.repositories.event_repository import SQLAlchemyEventRepository
            repo = SQLAlchemyEventRepository(session)
            event_id = repo.create(event_data)
            if event_id:
                logger.info(f"EventPersistenceService: created event {event_id}")
            return event_id

    def get_event(self, event_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve an event by ID.

        Args:
            event_id: Event identifier.

        Returns:
            Dict: Event data if found, None otherwise.
        """
        with TransactionManager.read_only(self.session_manager) as session:
            from app.repositories.event_repository import SQLAlchemyEventRepository
            repo = SQLAlchemyEventRepository(session)
            return repo.get(event_id)

    def update_status(self, event_id: str, new_status: str) -> bool:
        """
        Update the status of an event.

        Args:
            event_id: Event identifier.
            new_status: New status string.

        Returns:
            bool: True if updated, False if event not found.
        """
        with self.factory.managed_session() as session:
            from app.repositories.event_repository import SQLAlchemyEventRepository
            repo = SQLAlchemyEventRepository(session)
            result = repo.update_status(event_id, new_status)
            if result:
                logger.info(f"EventPersistenceService: updated {event_id} status={new_status}")
            return result

    def soft_delete(self, event_id: str) -> bool:
        """
        Soft delete an event.

        Args:
            event_id: Event identifier.

        Returns:
            bool: True if marked as deleted, False if not found.
        """
        with self.factory.managed_session() as session:
            from app.repositories.event_repository import SQLAlchemyEventRepository
            repo = SQLAlchemyEventRepository(session)
            result = repo.soft_delete(event_id)
            if result:
                logger.info(f"EventPersistenceService: soft_deleted {event_id}")
            return result

    def find_by_status(self, status: str) -> List[Dict[str, Any]]:
        """
        Find all events with a given status.

        Args:
            status: Status string to filter by.

        Returns:
            List of event data dictionaries.
        """
        with TransactionManager.read_only(self.session_manager) as session:
            from app.repositories.event_repository import SQLAlchemyEventRepository
            repo = SQLAlchemyEventRepository(session)
            return repo.find_by_status(status)

    def count(self) -> int:
        """
        Count total non-deleted events.

        Returns:
            int: Total number of events.
        """
        with TransactionManager.read_only(self.session_manager) as session:
            from app.repositories.event_repository import SQLAlchemyEventRepository
            repo = SQLAlchemyEventRepository(session)
            return repo.count()
