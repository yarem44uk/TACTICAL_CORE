"""Entity Bridge Module.

Provides the EntityBridge that connects the processing pipeline to the
entity management system via a clean interface boundary.

The bridge operates in best-effort mode — failures are logged but do not
propagate back to the pipeline.
"""

from __future__ import annotations

from .entity_bridge import EntityBridge
from .interfaces import (
    EntityUpdateRequest,
    IEntityBridge,
    IEntityManager,
)

__all__ = [
    "EntityBridge",
    "EntityUpdateRequest",
    "IEntityBridge",
    "IEntityManager",
]
