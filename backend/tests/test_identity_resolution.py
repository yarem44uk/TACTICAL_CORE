from __future__ import annotations
import threading
from typing import List
import pytest
from app.identity_resolution import IdentityManager, MemoryIdentityRepository

@pytest.fixture
def repository() -> MemoryIdentityRepository:
    return MemoryIdentityRepository()

@pytest.fixture
def manager(repository: MemoryIdentityRepository) -> IdentityManager:
    return IdentityManager(repository=repository)

class TestResolveIdentity:
    def test_resolve_existing_identity(self, manager: IdentityManager) -> None:
        manager.register_external_id("ent-1", "signal", "12345", "person")
        assert manager.resolve_identity("signal", "12345", "person") == "ent-1"
    def test_resolve_missing_identity(self, manager: IdentityManager) -> None:
        assert manager.resolve_identity("radio", "999", "device") is None

class TestRegisterExternalId:
    def test_register_external_id(self, manager: IdentityManager) -> None:
        manager.register_external_id("ent-1", "signal", "12345", "person")
        assert manager.resolve_identity("signal", "12345", "person") == "ent-1"
    def test_duplicate_prevention(self, manager: IdentityManager) -> None:
        manager.register_external_id("ent-1", "signal", "12345", "person")
        manager.register_external_id("ent-2", "signal", "12345", "person")
        assert manager.resolve_identity("signal", "12345", "person") == "ent-1"

class TestRegisterAlias:
    def test_register_alias(self, manager: IdentityManager) -> None:
        manager.register_external_id("ent-1", "signal", "12345", "person")
        manager.register_alias("ent-1", "John")
        assert manager.lookup("John") == ["ent-1"]
    def test_lookup_case_insensitive(self, manager: IdentityManager) -> None:
        manager.register_external_id("ent-1", "signal", "12345", "person")
        manager.register_alias("ent-1", " JOHN ")
        assert manager.lookup("john") == ["ent-1"]

class TestMergeIdentity:
    def test_merge_identities(self, manager: IdentityManager) -> None:
        manager.register_external_id("ent-A", "src-A", "ext-A", "person")
        manager.register_external_id("ent-B", "src-B", "ext-B", "person")
        manager.merge_identity("ent-A", "ent-B")
        assert manager.resolve_identity("src-B", "ext-B", "person") == "ent-A"
    def test_alias_transfer_after_merge(self, manager: IdentityManager) -> None:
        manager.register_external_id("ent-A", "src-A", "ext-A", "person")
        manager.register_external_id("ent-B", "src-B", "ext-B", "person")
        manager.register_alias("ent-B", "AliasB")
        manager.merge_identity("ent-A", "ent-B")
        assert "ent-A" in manager.lookup("AliasB")

class TestRepositoryPersistence:
    def test_repository_retains_data(self, repository: MemoryIdentityRepository) -> None:
        data = {"identity_key": "k1", "entity_id": "e1", "aliases": []}
        repository.save(data)
        assert repository.get("k1") == data

class TestConcurrency:
    def test_concurrent_register(self, manager: IdentityManager, repository: MemoryIdentityRepository) -> None:
        def worker(i: int) -> None:
            manager.register_external_id(f"ent-{i}", f"src-{i}", f"ext-{i}", "type")
        threads = [threading.Thread(target=worker, args=(i,)) for i in range(50)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert len(repository.list_all()) == 50
    def test_concurrent_resolve(self, manager: IdentityManager) -> None:
        manager.register_external_id("ent-1", "src-1", "ext-1", "type")
        errors: List[Exception] = []
        def worker() -> None:
            try: manager.resolve_identity("src-1", "ext-1", "type")
            except Exception as e: errors.append(e)
        threads = [threading.Thread(target=worker) for _ in range(50)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert len(errors) == 0
