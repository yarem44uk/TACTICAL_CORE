from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest

from app.event.event import Event
from app.event.event_types import EventType
from app.event_bus.event_bus import EventBus


def _make_event(event_type: EventType = EventType.ENTITY_CREATED) -> Event:
    return Event(
        entity_id="e-001",
        event_type=event_type,
        source="test",
        payload={"test": True},
    )


class TestSubscribe:
    def test_subscribe_returns_subscription(self):
        bus = EventBus()
        sub = bus.subscribe(EventType.ENTITY_CREATED, lambda e: None)
        assert sub is not None
        assert sub.event_type == EventType.ENTITY_CREATED

    def test_subscribe_increases_count(self):
        bus = EventBus()
        bus.subscribe(EventType.ENTITY_CREATED, lambda e: None)
        assert bus.subscriber_count() == 1

    def test_duplicate_subscriptions_allowed(self):
        bus = EventBus()
        cb = lambda e: None
        s1 = bus.subscribe(EventType.ENTITY_CREATED, cb)
        s2 = bus.subscribe(EventType.ENTITY_CREATED, cb)
        assert s1.id != s2.id
        assert bus.subscriber_count() == 2


class TestUnsubscribe:
    def test_unsubscribe_removes(self):
        bus = EventBus()
        sub = bus.subscribe(EventType.ENTITY_CREATED, lambda e: None)
        assert bus.unsubscribe(sub) is True
        assert bus.subscriber_count() == 0

    def test_unsubscribe_nonexistent_returns_false(self):
        bus = EventBus()
        sub = bus.subscribe(EventType.ENTITY_CREATED, lambda e: None)
        bus.unsubscribe(sub)
        assert bus.unsubscribe(sub) is False

    def test_unsubscribe_idempotent(self):
        bus = EventBus()
        sub = bus.subscribe(EventType.ENTITY_CREATED, lambda e: None)
        assert bus.unsubscribe(sub) is True
        assert bus.unsubscribe(sub) is False


class TestPublish:
    def test_publish_calls_subscriber(self):
        bus = EventBus()
        received = []
        bus.subscribe(EventType.ENTITY_CREATED, received.append)
        event = _make_event()
        assert bus.publish(event) == 1
        assert len(received) == 1
        assert received[0] is event

    def test_publish_multiple_subscribers(self):
        bus = EventBus()
        r1, r2 = [], []
        bus.subscribe(EventType.ENTITY_CREATED, r1.append)
        bus.subscribe(EventType.ENTITY_CREATED, r2.append)
        assert bus.publish(_make_event()) == 2
        assert len(r1) == 1
        assert len(r2) == 1

    def test_publish_only_matching_type(self):
        bus = EventBus()
        r1, r2 = [], []
        bus.subscribe(EventType.ENTITY_CREATED, r1.append)
        bus.subscribe(EventType.ENTITY_REMOVED, r2.append)
        bus.publish(_make_event(EventType.ENTITY_CREATED))
        assert len(r1) == 1
        assert len(r2) == 0

    def test_publish_without_subscribers(self):
        bus = EventBus()
        assert bus.publish(_make_event()) == 0

    def test_publish_non_event_object(self):
        bus = EventBus()
        assert bus.publish("not_an_event") == 0

    def test_subscriber_exception_isolation(self):
        bus = EventBus()
        received = []
        def bad_cb(e):
            raise ValueError("boom")
        bus.subscribe(EventType.ENTITY_CREATED, bad_cb)
        bus.subscribe(EventType.ENTITY_CREATED, received.append)
        assert bus.publish(_make_event()) == 1
        assert len(received) == 1


class TestClear:
    def test_clear_removes_all(self):
        bus = EventBus()
        bus.subscribe(EventType.ENTITY_CREATED, lambda e: None)
        bus.subscribe(EventType.ENTITY_REMOVED, lambda e: None)
        bus.clear()
        assert bus.subscriber_count() == 0


class TestThreadSafety:
    def test_concurrent_subscribe_and_publish(self):
        bus = EventBus()
        received = []
        lock = threading.Lock()

        def subscriber(e):
            with lock:
                received.append(e)

        bus.subscribe(EventType.ENTITY_CREATED, subscriber)

        def publisher():
            for _ in range(50):
                bus.publish(_make_event())

        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(publisher) for _ in range(4)]
            for f in as_completed(futures):
                f.result()

        assert len(received) == 200


class TestGetSubscribers:
    def test_get_subscribers_returns_list(self):
        bus = EventBus()
        sub = bus.subscribe(EventType.ENTITY_CREATED, lambda e: None)
        assert len(bus.get_subscribers(EventType.ENTITY_CREATED)) == 1

    def test_get_subscribers_empty(self):
        bus = EventBus()
        assert bus.get_subscribers(EventType.ENTITY_CREATED) == []
