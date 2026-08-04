"""
Event Persistence Service Tests.

Tests the service layer that orchestrates event persistence.
Verifies integration with RepositoryFactory and TransactionManager.

Author: Tactical Core Engineering Team
Version: 1.0
"""

import uuid
from typing import Any, Dict

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.base import Base
from app.database.session import DatabaseSessionManager
from app.database.event_service import EventPersistenceService


@pytest.fixture
def session_manager():
    """Create an in-memory SQLite session manager with StaticPool."""
    url = "sqlite:///:memory:"
    sm = DatabaseSessionManager(url, echo=False)
    sm._engine = create_engine(
        url, echo=False, poolclass=StaticPool, connect_args={"check_same_thread": False}, future=True
    )
    sm._session_factory = sessionmaker(
        bind=sm._engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )
    sm._initialized = True
    # Import Event to register it on Base.metadata before creating tables
    from app.models.event import Event  # noqa: F401
    Base.metadata.create_all(sm._engine)
    yield sm
    sm._engine.dispose()
    sm._initialized = False
    sm._engine = None
    sm._session_factory = None


@pytest.fixture
def service(session_manager: DatabaseSessionManager) -> EventPersistenceService:
    return EventPersistenceService(session_manager=session_manager)


@pytest.fixture
def sample_event_data() -> Dict[str, Any]:
    return {
        "event_type": "signal.message",
        "source": "signal_connector",
        "title": "Test Event",
        "description": "Test description",
        "status": "new",
        "priority": "medium",
    }


class TestEventPersistenceServiceCreate:
    def test_create_event_returns_id(self, service: EventPersistenceService, sample_event_data: dict):
        event_id = service.create_event(sample_event_data)
        assert event_id is not None
        assert len(event_id) > 0

    def test_create_event_stores_data(self, service: EventPersistenceService, sample_event_data: dict):
        event_id = service.create_event(sample_event_data)
        result = service.get_event(event_id)
        assert result is not None
        assert result["event_type"] == sample_event_data["event_type"]
        assert result["source"] == sample_event_data["source"]

    def test_create_event_sets_defaults(self, service: EventPersistenceService):
        minimal = {"event_type": "test", "source": "test"}
        event_id = service.create_event(minimal)
        result = service.get_event(event_id)
        assert result is not None
        assert result["status"] == "new"
        assert result["priority"] == "medium"


class TestEventPersistenceServiceGet:
    def test_get_existing_event(self, service: EventPersistenceService, sample_event_data: dict):
        event_id = service.create_event(sample_event_data)
        result = service.get_event(event_id)
        assert result is not None
        assert result["id"] == event_id

    def test_get_nonexistent_event(self, service: EventPersistenceService):
        result = service.get_event(str(uuid.uuid4()))
        assert result is None


class TestEventPersistenceServiceUpdateStatus:
    def test_update_status(self, service: EventPersistenceService, sample_event_data: dict):
        event_id = service.create_event(sample_event_data)
        result = service.update_status(event_id, "processed")
        assert result is True
        event = service.get_event(event_id)
        assert event["status"] == "processed"

    def test_update_nonexistent_event(self, service: EventPersistenceService):
        result = service.update_status(str(uuid.uuid4()), "processed")
        assert result is False


class TestEventPersistenceServiceSoftDelete:
    def test_soft_delete(self, service: EventPersistenceService, sample_event_data: dict):
        event_id = service.create_event(sample_event_data)
        result = service.soft_delete(event_id)
        assert result is True

    def test_soft_delete_nonexistent_event(self, service: EventPersistenceService):
        result = service.soft_delete(str(uuid.uuid4()))
        assert result is False

    def test_soft_delete_removes_from_count(self, service: EventPersistenceService, sample_event_data: dict):
        event_id = service.create_event(sample_event_data)
        count_before = service.count()
        service.soft_delete(event_id)
        count_after = service.count()
        assert count_after == count_before - 1


class TestEventPersistenceServiceFindByStatus:
    def test_find_by_status(self, service: EventPersistenceService, sample_event_data: dict):
        service.create_event(sample_event_data)
        service.create_event({**sample_event_data, "title": "Second Event"})
        results = service.find_by_status("new")
        assert len(results) >= 2

    def test_find_by_status_returns_empty(self, service: EventPersistenceService):
        results = service.find_by_status("nonexistent_status")
        assert results == []


class TestEventPersistenceServiceCount:
    def test_count_zero_initial(self, service: EventPersistenceService):
        count = service.count()
        assert count == 0

    def test_count_increments(self, service: EventPersistenceService, sample_event_data: dict):
        service.create_event(sample_event_data)
        count = service.count()
        assert count >= 1


class TestTransactionRollback:
    def test_failed_operation_does_not_leak(self, service: EventPersistenceService, sample_event_data: dict):
        event_id = service.create_event(sample_event_data)
        count_before = service.count()
        service.soft_delete(str(uuid.uuid4()))
        count_after = service.count()
        assert count_before == count_after


class TestRepositoryFactoryIntegration:
    def test_factory_creates_repository(self, session_manager: DatabaseSessionManager):
        from app.database.repository_factory import RepositoryFactory
        factory = RepositoryFactory(session_manager=session_manager)
        repo = factory.create_event_repository()
        assert repo is not None

    def test_service_uses_transaction_manager(self, service: EventPersistenceService, sample_event_data: dict):
        event_id = service.create_event(sample_event_data)
        assert event_id is not None
        event = service.get_event(event_id)
        assert event is not None
        assert event["id"] == event_id
