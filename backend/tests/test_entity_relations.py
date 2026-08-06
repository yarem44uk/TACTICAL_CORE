from __future__ import annotations

import threading
from uuid import uuid4

import pytest

from app.entity_relations import RelationManager, MemoryRelationRepository


@pytest.fixture
def manager() -> RelationManager:
    return RelationManager(repository=MemoryRelationRepository())


class TestCreateRelation:
    def test_create_relation(self, manager: RelationManager) -> None:
        rid = manager.create_relation(uuid4(), uuid4(), "owns")
        assert manager.get_relations(rid) is not None

    def test_unsupported_type_raises(self, manager: RelationManager) -> None:
        with pytest.raises(ValueError):
            manager.create_relation(uuid4(), uuid4(), "invalid_type")


class TestDuplicateRelation:
    def test_duplicate_prevention(self, manager: RelationManager) -> None:
        s, t = uuid4(), uuid4()
        manager.create_relation(s, t, "owns")
        with pytest.raises(ValueError):
            manager.create_relation(s, t, "owns")


class TestDeleteRelation:
    def test_delete_relation(self, manager: RelationManager) -> None:
        rid = manager.create_relation(uuid4(), uuid4(), "controls")
        assert manager.remove_relation(rid) is True
        assert manager.get_relations(rid) is None


class TestIncomingOutgoing:
    def test_outgoing_lookup(self, manager: RelationManager) -> None:
        s, t = uuid4(), uuid4()
        manager.create_relation(s, t, "owns")
        out = manager.get_outgoing(s)
        assert len(out) == 1
        assert out[0]["target_entity_id"] == str(t)

    def test_incoming_lookup(self, manager: RelationManager) -> None:
        s, t = uuid4(), uuid4()
        manager.create_relation(s, t, "owns")
        inc = manager.get_incoming(t)
        assert len(inc) == 1
        assert inc[0]["source_entity_id"] == str(s)


class TestMultipleRelationTypes:
    def test_multiple_types_same_pair(self, manager: RelationManager) -> None:
        s, t = uuid4(), uuid4()
        manager.create_relation(s, t, "owns")
        manager.create_relation(s, t, "controls")
        assert len(manager.get_outgoing(s)) == 2


class TestThreadSafety:
    def test_concurrent_creations(self, manager: RelationManager) -> None:
        target = uuid4()
        errors = []
        def create_rel() -> None:
            try:
                manager.create_relation(uuid4(), target, "belongs_to")
            except Exception as e:
                errors.append(e)
        threads = [threading.Thread(target=create_rel) for _ in range(10)]
        for th in threads:
            th.start()
        for th in threads:
            th.join()
        assert len(errors) == 0
        assert len(manager.get_incoming(target)) == 10


class TestVersionIncrement:
    def test_version_starts_at_1(self, manager: RelationManager) -> None:
        s, t = uuid4(), uuid4()
        rid = manager.create_relation(s, t, "owns")
        rel = manager.get_relations(rid)
        assert rel is not None
        assert rel["version"] == 1


class TestRepositoryPersistence:
    def test_list_all_persists(self, manager: RelationManager) -> None:
        s, t = uuid4(), uuid4()
        manager.create_relation(s, t, "owns")
        manager.create_relation(t, s, "belongs_to")
        all_rels = manager.get_relations(str(manager.get_outgoing(s)[0]["relation_id"]))
        assert all_rels is not None
        assert len(manager.get_outgoing(s)) == 1
        assert len(manager.get_incoming(s)) == 1
