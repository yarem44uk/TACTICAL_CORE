# ADR-ENTITY-RELATION-LIFECYCLE — Canonical Entity & Relation Lifecycle, Tombstoning, and Cascade Architecture

## Status
ACCEPTED (ratified)

## Context
The canonical production path (baseline `ab2ac7c`, WO-016 "durable relation projection") projects canonical
Events into durable Entities and durable Relations through the single `DatabaseSessionManager`. Neither
canonical Entities nor canonical Relations carried lifecycle state: a relation, once created, could only be
physically deleted, destroying provenance and preventing historical preservation. Canonical `Event` is
immutable/append-only with an immutable `EventType` taxonomy.

## Problem
- No lifecycle/state on canonical relations or entities.
- Physical deletion was the only removal mechanism, violating "relation termination ≠ relation deletion".
- No canonical lifecycle event contract and no defined entity→relation cascade.
- No deterministic, replayable lifecycle semantics.

## Decision
Adopt a durable-tombstone lifecycle state machine applied as deterministic, per-record transitions within
the existing independent-transaction projection model. Lifecycle removal transitions a record to a durable
terminal state; it NEVER physically deletes the row. Entity deactivation cascades synchronously to relations
referencing that entity. No new `EventType` values are introduced.

## Entity State Machine (v1)
```
ACTIVE
  ↓ ENTITY_REMOVED (logical removal → durable tombstone)
TOMBSTONED  (terminal; no reactivation)
```
- `ACTIVE`: created by `ENTITY_CREATED`, updated by `ENTITY_UPDATED`.
- `TOMBSTONED`: entered only from `ACTIVE` by `ENTITY_REMOVED`; terminal; no out-transitions.
- Row remains durable; physical deletion is NOT a lifecycle operation.

## Relation State Machine (v1)
```
ACTIVE
  ↓ entity-deactivation cascade
INACTIVE  (terminal; no reactivation)
```
- `ACTIVE`: default on relation creation (existing rows backfilled to `ACTIVE`).
- `INACTIVE`: terminal; entered by the entity-deactivation cascade; row remains durable.
- No `SUPERSEDED`, no reactivation, no temporal `valid_from`/`valid_to` fields in v1.
- Deterministic relation identity is unchanged and does not include lifecycle state.

## Entity → Relation Cascade
When an entity transitions `ACTIVE → TOMBSTONED`, every canonical relation where
`source_entity_id == entity OR target_entity_id == entity` transitions `ACTIVE → INACTIVE`.
The cascade is synchronous, deterministic, idempotent, replayable, projection-time, and based on the
canonical lifecycle event. It is NOT atomic with the entity persistence operation (independent transactions).

## Event Contract
- No new `EventType` values. `EventType` taxonomy unchanged.
- `ENTITY_REMOVED` is the canonical logical-removal event; its persistence representation changes from
  physical deletion to durable tombstoning. Canonical Event semantics remain unchanged and immutable.
- No `LINK_CREATED`, `LINK_SEVERED`, `ENTITY_DEACTIVATED`, `RELATION_INVALIDATED`, `RELATION_SUPERSEDED`,
  `TOMBSTONE`, or `SUPERSEDED` event types are introduced.
- Explicit relation-level severance (severing a relation while both endpoints remain ACTIVE) is OUT OF SCOPE
  for this architecture and requires a separate ratified decision.

## Transaction Model
Independent transactions per persistence operation (unchanged):
```
EVENT TX #1
ENTITY TX #2
RELATION TX #3
EVENTBUS after commits
```
No global/implicit transaction. No atomicity is claimed between entity tombstone and relation cascade.
Temporary partial projection state is possible if one transaction succeeds and another fails; it is repaired
by deterministic `Event.seq`-ordered replay/recovery.

## Database Ownership
- Single `DatabaseSessionManager` owner.
- No second engine, no second sessionmaker, no second database owner, no second persistence plane.

## Replay / Idempotency
- Replay processes canonical events in strict `Event.seq` order.
- Guarantees IDEMPOTENCY (reprocessing the same event yields the same result).
- Does NOT guarantee COMMUTATIVITY (arbitrary event reordering is not supported).
- Terminal states make repeated lifecycle events no-ops; the durable event log reconstructs current state
  deterministically.

## Historical Preservation
- Lifecycle transitions do not physically delete rows.
- `terminated_at` is durable where implemented.
- `source_event_id` / provenance and deterministic relation identity are preserved.

## Migration / Read Semantics
- Existing relation rows backfilled to `status='ACTIVE'`; identity/provenance/timestamps preserved.
- Consumers filter lifecycle state at the repository/query layer (active vs historical relations) via the
  canonical read-side. No CQRS/read-model redesign in v1.

## Out of Scope (future decisions)
- SUPERSEDED state; relation reactivation; temporal validity intervals; relation-level severance event;
  new EventType values; CQRS/read-model redesign; replay engine implementation; second DB owner;
  atomic entity/relation transaction.

## Consequences
Positive: auditable lifecycle; replayable/idempotent in `seq` order; historical preservation; no
physical-deletion data loss; deterministic synchronous cascade; single DB owner; fits the existing
projection path. Negative: no atomic entity+relation commit (correctness via idempotent replay, not
atomicity); no reactivation; no temporal intervals; no point-in-time snapshots in v1.
