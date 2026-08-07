import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest

from app.event.event import Event
from app.event.event_metadata import EventMetadata
from app.event.event_types import EventType
from app.event_repository.memory_event_repository import MemoryEventRepository


def _make_event(
    event_type: EventType = EventType.CUSTOM,
    source: str = "test_source",
    correlation_id: str | None = None,
) -> Event:
    metadata = EventMetadata(correlation_id=correlation_id) if correlation_id else EventMetadata()
    return Event(
        event_id=f"evt_{uuid.uuid4().hex[:12]}",
        entity_id="ent_test",
        event_type=event_type,
        source=source,
        payload={"data": "test"},
        metadata=metadata,
    )


class TestMemoryEventRepository:
    @pytest.fixture
    def repo(self):
        return MemoryEventRepository()

    def test_save_and_get(self, repo: MemoryEventRepository):
        evt = _make_event()
        repo.save(evt)
        result = repo.get(evt.event_id)
        assert result is not None
        assert result.event_id == evt.event_id
        assert result.event_type == evt.event_type

    def test_get_nonexistent(self, repo: MemoryEventRepository):
        assert repo.get("nonexistent_id") is None

    def test_exists_true(self, repo: MemoryEventRepository):
        evt = _make_event()
        repo.save(evt)
        assert repo.exists(evt.event_id) is True

    def test_exists_false(self, repo: MemoryEventRepository):
        assert repo.exists("nonexistent_id") is False

    def test_delete_existing(self, repo: MemoryEventRepository):
        evt = _make_event()
        repo.save(evt)
        assert repo.delete(evt.event_id) is True
        assert repo.exists(evt.event_id) is False

    def test_delete_nonexistent(self, repo: MemoryEventRepository):
        assert repo.delete("nonexistent_id") is False

    def test_count_initial(self, repo: MemoryEventRepository):
        assert repo.count() == 0

    def test_count_after_saves(self, repo: MemoryEventRepository):
        for _ in range(5):
            repo.save(_make_event())
        assert repo.count() == 5

    def test_list_all_empty(self, repo: MemoryEventRepository):
        assert repo.list_all() == []

    def test_list_all_populated(self, repo: MemoryEventRepository):
        events = [_make_event() for _ in range(3)]
        for e in events:
            repo.save(e)
        assert len(repo.list_all()) == 3

    def test_list_by_type(self, repo: MemoryEventRepository):
        repo.save(_make_event(event_type=EventType.CUSTOM))
        repo.save(_make_event(event_type=EventType.SYSTEM_STARTUP))
        repo.save(_make_event(event_type=EventType.CUSTOM))
        assert len(repo.list_by_type(EventType.CUSTOM)) == 2
        assert len(repo.list_by_type(EventType.SYSTEM_STARTUP)) == 1

    def test_list_by_source(self, repo: MemoryEventRepository):
        repo.save(_make_event(source="src_1"))
        repo.save(_make_event(source="src_2"))
        repo.save(_make_event(source="src_1"))
        assert len(repo.list_by_source("src_1")) == 2
        assert len(repo.list_by_source("src_2")) == 1

    def test_list_by_correlation(self, repo: MemoryEventRepository):
        repo.save(_make_event(correlation_id="corr_X"))
        repo.save(_make_event(correlation_id="corr_Y"))
        repo.save(_make_event(correlation_id="corr_X"))
        assert len(repo.list_by_correlation("corr_X")) == 2
        assert len(repo.list_by_correlation("corr_Y")) == 1
        assert len(repo.list_by_correlation("corr_Z")) == 0

    def test_save_overwrites_existing(self, repo: MemoryEventRepository):
        evt1 = _make_event(event_type=EventType.SYSTEM_STARTUP)
        repo.save(evt1)
        evt2 = _make_event(event_type=EventType.CUSTOM)
        # Create new event with same ID to test overwrite
        evt2 = Event(
            event_id=evt1.event_id,
            entity_id="ent_test",
            event_type=EventType.CUSTOM,
            source="test_source",
            payload={"data": "new"},
            metadata=EventMetadata(),
        )
        repo.save(evt2)
        assert repo.count() == 1
        retrieved = repo.get(evt1.event_id)
        assert retrieved is not None
        assert retrieved.event_type == EventType.CUSTOM

    def test_delete_removes_from_queries(self, repo: MemoryEventRepository):
        evt = _make_event(event_type=EventType.CUSTOM, source="target_src", correlation_id="corr")
        repo.save(evt)
        repo.delete(evt.event_id)
        assert repo.list_by_type(EventType.CUSTOM) == []
        assert repo.list_by_source("target_src") == []
        assert repo.list_by_correlation("corr") == []

    def test_thread_safety_concurrent_saves(self, repo: MemoryEventRepository):
        num_threads = 20
        num_events_per_thread = 50

        def _save_batch():
            for _ in range(num_events_per_thread):
                repo.save(_make_event())

        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(_save_batch) for _ in range(num_threads)]
            for f in as_completed(futures):
                f.result()

        assert repo.count() == num_threads * num_events_per_thread

    def test_thread_safety_concurrent_mixed_operations(self, repo: MemoryEventRepository):
        for i in range(10):
            repo.save(_make_event(event_type=EventType.CUSTOM))

        def _read_ops():
            for _ in range(50):
                repo.list_all()
                repo.list_by_type(EventType.CUSTOM)
                repo.count()

        def _write_ops():
            for _ in range(50):
                repo.save(_make_event(event_type=EventType.CUSTOM))

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(_read_ops) for _ in range(5)]
            futures += [executor.submit(_write_ops) for _ in range(5)]
            for f in as_completed(futures):
                f.result()

        assert repo.count() == 10 + 250

    def test_metadata_preservation(self, repo: MemoryEventRepository):
        custom_meta = EventMetadata(
            correlation_id="abc123",
            tags=["a", "b"],
            properties={"priority": "high"},
        )
        evt = Event(
            event_id="evt_meta_test",
            entity_id="ent_1",
            event_type=EventType.CUSTOM,
            source="sys",
            payload={"x": 1},
            metadata=custom_meta,
        )
        repo.save(evt)
        retrieved = repo.get("evt_meta_test")
        assert retrieved is not None
        assert retrieved.metadata.correlation_id == "abc123"
        assert retrieved.metadata.tags == ["a", "b"]
        assert retrieved.metadata.properties == {"priority": "high"}

    def test_empty_correlation_filter(self, repo: MemoryEventRepository):
        repo.save(_make_event())  # no correlation_id
        repo.save(_make_event(correlation_id="exists"))
        assert len(repo.list_by_correlation("missing")) == 0

    def test_multiple_events_same_type(self, repo: MemoryEventRepository):
        ids = []
        for i in range(5):
            evt = _make_event(event_type=EventType.CUSTOM, source=f"src_{i}")
            repo.save(evt)
            ids.append(evt.event_id)
        all_custom = repo.list_by_type(EventType.CUSTOM)
        assert len(all_custom) == 5

    def test_repository_isolation(self):
        repo_a = MemoryEventRepository()
        repo_b = MemoryEventRepository()
        repo_a.save(_make_event())
        assert repo_a.count() == 1
        assert repo_b.count() == 0

    def test_save_preserves_timestamp(self, repo: MemoryEventRepository):
        evt = _make_event()
        original_ts = evt.timestamp
        repo.save(evt)
        retrieved = repo.get(evt.event_id)
        assert retrieved is not None
        assert retrieved.timestamp == original_ts

    def test_list_by_type_no_match(self, repo: MemoryEventRepository):
        repo.save(_make_event(event_type=EventType.CUSTOM))
        assert repo.list_by_type(EventType.SYSTEM_ERROR) == []

    def test_list_by_source_no_match(self, repo: MemoryEventRepository):
        repo.save(_make_event(source="known"))
        assert repo.list_by_source("unknown") == []
