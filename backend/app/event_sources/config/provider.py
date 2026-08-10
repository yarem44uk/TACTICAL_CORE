"""
TACTICAL CORE — Source Config Provider Interface
WO-013-004

Abstract contract for supplying/reading source configuration.

A provider only loads and exposes SourceDefinition objects. It must NOT:
- spawn threads
- start/stop/restart adapters
- poll sources
- manage lifecycle
- implement restart logic
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from .source_definition import SourceDefinition


class ISourceConfigProvider(ABC):
    """Contract for reading source configuration."""

    @abstractmethod
    def load(self) -> None:
        """Load (or reload) the source configuration into memory.

        Raises SourceConfigError on invalid configuration.
        """

    @abstractmethod
    def list_sources(self) -> list[SourceDefinition]:
        """Return all configured source definitions."""

    @abstractmethod
    def get_source(self, name: str) -> SourceDefinition:
        """Return the source definition for the given name.

        Raises SourceNotFoundError if no such source exists.
        """
