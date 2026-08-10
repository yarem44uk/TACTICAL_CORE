"""
TACTICAL CORE — Source Definition
WO-013-004

Immutable description of a configured event source.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .errors import SourceDefinitionError


@dataclass(frozen=True)
class SourceDefinition:
    """Immutable configuration describing one event source.

    Attributes:
        name: Unique source identifier. Required, non-empty.
        enabled: Whether the source should be started.
        adapter_type: Which adapter type to use. Required, non-empty.
        config: Adapter-specific configuration (opaque to the config layer).
        credentials_ref: Reference/key to a credential store entry. Secrets
            are NEVER stored inline in the definition — only a reference.

    Validation:
        - name is required and must be non-empty
        - adapter_type is required and must be non-empty
        - duplicates are rejected at the provider/loader level (not here)
    """

    name: str
    adapter_type: str
    enabled: bool = True
    config: dict[str, Any] = field(default_factory=dict)
    credentials_ref: str | None = None

    def __post_init__(self) -> None:
        if not self.name or not isinstance(self.name, str) or not self.name.strip():
            raise SourceDefinitionError("source 'name' is required and must be non-empty")
        if not self.adapter_type or not isinstance(self.adapter_type, str) or not self.adapter_type.strip():
            raise SourceDefinitionError(
                f"source '{self.name}': 'adapter_type' is required and must be non-empty"
            )
        # Secrets must be represented only by reference, never inline.
        if self.credentials_ref is not None and not isinstance(self.credentials_ref, str):
            raise SourceDefinitionError(
                f"source '{self.name}': 'credentials_ref' must be a string reference"
            )
