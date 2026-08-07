from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock

import pytest

from app.event.event import Event
from app.event.event_types import EventType
from app.event.event_status import EventStatus
from app.event_bus.event_bus import EventBus
from app.event_dispatcher.event_dispatcher import EventDispatcher
from app.event_dispatcher.interfaces.i_event_dispatcher import (
    IEventDispatcher,
)


# ------------------------------------------------------------------
# helpers
# ------------------------------------------------------------------

def _make_event(
    event_type: EventType = EventType.SYSTEM_STARTUP,
    entity_id: str = "e1",
    source: str = "test",
) -> Event:
    return Event(
        event_type=event_type,
        entity_id=entity_id,
        source=source,
    )

@pytest.fixture
def event_bus() -> EventBus:
    return EventBus()


@pytest.fixture
def dispatcher(event_bus: EventBus) -> EventDispatcher:
    return EventDispatcher(event_bus)


# ------------------------------------------------------------------
# identity
# ------------------------------------------------------------------

class TestIdentity:
    def test_is_ideventdispatcher(self, dispatcher):
        assert isinstance(dispatcher, IEventDispatcher)

    def test_holds_event_bus_reference(self, event_bus, dispatcher):
        assert dispatcher._event_bus is event_bus


# ------------------------------------------------------------------
# dispatch (basic)
# ------------------------------------------------------------------

class TestDispatch:
    def test_dispatch_calls_subscriber(self, event_bus, dispatcher):
        callback = MagicMock()
        event_bus.subscribe(EventType.SYSTEM_STARTUP, callback)
        ev = _make_event(EventType.SYSTEM_STARTUP)

        result = dispatcher.dispatch(ev)

        assert result == 1
        callback.assert_called_once_with(ev)

    def test_dispatch_returns_zero_when_no_subscribers(self, event_bus, dispatcher):
        ev = _make_event()
        result = dispatcher.dispatch(ev)
        assert result == 0

    def test_dispatch_does_not_call_wrong_event_type_subscriber(self, event_bus, dispatcher):
        callback = MagicMock()
        event_bus.subscribe(EventType.SYSTEM_SHUTDOWN, callback)
        ev = _make_event(EventType.SYSTEM_STARTUP)

        dispatcher.dispatch(ev)

        callback.assert_not_called()


# ------------------------------------------------------------------
# middleware
# ------------------------------------------------------------------

class TestMiddleware:
    def test_middleware_passes_event_through(self, event_bus, dispatcher):
        callback = MagicMock()
        mw = lambda e: e  # identity middleware
        dispatcher.add_middleware(mw)
        event_bus.subscribe(EventType.SYSTEM_STARTUP, callback)
        ev = _make_event(EventType.SYSTEM_STARTUP)

        dispatcher.dispatch(ev)

        callback.assert_called_once()

    def test_middleware_modifies_event(self, event_bus, dispatcher):
        received = []
        callback = lambda e: received.append(e)
        mw = lambda e: Event(
            event_type=EventType.SYSTEM_SHUTDOWN,
            entity_id=e.entity_id,
            source="modified",
        )
        dispatcher.add_middleware(mw)
        event_bus.subscribe(EventType.SYSTEM_SHUTDOWN, callback)
        ev = _make_event(EventType.SYSTEM_STARTUP)

        dispatcher.dispatch(ev)

        assert len(received) == 1
        assert received[0].event_type == EventType.SYSTEM_SHUTDOWN
        assert received[0].source == "modified"

    def test_middleware_drop_event(self, event_bus, dispatcher):
        callback = MagicMock()
        mw = lambda e: None  # drop
        dispatcher.add_middleware(mw)
        event_bus.subscribe(EventType.SYSTEM_STARTUP, callback)
        ev = _make_event(EventType.SYSTEM_STARTUP)

        result = dispatcher.dispatch(ev)

        assert result == 0
        callback.assert_not_called()

    def test_middleware_exception_does_not_stop_dispatch(self, event_bus, dispatcher):
        callback = MagicMock()
        bad_mw = lambda e: (_ for _ in ()).throw(RuntimeError("mw crash"))  # noqa: B018
        good_mw = lambda e: e  # passes through
        dispatcher.add_middleware(bad_mw)
        dispatcher.add_middleware(good_mw)
        event_bus.subscribe(EventType.SYSTEM_STARTUP, callback)
        ev = _make_event(EventType.SYSTEM_STARTUP)

        dispatcher.dispatch(ev)

        # Exception in first middleware should not stop second middleware or dispatch
        callback.assert_called_once()

    def test_remove_middleware(self, dispatcher):
        mw = lambda e: e
        dispatcher.add_middleware(mw)
        assert dispatcher.remove_middleware(mw) is True
        assert dispatcher.remove_middleware(mw) is False

    def test_clear_middleware(self, dispatcher):
        dispatcher.add_middleware(lambda e: e)
        dispatcher.add_middleware(lambda e: e)
        dispatcher.clear_middleware()
        assert len(dispatcher._middleware) == 0


# ------------------------------------------------------------------
# lifecycle hooks
# ------------------------------------------------------------------

class TestLifecycleHooks:
    def test_before_dispatch_called(self, event_bus, dispatcher):
        hook = MagicMock()
        dispatcher.register_before_dispatch(hook)
        ev = _make_event()

        dispatcher.dispatch(ev)

        hook.assert_called_once_with(ev)

    def test_after_dispatch_called_with_success_count(self, event_bus, dispatcher):
        hook = MagicMock()
        dispatcher.register_after_dispatch(hook)
        event_bus.subscribe(EventType.SYSTEM_STARTUP, lambda e: None)
        ev = _make_event(EventType.SYSTEM_STARTUP)

        dispatcher.dispatch(ev)

        hook.assert_called_once_with(ev, 1)

    def test_error_dispatch_registered(self, dispatcher):
        hook = MagicMock()
        dispatcher.register_error_dispatch(hook)
        assert len(dispatcher._error_hooks) == 1

    def test_clear_hooks(self, dispatcher):
        dispatcher.register_before_dispatch(lambda e: None)
        dispatcher.register_after_dispatch(lambda e, c: None)
        dispatcher.register_error_dispatch(lambda e, ex: None)
        dispatcher.clear_hooks()
        assert len(dispatcher._before_hooks) == 0
        assert len(dispatcher._after_hooks) == 0
        assert len(dispatcher._error_hooks) == 0

    def test_before_hook_exception_does_not_stop_dispatch(self, event_bus, dispatcher):
        callback = MagicMock()
        bad_hook = lambda e: (_ for _ in ()).throw(RuntimeError("hook crash"))  # noqa: B018
        dispatcher.register_before_dispatch(bad_hook)
        event_bus.subscribe(EventType.SYSTEM_STARTUP, callback)
        ev = _make_event(EventType.SYSTEM_STARTUP)

        dispatcher.dispatch(ev)

        # dispatch still happens despite bad hook
        callback.assert_called_once()

    def test_after_hook_exception_does_not_stop_dispatch(self, event_bus, dispatcher):
        callback = MagicMock()
        bad_hook = lambda e, c: (_ for _ in ()).throw(RuntimeError("after crash"))  # noqa: B018
        dispatcher.register_after_dispatch(bad_hook)
        event_bus.subscribe(EventType.SYSTEM_STARTUP, callback)
        ev = _make_event(EventType.SYSTEM_STARTUP)

        dispatcher.dispatch(ev)

        callback.assert_called_once()


# ------------------------------------------------------------------
# multiple event types
# ------------------------------------------------------------------

class TestMultipleEventTypes:
    def test_dispatch_different_event_types(self, event_bus, dispatcher):
        cb1 = MagicMock()
        cb2 = MagicMock()
        event_bus.subscribe(EventType.SYSTEM_STARTUP, cb1)
        event_bus.subscribe(EventType.SYSTEM_SHUTDOWN, cb2)

        ev1 = _make_event(EventType.SYSTEM_STARTUP)
        ev2 = _make_event(EventType.SYSTEM_SHUTDOWN)

        dispatcher.dispatch(ev1)
        dispatcher.dispatch(ev2)

        cb1.assert_called_once_with(ev1)
        cb2.assert_called_once_with(ev2)


# ------------------------------------------------------------------
# thread safety
# ------------------------------------------------------------------

class TestThreadSafety:
    def test_concurrent_add_middleware(self, dispatcher):
        mw = lambda e: e
        errors = []

        def add_many():
            for _ in range(100):
                try:
                    dispatcher.add_middleware(mw)
                except Exception as ex:
                    errors.append(ex)

        threads = [threading.Thread(target=add_many) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(dispatcher._middleware) == 500

    def test_concurrent_dispatch_and_modify(self, event_bus, dispatcher):
        event_bus.subscribe(EventType.SYSTEM_STARTUP, lambda e: None)
        ev = _make_event(EventType.SYSTEM_STARTUP)
        errors = []
        barrier = threading.Barrier(3)

        def dispatch_worker():
            barrier.wait()
            for _ in range(50):
                try:
                    dispatcher.dispatch(ev)
                except Exception as ex:
                    errors.append(ex)

        def modify_worker():
            barrier.wait()
            for _ in range(50):
                try:
                    dispatcher.add_middleware(lambda e: e)
                    dispatcher.clear_middleware()
                except Exception as ex:
                    errors.append(ex)

        threads = [
            threading.Thread(target=dispatch_worker),
            threading.Thread(target=dispatch_worker),
            threading.Thread(target=modify_worker),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0

