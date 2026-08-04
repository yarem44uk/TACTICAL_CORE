"""
Event Repository Tests.

Tests for InMemory and SQLAlchemy Event Repository implementations.
"""

import pytest
import uuid
from unittest.mock import MagicMock, patch

from app.repositories.event_repository import InMemoryEventRepository, SQLAlchemyEventRepository


class TestInMemoryEventRepository:
    """Tests for InMemory Event Repository."""

    def test_create_event(self):
        repo = InMemoryEventRepository()
        event_data = {
            "id": str(uuid.uuid4()),
            "event_type": "signal.message",
            "source": "signal_connector",
            "title": "Test Event",
            "status": "new",
            "priority": "medium",
        }
        event_id = repo.create(event_data)
        assert event_id is not None
        assert event_id == event_data["id"]

    def test_get_event(self):
        repo = InMemoryEventRepository()
        event_id = str(uuid.uuid4())
        event_data = {
            "id": event_id,
            "event_type": "signal.message",
            "source": "signal_connector",
            "status": "new",
            "priority": "medium",
        }
        repo.create(event_data)
        result = repo.get(event_id)
        assert result is not None
        assert result["id"] == event_id
        assert result["event_type"] == "signal.message"

    def test_get_nonexistent(self):
        repo = InMemoryEventRepository()
        result = repo.get("nonexistent-id")
        assert result is None

    def test_count(self):
        repo = InMemoryEventRepository()
        assert repo.count() == 0
        repo.create({"id": str(uuid.uuid4()), "event_type": "t1", "source": "s1"})
        assert repo.count() == 1
        repo.create({"id": str(uuid.uuid4()), "event_type": "t2", "source": "s2"})
        assert repo.count() == 2

    def test_soft_delete(self):
        repo = InMemoryEventRepository()
        event_id = str(uuid.uuid4())
        repo.create({"id": event_id, "event_type": "t1", "source": "s1"})
        result = repo.soft_delete(event_id)
        assert result is True
        # Count should exclude deleted
        assert repo.count() == 0
        # Event should still exist in storage
        event = repo.get(event_id)
        assert event is not None
        assert event["is_deleted"] is True

    def test_update_status(self):
        repo = InMemoryEventRepository()
        event_id = str(uuid.uuid4())
        repo.create({"id": event_id, "event_type": "t1", "source": "s1", "status": "new"})
        result = repo.update_status(event_id, "processed")
        assert result is True
        event = repo.get(event_id)
        assert event["status"] == "processed"

    def test_find_by_status(self):
        repo = InMemoryEventRepository()
        repo.create({"id": str(uuid.uuid4()), "event_type": "t1", "source": "s1", "status": "new"})
        repo.create({"id": str(uuid.uuid4()), "event_type": "t1", "source": "s1", "status": "processed"})
        results = repo.find_by_status("new")
        assert len(results) == 1
        assert results[0]["status"] == "new"

    def test_soft_delete_prevents_find(self):
        repo = InMemoryEventRepository()
        event_id = str(uuid.uuid4())
        repo.create({"id": event_id, "event_type": "t1", "source": "s1", "status": "new"})
        repo.soft_delete(event_id)
        results = repo.find_by_status("new")
        assert len(results) == 0


class TestSQLAlchemyEventRepository:
    """Tests for SQLAlchemy Event Repository (with mocked session)."""

    @pytest.fixture
    def mock_session(self):
        session = MagicMock()
        session.commit = MagicMock()
        session.refresh = MagicMock()
        session.rollback = MagicMock()
        return session

    def test_create_event(self, mock_session):
        with patch("app.repositories.event_repository.Event") as MockEvent:
            event_obj = MagicMock()
            event_obj.id = uuid.uuid4()
            MockEvent.from_dict.return_value = event_obj
            repo = SQLAlchemyEventRepository(mock_session)
            event_id = repo.create({"id": str(uuid.uuid4()), "event_type": "t1", "source": "s1"})
            assert event_id is not None
            mock_session.add.assert_called_once()
            mock_session.commit.assert_called_once()

    def test_update_status(self, mock_session):
        with patch("app.repositories.event_repository.Event") as MockEvent:
            event_obj = MagicMock()
            mock_session.query.return_value.filter.return_value.first.return_value = event_obj
            repo = SQLAlchemyEventRepository(mock_session)
            result = repo.update_status("some-id", "processed")
            assert result is True
            event_obj.increment_version.assert_called_once()
            mock_session.commit.assert_called_once()
