"""
Event Persistence Service.

Orchestration layer between Pipeline/Connectors and Repository implementations.
Manages transaction lifecycle via RepositoryFactory (which delegates to
TransactionManager). Delegates all CRUD to repository through RepositoryFactory
— contains no direct SQLAlchemy access.

Architecture Rule: All module communication via Event Service.
No direct module-to-module coupling.
No direct repository construction — all repositories via RepositoryFactory.

Author: Tactical Core Engineering Team
Version: 1.0
"""

import logging
from typing import Any, Dict, List, Optional

from app.database.repository_factory import RepositoryFactory, RepositoryType
from app.repositories.event_repository import EventRepository

logger = logging.getLogger(__name__)


class EventPersistenceService:
    """
    Event persistence service — orchestration layer.

    Responsibilities:
    - Transaction lifecycle (via RepositoryFactory managed sessions)
    - Repository access via RepositoryFactory
    - Orchestration of persistence operations

    Does NOT:
    - Contain CRUD logic (delegated to repository)
    - Access SQLAlchemy directly
    - Construct repositories directly
    - Manage sessions manually
    """

    def __init__(
        self,
        factory: RepositoryFactory,
    ) -> None:
        """
        Initialize the event persistence service.

        Args:
            factory: RepositoryFactory for creating repository instances
                with managed sessions.
        """
        self._factory = factory

    # -------------------------------------------------------------------------
    # CRUD operations
    # -------------------------------------------------------------------------

    def create_event(self, event_data: Dict[str, Any]) -> Optional[str]:
        """
        Create a new event in the database.

        Wraps repository.create() in a committed transaction.

        Args:
            event_data: Event data dictionary with event_type, source, etc.

        Returns:
            Event ID string if created, None if creation failed.
        """
        try:
            with self._factory.managed_session() as session:
                repo: EventRepository = self._factory.create(RepositoryType.EVENT, session)
                result = repo.create(event_data)
                logger.debug(f"EventPersistenceService: created event {result}")
                return result
        except Exception as e:
            logger.error(f"EventPersistenceService: create_event failed: {e}")
            return None

    def get_event(self, event_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve an event by ID.

        Uses a read-only transaction (rollback on exit).

        Args:
            event_id: Event identifier string.

        Returns:
            Event data dict if found, None otherwise.
        """
        try:
            with self._factory.managed_read_only_session() as session:
                repo: EventRepository = self._factory.create(RepositoryType.EVENT, session)
                return repo.get(event_id)
        except Exception as e:
            logger.error(f"EventPersistenceService: get_event failed: {e}")
            return None

    def update_status(self, event_id: str, new_status: str) -> bool:
        """
        Update the status of an event.

        Wraps repository.update_status() in a committed transaction.

        Args:
            event_id: Event identifier string.
            new_status: New status string.

        Returns:
            True if updated, False if event not found.
        """
        try:
            with self._factory.managed_session() as session:
                repo: EventRepository = self._factory.create(RepositoryType.EVENT, session)
                return repo.update_status(event_id, new_status)
        except Exception as e:
            logger.error(f"EventPersistenceService: update_status failed: {e}")
            return False

    def soft_delete(self, event_id: str) -> bool:
        """
        Soft delete an event (CV2 compliant).

        Wraps repository.soft_delete() in a committed transaction.

        Args:
            event_id: Event identifier string.

        Returns:
            True if marked as deleted, False if not found.
        """
        try:
            with self._factory.managed_session() as session:
                repo: EventRepository = self._factory.create(RepositoryType.EVENT, session)
                return repo.soft_delete(event_id)
        except Exception as e:
            logger.error(f"EventPersistenceService: soft_delete failed: {e}")
            return False

    def find_by_status(self, status: str) -> List[Dict[str, Any]]:
        """
        Find all events with a given status.

        Uses a read-only transaction (rollback on exit).

        Args:
            status: Status string to filter by.

        Returns:
            List of event data dicts.
        """
        try:
            with self._factory.managed_read_only_session() as session:
                repo: EventRepository = self._factory.create(RepositoryType.EVENT, session)
                return repo.find_by_status(status)
        except Exception as e:
            logger.error(f"EventPersistenceService: find_by_status failed: {e}")
            return []

    def count(self) -> int:
        """
        Count total non-deleted events.

        Uses a read-only transaction (rollback on exit).

        Returns:
            Total number of non-deleted events.
        """
        try:
            with self._factory.managed_read_only_session() as session:
                repo: EventRepository = self._factory.create(RepositoryType.EVENT, session)
                return repo.count()
        except Exception as e:
            logger.error(f"EventPersistenceService: count failed: {e}")
            return 0
