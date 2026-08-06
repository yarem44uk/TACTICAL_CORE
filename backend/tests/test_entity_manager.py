from __future__ import annotations

import threading

import pytest

from app.entity_manager import EntityManager, MemoryRepository


@pytest.fixture
def repo() -> MemoryRepository:
    return MemoryRepository()


@pytest.fixture
def manager(repo: MemoryRepository) -> EntityManager:
    return EntityManager(repository=repo)


class TestCreateEntity:
    def test_apply_update_creates_new_entity(
        self, manager: EntityManager,
    ) -> None:
        res = manager.apply_update(
            entity_type="person",
            entity_id="p-1",
            payload={"name": "John"},
            metadata={"source": "test"},
        )
        assert res is True
        ent = manager.get_entity("person", "p-1")
        assert ent is not None
        assert ent["attributes"]["name"] == "John"
        assert ent["version"] == 1


class TestUpdateEntity:
    def test_apply_update_existing_increments_version(
        self, manager: EntityManager,
    ) -> None:
        manager.apply_update("person", "p-1", {"name": "John"}, {})
        manager.apply_update("person", "p-1", {"age": 30}, {})
        ent = manager.get_entity("person", "p-1")
        assert ent is not None
        assert ent["version"] == 2
        assert ent["attributes"]["age"] == 30


class TestDeleteEntity:
    def test_delete_entity_removes_it(
        self, manager: EntityManager,
    ) -> None:
        manager.apply_update("person", "p-1", {"name": "John"}, {})
        assert manager.delete_entity("person", "p-1") is True
        assert manager.get_entity("person", "p-1") is None


class TestListEntities:
    def test_list_entities_filters_by_type(
        self, manager: EntityManager,
    ) -> None:
        manager.apply_update("person", "p-1", {"name": "John"}, {})
        manager.apply_update("vehicle", "v-1", {"model": "Car"}, {})
        persons = manager.list_entities("person")
        assert len(persons) == 1


class TestConcurrentUpdates:
    def test_concurrent_updates_thread_safe(
        self, manager: EntityManager,
    ) -> None:
        def update_worker(i: int) -> None:
            manager.apply_update("counter", "c-1", {"val": i}, {})

        threads = [
            threading.Thread(target=update_worker, args=(i,))
            for i in range(10)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        ent = manager.get_entity("counter", "c-1")
        assert ent is not None
        assert ent["version"] == 10
