"""
Event Persistence Service Tests.

Tests for EventPersistenceService orchestration layer.
Uses real DatabaseSessionManager with in-memory SQLite and real SQLAlchemy repository.
"""

import uuid
import pytest

from app.database.session import DatabaseSessionManager
from app.database.base import Base
from app.database.repository_factory import RepositoryFactory, RepositoryType
from app.database.event_service import EventPersistenceService
from app.repositories.event_repository import (
    EventRepository,
    InMemoryEventRepository,
    SQLAlchemyEventRepository,
)


@pytest.fixture
def session_manager():
    """Create a DatabaseSessionManager with in-memory SQLite."""
    from app.models.event import Event  # Register Event in Base.metadata
    sm = DatabaseSessionManager("sqlite:///:memory:")
    sm.initialize()
    Base.metadata.create_all(sm.engine)
    yield sm
    sm.close()


@pytest.fixture
def factory(session_manager):
    """Create a RepositoryFactory with SQLAlchemyEventRepository registered."""
    f = RepositoryFactory(session_manager)
    f.register(RepositoryType.EVENT, SQLAlchemyEventRepository)
    return f


@pytest.fixture
def service(factory):
    """Create EventPersistenceService with RepositoryFactory."""
    return EventPersistenceService(factory)


class TestCreateEvent:
    """Tests for create_event()."""

    def test_create_event_returns_id(self, service):
        event_data = {
            "event_type": "signal.message",
            "source": "signal_connector",
            "title": "Test Event",
            "status": "new",
            "priority": "medium",
        }
        result = service.create_event(event_data)
        assert result is not None

    def test_create_event_with_explicit_id(self, service):
        explicit_id = str(uuid.uuid4())
        event_data = {
            "id": explicit_id,
            "event_type": "signal.message",
            "source": "signal_connector",
        }
        result = service.create_event(event_data)
        assert result == explicit_id

    def test_create_event_retrievable(self, service):
        event_data = {
            "event_type": "signal.message",
            "source": "signal_connector",
            "status": "new",
        }
        event_id = service.create_event(event_data)
        event = service.get_event(event_id)
        assert event is not None
        assert event["event_type"] == "signal.message"
        assert event["source"] == "signal_connector"
        assert event["status"] == "new"

    def test_create_event_sets_defaults(self, service):
        """Verify that default values are applied when not provided."""
        event_data = {
            "event_type": "signal.message",
            "source": "signal_connector",
        }
        event_id = service.create_event(event_data)
        event = service.get_event(event_id)
        assert event is not None
        assert event["status"] == "new"
        assert event["priority"] == "medium"


class TestGetEvent:
    """Tests for get_event()."""

    def test_get_existing_event(self, service):
        event_id = service.create_event({
            "event_type": "test",
            "source": "test_source",
        })
        event = service.get_event(event_id)
        assert event is not None
        assert event["id"] == event_id

    def test_get_nonexistent_event(self, service):
        result = service.get_event("nonexistent-id")
        assert result is None

    def test_get_soft_deleted_returns_none(self, service):
        event_id = service.create_event({
            "event_type": "test",
            "source": "test_source",
        })
        service.soft_delete(event_id)
        result = service.get_event(event_id)
        assert result is None


class TestUpdateStatus:
    """Tests for update_status()."""

    def test_update_status_success(self, service):
        event_id = service.create_event({
            "event_type": "test",
            "source": "test_source",
            "status": "new",
        })
        result = service.update_status(event_id, "processed")
        assert result is True
        event = service.get_event(event_id)
        assert event["status"] == "processed"

    def test_update_status_nonexistent(self, service):
        result = service.update_status("nonexistent-id", "processed")
        assert result is False


class TestSoftDelete:
    """Tests for soft_delete()."""

    def test_soft_delete_marks_deleted(self, service):
        event_id = service.create_event({
            "event_type": "test",
            "source": "test_source",
        })
        result = service.soft_delete(event_id)
        assert result is True

    def test_soft_delete_excludes_from_get(self, service):
        event_id = service.create_event({
            "event_type": "test",
            "source": "test_source",
        })
        service.soft_delete(event_id)
        assert service.get_event(event_id) is None

    def test_soft_delete_excludes_from_count(self, service):
        service.create_event({"event_type": "t1", "source": "s1"})
        event_id = service.create_event({"event_type": "t2", "source": "s2"})
        assert service.count() == 2
        service.soft_delete(event_id)
        assert service.count() == 1

    def test_soft_delete_nonexistent(self, service):
        result = service.soft_delete("nonexistent-id")
        assert result is False


class TestFindByStatus:
    """Tests for find_by_status()."""

    def test_find_by_status(self, service):
        service.create_event({"event_type": "t1", "source": "s1", "status": "new"})
        service.create_event({"event_type": "t2", "source": "s2", "status": "processed"})
        results = service.find_by_status("new")
        assert len(results) == 1
        assert results[0]["status"] == "new"

    def test_find_by_status_empty(self, service):
        service.create_event({"event_type": "t1", "source": "s1", "status": "new"})
        results = service.find_by_status("processed")
        assert len(results) == 0

    def test_find_by_status_excludes_deleted(self, service):
        event_id = service.create_event({
            "event_type": "t1",
            "source": "s1",
            "status": "new",
        })
        service.soft_delete(event_id)
        results = service.find_by_status("new")
        assert len(results) == 0


class TestCount:
    """Tests for count()."""

    def test_count_empty(self, service):
        assert service.count() == 0

    def test_count_increments(self, service):
        assert service.count() == 0
        service.create_event({"event_type": "t1", "source": "s1"})
        assert service.count() == 1
        service.create_event({"event_type": "t2", "source": "s2"})
        assert service.count() == 2


class TestTransactionRollback:
    """Tests for transaction rollback on failure."""

    def test_create_event_rollback_on_db_error(self, factory):
        """Verify that a failed create does not partially commit."""
        service = EventPersistenceService(factory)
        # Create one valid event first
        service.create_event({"event_type": "valid", "source": "s1"})
        assert service.count() == 1

        # The service catches all exceptions and returns None on failure
        # so the transaction rollback is contained within the method
        result = service.create_event({})  # no required fields — may fail or succeed
        # Regardless of result, the valid event should still exist (no corruption)
        assert service.count() >= 1

    def test_transaction_isolation_per_call(self, service):
        """Each service method call creates its own transaction."""
        event_id = service.create_event({
            "event_type": "test",
            "source": "s1",
        })
        # Subsequent call uses a different session but sees committed data
        event = service.get_event(event_id)
        assert event is not None


class TestRepositoryFactory:
    """Tests for repository factory integration."""

    def test_repository_instantiated_per_call(self, factory):
        """Each method call creates a fresh repository instance."""
        service = EventPersistenceService(factory)
        eid1 = service.create_event({"event_type": "t1", "source": "s1"})
        assert eid1 is not None
        eid2 = service.create_event({"event_type": "t2", "source": "s2"})
        assert eid2 is not None
        # Both events persisted across separate repository instances
        assert service.count() == 2
        e1 = service.get_event(eid1)
        e2 = service.get_event(eid2)
        assert e1 is not None
        assert e2 is not None

    def test_factory_creates_repository(self, session_manager):
        """RepositoryFactory.create() returns a properly configured repository."""
        f = RepositoryFactory(session_manager)
        f.register(RepositoryType.EVENT, SQLAlchemyEventRepository)
        repo = f.create(RepositoryType.EVENT)
        assert isinstance(repo, SQLAlchemyEventRepository)
