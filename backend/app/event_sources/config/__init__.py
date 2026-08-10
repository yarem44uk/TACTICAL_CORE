"""
TACTICAL CORE — Event Source Configuration Management
WO-013-004

Configuration layer for describing and loading event source definitions.

This layer ONLY describes/loads configuration. It does NOT:
- spawn threads
- start/stop/restart adapters
- poll sources
- manage lifecycle
- implement restart logic
"""

from .adapter_factory import AdapterFactory
from .errors import (
    AdapterTypeError,
    DuplicateSourceError,
    SourceConfigError,
    SourceDefinitionError,
    SourceNotFoundError,
)
from .provider import ISourceConfigProvider
from .source_definition import SourceDefinition

__all__ = [
    "AdapterFactory",
    "AdapterTypeError",
    "DuplicateSourceError",
    "ISourceConfigProvider",
    "SourceConfigError",
    "SourceDefinition",
    "SourceDefinitionError",
    "SourceNotFoundError",
]
