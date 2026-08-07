from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from backend.app.event.event_types import EventType
    from collections.abc import Sequence


# Middleware signature: receives event, returns (possibly modified) event or None to drop
MiddlewareFn = Callable[[object], object | None]

# Lifecycle callback signatures
BeforeDispatchFn = Callable[[object], None]
AfterDispatchFn = Callable[[object, int], None]
ErrorDispatchFn = Callable[[object, Exception], None]


class IEventDispatcher(ABC):
    """Event dispatcher interface.

    Sits above EventBus. Adds middleware pipeline and lifecycle hooks
    (before_dispatch, after_dispatch, error_dispatch).
    """

    @abstractmethod
    def dispatch(self, event: object) -> int: ...

    @abstractmethod
    def add_middleware(self, middleware: MiddlewareFn) -> None: ...

    @abstractmethod
    def remove_middleware(self, middleware: MiddlewareFn) -> bool: ...

    @abstractmethod
    def register_before_dispatch(self, callback: BeforeDispatchFn) -> None: ...

    @abstractmethod
    def register_after_dispatch(self, callback: AfterDispatchFn) -> None: ...

    @abstractmethod
    def register_error_dispatch(self, callback: ErrorDispatchFn) -> None: ...

    @abstractmethod
    def clear_middleware(self) -> None: ...

    @abstractmethod
    def clear_hooks(self) -> None: ...

