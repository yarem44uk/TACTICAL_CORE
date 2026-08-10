"""
TACTICAL CORE — Event Source Configuration Errors
WO-013-004

Exception hierarchy for source configuration management.
"""

from __future__ import annotations


class SourceConfigError(Exception):
    """Base error for source configuration problems.

    Raised when a source definition is invalid, cannot be loaded, or
    cannot be resolved into an adapter.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class SourceDefinitionError(SourceConfigError):
    """Raised when a SourceDefinition fails validation.

    Covers missing/invalid name, missing/invalid adapter_type, and
    duplicate source names.
    """


class SourceNotFoundError(SourceConfigError):
    """Raised when a requested source is not present in configuration."""


class AdapterTypeError(SourceConfigError):
    """Raised when an adapter type cannot be resolved.

    Covers unknown adapter types and duplicate adapter type registration.
    """


class DuplicateSourceError(SourceConfigError):
    """Raised when a source name is registered more than once."""
