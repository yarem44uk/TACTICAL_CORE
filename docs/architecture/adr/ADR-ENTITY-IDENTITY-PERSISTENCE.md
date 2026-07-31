# ADR-ENTITY-IDENTITY-PERSISTENCE

## Architecture Decision Record

**Entity Identity Persistence Strategy**

---

## Status

ACCEPTED

---

## Context

When TACTICAL CORE creates Entities from Observations through the EntityBridge,
identity resolution must ensure that the same external identity always resolves
to the same Entity, even when:

- A new EntityManager instance is created
- The application restarts
- The repository is reloaded from persistent storage

The key architectural question is: **How does TACTICAL CORE preserve identity
resolution across EntityManager and persistence lifecycles?**

---

## Decision

**Identity mappings are stored in the Repository alongside Entities.**

The `EntityManager.resolve_or_create()` method:

1. First checks `repository.resolve_by_identity(source, external_id)`
2. If found, returns existing Entity
3. If not found, creates new Entity
4. New Entity's `external_ids` dict stores the mapping
5. `Repository.save()` persists both Entity and extracts identity mappings

### Implementation

The `InMemoryEntityRepository` (and by contract any Repository implementation)
stores identity mappings in a `_identities` dict:

```python
# Repository stores: (source, external_id) -> entity_id
self._identities: Dict[tuple[str, str], UUID] = {}

async def resolve_by_identity(self, source: str, external_id: str) -> Optional[UUID]:
    return self._identities.get((source, external_id))

async def save(self, entity: Entity) -> Entity:
    self._entities[str(entity.id)] = entity
    # Extract and store identity mappings
    for source, external_id in entity.external_ids.items():
        self._identities[(source, external_id)] = entity.id
    return entity
```

The `EntityManager.resolve_or_create()` delegates to repository:

```python
async def resolve_or_create(self, ...) -> tuple[Entity, bool]:
    # Try repository identity lookup first (persistent)
    existing_id = await self._repository.resolve_by_identity(source, external_id)
    if existing_id:
        entity = await self._repository.get(existing_id)
        if entity:
            return entity, False  # existing, not created

    # Create new
    entity = Entity.create(...)
    entity.external_ids[source] = external_id
    await self._repository.save(entity)
    return entity, True  # created
```

---

## Consequences

### Positive

- Identity mappings survive EntityManager recreation
- Same repository = same identity resolution
- No need for global singleton or memory-only IdentityResolver
- Follows the Repository pattern consistently
- SQLAlchemyEntityRepository can persist to SQLite

### Negative

- Identity mappings are tightly coupled to Entity storage
- Requires Repository implementations to maintain identity index
- External IDs must be stored on Entity (already required by architecture)

### Neutral

- IdentityResolver (memory-only) is not used by resolve_or_create
- Could be removed or repurposed for other identity operations

---

## Alternatives Considered

### A: Persistent IdentityResolver with own storage

Store identity mappings in a separate table/entity.

**Rejected**: Adds complexity, requires separate persistence mechanism,
and IdentityResolver doesn't add value over repository-based resolution.

### B: Global singleton IdentityResolver

Keep IdentityResolver as a singleton.

**Rejected**: Violates clean lifecycle management, doesn't survive
application restart if singleton is in-memory only.

### C: Entity owns all identity state

Include full identity history in Entity.

**Rejected**: Entity becomes mutable, violates some constitutional rules
about immutability of evidence.

---

## Persistence Lifecycle

```
EntityManager.create()/resolve_or_create()
    ↓
Repository.resolve_by_identity() - check persistent storage
    ↓
If exists → return existing Entity (created=False)
If not → Entity.create() → Repository.save() → identity indexed
    ↓
Entity + identity mapping persisted together
```

After restart:

```
New EntityManager(repository=existing_repo)
    ↓
resolve_or_create() → Repository.resolve_by_identity()
    ↓
Finds identity in repository's _identities
    ↓
Returns existing Entity (created=False)
```

---

## Failure Behavior

### Repository resolve fails

- If `resolve_by_identity()` raises, error propagates
- No phantom Entity created
- Transaction behavior depends on Repository implementation

### Entity not found after identity resolution

- If identity resolves to ID but `get(ID)` returns None
- System is inconsistent (identity exists but Entity doesn't)
- Should not happen in normal operation

---

## Migration Considerations

Existing code that creates Entities without registering external_ids
will not benefit from identity persistence.

Migration path:
1. All Entity creation should use `resolve_or_create()` with external_id
2. Or ensure `external_ids` is populated before `save()`

---

## References

- WO-008-016: Persistent Identity Resolution
- ENTITY-001 Constitutional Architecture
- CV1: Identity-First resolution
- Repository pattern implementation

---

**Decision Date:** 2026-01
**Status:** ACCEPTED
