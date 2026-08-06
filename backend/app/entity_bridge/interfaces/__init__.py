"""
EntityBridge Interfaces Package.

Defines the contracts that EntityBridge implements and depends on:

- :class:`IEntityManager` — the entity management contract (dependency).
- :class:`IEntityBridge` — the bridge contract (implemented by EntityBridge).
- :class:`EntityUpdateRequest` — data carrier between bridge and manager.
"""
from __future__ import annotations

from .entity_update_request import EntityUpdateRequest
from .i_entity_bridge import IEntityBridge
from .i_entity_manager import IEntityManager

__all__ = [
    "EntityUpdateRequest",
    "IEntityBridge",
    "IEntityManager",
]
