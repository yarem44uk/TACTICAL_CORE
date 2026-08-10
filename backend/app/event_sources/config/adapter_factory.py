"""
TACTICAL CORE — Adapter Factory
WO-013-004

Registry/plugin pattern for resolving adapter_type -> IEventSourceAdapter.

The factory contains NO protocol-specific logic and imports no concrete
protocol adapters (MQTT/Signal/Radio/ATAK/MPU5). Concrete adapter builders
are registered externally via register_type().

The factory only constructs adapter instances; it never starts them.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from ..interfaces.i_event_source_adapter import IEventSourceAdapter
from .errors import AdapterTypeError, SourceDefinitionError
from .source_definition import SourceDefinition

# A builder receives the source definition (and optionally a resolved
# credentials reference) and returns a configured IEventSourceAdapter.
AdapterBuilder = Callable[[SourceDefinition], IEventSourceAdapter]


class AdapterFactory:
    """Resolves adapter types to adapter instances via a plugin registry.

    Thread-safe registration and lookup.
    """

    def __init__(self) -> None:
        self._builders: dict[str, AdapterBuilder] = {}
        self._lock = threading.Lock()

    def register_type(self, adapter_type: str, builder: AdapterBuilder) -> None:
        """Register an adapter type with its builder.

        Args:
            adapter_type: Stable identifier for the adapter type.
            builder: Callable that constructs an IEventSourceAdapter from a
                SourceDefinition.

        Raises:
            AdapterTypeError: If the adapter_type is invalid or already
                registered (duplicate registration is a deterministic error).
        """
        if not adapter_type or not isinstance(adapter_type, str) or not adapter_type.strip():
            raise AdapterTypeError("adapter_type must be a non-empty string")
        if not callable(builder):
            raise AdapterTypeError(f"adapter_type '{adapter_type}': builder must be callable")
        with self._lock:
            if adapter_type in self._builders:
                raise AdapterTypeError(
                    f"adapter_type '{adapter_type}' is already registered"
                )
            self._builders[adapter_type] = builder

    def create(self, definition: SourceDefinition) -> IEventSourceAdapter:
        """Construct an adapter instance for the given source definition.

        Args:
            definition: Validated source definition.

        Returns:
            A configured IEventSourceAdapter (NOT started).

        Raises:
            SourceDefinitionError: If the definition is invalid.
            AdapterTypeError: If the adapter_type is unknown/unregistered.
        """
        if not isinstance(definition, SourceDefinition):
            raise SourceDefinitionError("expected a SourceDefinition")
        # Re-validate to guarantee integrity (immutable, idempotent).
        with self._lock:
            builder = self._builders.get(definition.adapter_type)
        if builder is None:
            raise AdapterTypeError(
                f"unknown adapter_type '{definition.adapter_type}' for source "
                f"'{definition.name}'"
            )
        adapter = builder(definition)
        if not isinstance(adapter, IEventSourceAdapter):
            raise AdapterTypeError(
                f"builder for adapter_type '{definition.adapter_type}' did not return "
                "an IEventSourceAdapter"
            )
        return adapter

    def has_type(self, adapter_type: str) -> bool:
        """Return whether an adapter type is registered."""
        with self._lock:
            return adapter_type in self._builders

    def registered_types(self) -> list[str]:
        """Return the sorted list of registered adapter types."""
        with self._lock:
            return sorted(self._builders.keys())

    def unregister_type(self, adapter_type: str) -> None:
        """Remove an adapter type registration (idempotent)."""
        with self._lock:
            self._builders.pop(adapter_type, None)
