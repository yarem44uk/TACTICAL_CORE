"""Entity Management Module.

Provides entity management for Intelligence Core.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from app.intelligence.entity.types import EntityType, EntityStatus, EntityRelationType, Priority
from app.intelligence.entity.entity import Entity, EntityData, ExternalIdentity
from app.intelligence.entity.identity import IdentityResolver
from app.intelligence.entity.relations import EntityRelations, Relation
from app.intelligence.entity.entity_manager import EntityManager, EntityRepository


__all__ = [
    "EntityType",
    "EntityStatus",
    "EntityRelationType",
    "Priority",
    "Entity",
    "EntityData",
    "IdentityResolver",
    "ExternalIdentity",
    "EntityRelations",
    "Relation",
    "EntityManager",
    "EntityRepository",
]
