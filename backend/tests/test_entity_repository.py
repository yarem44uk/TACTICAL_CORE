from __future__ import annotations

import os
import tempfile
import threading
from uuid import uuid4

import pytest

from app.database.session import configure_session_manager
from app.entity_repository import SQLiteEntityRepository


@pytest.fixture
def repo():
    """Create a SQLite Entity repository backed by the shared session manager.

    WO-014-025 refactored ``SQLiteEntityRepository`` off its independent
    raw-sqlite3 database onto the single canonical ``DatabaseSessionManager``
    (single-owner invariant). The fixture therefore configures a file-backed
    session manager (QueuePool + ``check_same_thread=False``, matching real
    production SQLite) and initialises the durable ``entities`` table through
    the shared metadata, mirroring how the durable event repository tests
    configure the canonical DB owner. A file-backed DB (not ``:memory:``) is
    used so concurrent threads each get their own pooled connection, exactly as
    in production.
    """
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    manager = configure_session_manager(f"sqlite:///{path}")
    r = SQLiteEntityRepository(session_manager=manager)
    r.initialize()
    yield r
    r.close()
    manager.close()
    if os.path.exists(path):
        os.remove(path)


class TestSave:
    def test_save_entity(self, repo: SQLiteEntityRepository) -> None:
        repo.save({"entity_id": "e1", "entity_type": "person", "attributes": {"name": "A"}})
        result = repo.get("e1")
        assert result is not None
        assert result["id"] == "e1"
        assert result["entity_type"] == "person"

    def test_save_sets_unknown_status(self, repo: SQLiteEntityRepository) -> None:
        repo.save({"entity_id": "e1", "entity_type": "person"})
        result = repo.get("e1")
        assert result["status"] == "UNKNOWN"


class TestUpdate:
    def test_update_increments_version(self, repo: SQLiteEntityRepository) -> None:
        repo.save({"entity_id": "e1", "entity_type": "person", "attributes": {}})
        repo.update("e1", {"name": "B"})
        e = repo.get("e1")
        assert e["version"] == 2

    def test_update_returns_false_if_missing(self, repo: SQLiteEntityRepository) -> None:
        assert repo.update("missing", {"x": 1}) is False


class TestSoftDelete:
    def test_soft_delete_marks_deleted(self, repo: SQLiteEntityRepository) -> None:
        repo.save({"entity_id": "e1", "entity_type": "person"})
        assert repo.soft_delete("e1") is True
        assert repo.get("e1") is None
        assert len(repo.list_deleted()) == 1

    def test_delete_alias_soft_delete(self, repo: SQLiteEntityRepository) -> None:
        repo.save({"entity_id": "e1", "entity_type": "person"})
        assert repo.delete("e1") is True
        assert len(repo.list_deleted()) == 1


class TestHardDelete:
    def test_hard_delete_removes(self, repo: SQLiteEntityRepository) -> None:
        repo.save({"entity_id": "e1", "entity_type": "person"})
        assert repo.hard_delete("e1") is True
        assert repo.get("e1") is None
        assert len(repo.list_deleted()) == 0


class TestList:
    def test_list_by_type(self, repo: SQLiteEntityRepository) -> None:
        repo.save({"entity_id": "e1", "entity_type": "person"})
        repo.save({"entity_id": "e2", "entity_type": "device"})
        assert len(repo.list_by_type("person")) == 1
        assert len(repo.list_by_type("device")) == 1


class TestConcurrency:
    def test_concurrent_saves(self, repo: SQLiteEntityRepository) -> None:
        errors: list[Exception] = []

        def worker(i: int) -> None:
            try:
                repo.save({"entity_id": f"e-{i}", "entity_type": "t"})
            except Exception as ex:
                errors.append(ex)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(errors) == 0

    def test_concurrent_updates(self, repo: SQLiteEntityRepository) -> None:
        repo.save({"entity_id": "e1", "entity_type": "t", "attributes": {"c": 0}})
        errors: list[Exception] = []

        def worker() -> None:
            try:
                repo.update("e1", {"c": 1})
            except Exception as ex:
                errors.append(ex)

        threads = [threading.Thread(target=worker) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(errors) == 0
