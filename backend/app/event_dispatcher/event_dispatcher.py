from __future__ import annotations

import logging
import threading
from typing import Callable

from app.event_bus.interfaces.i_event_bus import IEventBus
from app.event_dispatcher.interfaces.i_event_dispatcher import (
    IEventDispatcher,
    BeforeDispatchFn,
    AfterDispatchFn,
    ErrorDispatchFn,
    MiddlewareFn,
)

logger = logging.getLogger(__name__)


class EventDispatcher(IEventDispatcher):
    """Thread-safe event dispatcher sitting above EventBus.

    Adds a middleware pipeline and lifecycle hooks:
      - before_dispatch  (called before EventBus.publish)
      - after_dispatch   (called after EventBus.publish with success count)
      - error_dispatch   (called when a subscriber raises)

    Middleware is executed in registration order. If middleware returns None,
    the event is dropped and no dispatch occurs.
    """

    def __init__(self, event_bus: IEventBus) -> None:
        self._event_bus = event_bus
        self._lock = threading.RLock()
        self._middleware: list[MiddlewareFn] = []
        self._before_hooks: list[BeforeDispatchFn] = []
        self._after_hooks: list[AfterDispatchFn] = []
        self._error_hooks: list[ErrorDispatchFn] = []

    # ------------------------------------------------------------------
    # core dispatch
    # ------------------------------------------------------------------

    def dispatch(self, event: object) -> int:
        """Run middleware pipeline, lifecycle hooks, then publish via EventBus.

        Returns the number of successful subscriber callbacks from EventBus.
        """
        # 1. Run middleware pipeline
        processed_event = event
        with self._lock:
            middleware = list(self._middleware)

        for mw in middleware:
            try:
                result = mw(processed_event)
                if result is None:
                    logger.info("Event dropped by middleware: %r", processed_event)
                    return 0
                processed_event = result
            except Exception:
                logger.exception("Middleware raised an exception: %s", mw)

        event_to_publish = processed_event

        # 2. before_dispatch hooks
        with self._lock:
            before_hooks = list(self._before_hooks)

        for hook in before_hooks:
            try:
                hook(event_to_publish)
            except Exception:
                logger.exception("before_dispatch hook raised: %s", hook)

        # 3. publish via EventBus
        success_count = self._event_bus.publish(event_to_publish)

        # 4. after_dispatch hooks
        with self._lock:
            after_hooks = list(self._after_hooks)

        for hook in after_hooks:
            try:
                hook(event_to_publish, success_count)
            except Exception:
                logger.exception("after_dispatch hook raised: %s", hook)

        return success_count

    # ------------------------------------------------------------------
    # middleware management
    # ------------------------------------------------------------------

    def add_middleware(self, middleware: MiddlewareFn) -> None:
        with self._lock:
            self._middleware.append(middleware)

    def remove_middleware(self, middleware: MiddlewareFn) -> bool:
        with self._lock:
            try:
                self._middleware.remove(middleware)
                return True
            except ValueError:
                return False

    def clear_middleware(self) -> None:
        with self._lock:
            self._middleware.clear()

    # ------------------------------------------------------------------
    # lifecycle hooks
    # ------------------------------------------------------------------

    def register_before_dispatch(self, callback: BeforeDispatchFn) -> None:
        with self._lock:
            self._before_hooks.append(callback)

    def register_after_dispatch(self, callback: AfterDispatchFn) -> None:
        with self._lock:
            self._after_hooks.append(callback)

    def register_error_dispatch(self, callback: ErrorDispatchFn) -> None:
        with self._lock:
            self._error_hooks.append(callback)

    def clear_hooks(self) -> None:
        with self._lock:
            self._before_hooks.clear()
            self._after_hooks.clear()
            self._error_hooks.clear()

