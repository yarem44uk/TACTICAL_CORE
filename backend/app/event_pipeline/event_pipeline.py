from typing import List, Callable, Any, Optional
from threading import Lock
from .interfaces.i_event_pipeline import IEventPipeline

class EventPipeline(IEventPipeline):
    def __init__(self):
        self._before_middleware: List[Callable[[Any], Any]] = []
        self._filters: List[Callable[[Any], bool]] = []
        self._after_middleware: List[Callable[[Any], Any]] = []
        self._dispatcher: Optional[Any] = None
        self._repository: Optional[Any] = None
        self._event_bus: Optional[Any] = None
        self._lock = Lock()

    def set_dispatcher(self, dispatcher: Any) -> None:
        self._dispatcher = dispatcher

    def set_repository(self, repository: Any) -> None:
        self._repository = repository

    def set_event_bus(self, event_bus: Any) -> None:
        self._event_bus = event_bus

    def process(self, event: Any) -> bool:
        with self._lock:
            # 1. Before Middleware
            for mw in self._before_middleware:
                event = mw(event)
            if event is None:
                return False
            
            # 2. Filters
            for f in self._filters:
                if not f(event):
                    return False
            
            # 3. Dispatcher
            if self._dispatcher and hasattr(self._dispatcher, 'dispatch'):
                self._dispatcher.dispatch(event)
                
            # 4. After Middleware
            for mw in self._after_middleware:
                event = mw(event)
            if event is None:
                return False

            # 5. Repository
            if self._repository and hasattr(self._repository, 'save'):
                self._repository.save(event)
                
            # 6. EventBus
            if self._event_bus and hasattr(self._event_bus, 'publish'):
                self._event_bus.publish(event)
                
        return True

    def add_filter(self, filter_func: Callable[[Any], bool]) -> None:
        with self._lock:
            self._filters.append(filter_func)

    def remove_filter(self, filter_func: Callable[[Any], bool]) -> None:
        with self._lock:
            if filter_func in self._filters:
                self._filters.remove(filter_func)

    def add_before(self, middleware: Callable[[Any], Any]) -> None:
        with self._lock:
            self._before_middleware.append(middleware)

    def add_after(self, middleware: Callable[[Any], Any]) -> None:
        with self._lock:
            self._after_middleware.append(middleware)

    def clear(self) -> None:
        with self._lock:
            self._before_middleware.clear()
            self._filters.clear()
            self._after_middleware.clear()
            self._dispatcher = None
            self._repository = None
            self._event_bus = None
