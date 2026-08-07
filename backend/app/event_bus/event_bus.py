from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

from app.event.event_types import EventType
from app.event_bus.interfaces.i_event_bus import IEventBus
from app.event_bus.subscription import Subscription

if TYPE_CHECKING:
    from collections import defaultdict

logger = logging.getLogger(__name__)


class EventBus(IEventBus):
    """Thread-safe in-memory event bus.

    Subscribes callbacks to event types. On publish, all matching
    callbacks are invoked synchronously. Exceptions in one callback
    do not stop dispatch to the rest.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._subscriptions: dict[EventType, list[Subscription]] = {}

    # ------------------------------------------------------------------
    # subscribe / unsubscribe
    # ------------------------------------------------------------------

    def subscribe(
        self, event_type: EventType, callback: callable
    ) -> Subscription:
        import uuid

        sub = Subscription(
            event_type=event_type,
            callback=callback,
            id=uuid.uuid4().hex,
        )
        with self._lock:
            subs = self._subscriptions.setdefault(event_type, [])
            subs.append(sub)
        return sub

    def unsubscribe(self, subscription: Subscription) -> bool:
        """Remove *subscription*. Returns True if it was present."""
        with self._lock:
            subs = self._subscriptions.get(subscription.event_type)
            if subs is None:
                return False
            before = len(subs)
            subs[:] = [s for s in subs if s.id != subscription.id]
            return len(subs) < before

    # ------------------------------------------------------------------
    # publish
    # ------------------------------------------------------------------

    def publish(self, event: object) -> int:
        """Dispatch *event* to all subscribers of its type.

        Returns the number of callbacks that executed without error.
        """
        try:
            event_type: EventType = event.event_type  # type: ignore[attr-defined]
        except AttributeError:
            logger.warning("publish called with non-Event object: %r", event)
            return 0

        with self._lock:
            subs = list(self._subscriptions.get(event_type, []))

        successes = 0
        for sub in subs:
            try:
                sub.callback(event)
                successes += 1
            except Exception:
                logger.exception(
                    "Subscriber %s raised an exception for event type %s",
                    sub.id,
                    event_type,
                )
        return successes

    # ------------------------------------------------------------------
    # housekeeping
    # ------------------------------------------------------------------

    def clear(self) -> None:
        with self._lock:
            self._subscriptions.clear()

    def subscriber_count(self) -> int:
        with self._lock:
            return sum(len(v) for v in self._subscriptions.values())

    def get_subscribers(self, event_type: EventType) -> list[Subscription]:
        with self._lock:
            return list(self._subscriptions.get(event_type, []))
