from abc import ABC, abstractmethod
from typing import Any, Callable

class IEventPipeline(ABC):
    @abstractmethod
    def process(self, event: Any) -> bool:
        pass

    @abstractmethod
    def add_filter(self, filter_func: Callable[[Any], bool]) -> None:
        pass

    @abstractmethod
    def remove_filter(self, filter_func: Callable[[Any], bool]) -> None:
        pass

    @abstractmethod
    def add_before(self, middleware: Callable[[Any], Any]) -> None:
        pass

    @abstractmethod
    def add_after(self, middleware: Callable[[Any], Any]) -> None:
        pass

    @abstractmethod
    def clear(self) -> None:
        pass
