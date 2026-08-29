# ADR-012 — Operational Classification and Severity Model

## Status
Proposed

## Context

TACTICAL CORE models operational events as immutable canonical facts. Each event carries a durable, authoritative record (event identity, timestamp, type, source, payload, correlation/trace identifiers, delivery state). This immutable core is the single source of truth for what happened.

The Operator / Situational Awareness layer (WO-037 series, ADR-011) requires a notion of operational criticality to support filtering, triage, sorting, and visual emphasis. There is currently **no authoritative severity field** on the canonical or durable event model, and the system has no formal model separating an event's inherent classification from the operator's contextual assessment.

The core requirement is therefore: **give operators a way to reason about and filter event criticality WITHOUT mutating or reinterpreting the immutable canonical fact, and WITHOUT inventing a second source of truth.**

This ADR formally separates three concepts that are frequently conflated: the immutable fact, its deterministic baseline classification, and the contextual operational assessment.

## Problem

1. TACTICAL CORE has immutable canonical facts, but no authoritative severity.
2. Operators need a concept of operational criticality for filtering/triage.
3. A severity value cannot be a mutation of the canonical event (it is not a fact about the event itself, it is an assessment).
4. Different stakeholders use "priority", "severity", "urgency", and "confidence" interchangeably, causing semantic overlap.
5. Any future classification must be reproducible, deterministic, read-only, offline-capable, and must not become a dependency of durable ingestion.

## Decision

- **ADOPT_OPERATIONAL_CLASSIFICATION_MODEL = YES** — TACTICAL CORE adopts a three-part model: immutable canonical fact, deterministic baseline classification, and separate contextual operational assessment.
- **CANONICAL_SEVERITY_FIELD = NO** — `severity` is NOT added as a field to `CanonicalEvent`.
- **DURABLE_CANONICAL_SEVERITY_FIELD = NO** — `severity` is NOT added to `DurableCanonicalEvent` or any migration by this ADR.
- **SEPARATE_OPERATIONAL_ASSESSMENT = YES** — operational assessment is modeled as separate, mutable, contextual operator state, distinct from the canonical fact.
- **BASELINE_CLASSIFICATION = YES** — a deterministic, derived, read-only baseline classification is an architectural concept.
- **NEW_DURABLE_STATE = NOT AUTHORIZED BY ADR-012** — this ADR introduces no new tables, columns, checkpoints, or durable state.
- **SCHEMA_CHANGE = NOT AUTHORIZED BY ADR-012** — this ADR introduces no schema/migration change.

## Definitions

Each term is defined separately and must not overlap semantically.

| Term | Definition | Question it answers | Owner | Mutability | Persistence |
| --- | --- | --- | --- | --- | --- |
| **Priority** | The relative order in which an item should be processed/handled. | "In what order should this be handled?" | Processing/workflow | Contextual | Process/workflow-scoped |
| **Severity** | The assessed degree of potential or actual operational impact (see Severity Definition). | "How operationally impactful is this?" | Baseline classifier / operator | Baseline: read-only; assessment: contextual | Separate from canonical |
| **Urgency** | The time-sensitivity — how quickly action is required. | "How soon must this be acted on?" | Operational/operator context | Contextual | Separate from canonical |
| **Confidence** | The degree of certainty in the underlying fact or assessment. | "How certain are we?" | Ingest/classifier/operator | Contextual | Separate from canonical |
| **Operational Assessment** | A contextual, possibly operator-authored judgement about an event's operational meaning. | "What does this mean for the mission right now?" | Operator / triage | Mutable | Separate from canonical |

**Key distinctions (non-overlapping):**
- **Priority != Severity** — priority orders handling; severity measures impact.
- **Severity != Urgency** — severity measures impact; urgency measures time-sensitivity.
- **Severity != Confidence** — severity measures impact; confidence measures certainty.
- **Confidence != Urgency** — certainty is not time-sensitivity.

## Architectural Model

Three distinct layers, each with a distinct ownership and mutability:

```
SOURCE
   provides raw / vendor information
        ↓
INGESTION NORMALIZATION
   normalizes source-specific facts into canonical form
        ↓
BASELINE CLASSIFIER
   derives a deterministic baseline classification from authoritative event facts
        ↓
OPERATOR / TRIAGE
   may create a contextual operational assessment (separate, mutable)
```

### Baseline Classification

**BASELINE_CLASSIFICATION** is:

- **deterministic** — same input produces same output;
- **derived from authoritative event facts** — it is a function of the immutable canonical event;
- **reproducible** — can be recomputed identically at any time;
- **read-only** — it is an interpretation of the fact, not a mutation of it;
- **not a mutation of canonical event** — it never rewrites event fields;
- **not a second source of truth** — it is derived from, and subordinate to, the canonical event.

Admissible inputs to baseline classification include (but the concrete mapping rules are a separate decision):

- `event_type`
- `source`
- normalized event attributes
- authoritative payload attributes

### Operational Assessment

**OPERATIONAL_ASSESSMENT** is a contextual assessment that may differ from the baseline classification (e.g., an operator may reclassify severity based on current mission context). It is:

- separate from the canonical event;
- mutable contextual operator state;
- NOT a field of `CanonicalEvent`.

## Authority and Ownership

No layer may silently redefine another layer's semantics:

- **SOURCE** provides raw/vendor information; it does not define the canonical meaning.
- **INGESTION NORMALIZATION** normalizes source-specific facts; it does not author an authoritative severity taxonomy.
- **BASELINE CLASSIFIER** derives a deterministic baseline classification from authoritative facts; it does not mutate the event.
- **OPERATOR / TRIAGE** may create a contextual operational assessment; it does not rewrite the canonical fact.

Each layer owns its own semantics and must not silently override another layer's semantics.

## Immutability Rules

- **Canonical Event = immutable fact.**
- **Baseline classification = deterministic interpretation of that fact** (read-only, derived).
- **Operational assessment = separate mutable state.**

An operational assessment MUST NOT overwrite:

- event identity
- event timestamp
- event type
- source
- payload
- canonical event fields
- durable canonical record

## Replay Semantics

- Baseline classification is **deterministic and replayable** — recomputing it over the same authoritative events yields the same result.
- Baseline classification is **independent of mutable operator assessment** — operator changes never affect the derived classification of a given event.
- If classification-rule versioning is ever needed, it is an open decision; this ADR does not specify a mechanism.

## Persistence Rules

- `CanonicalEvent.severity = NO` (until a separate approved decision).
- `DurableCanonicalEvent.severity = NO` (until a separate approved decision).
- If baseline classification must ever be cached/persisted, that is a **separate architecture decision** (new durable state is NOT authorized by ADR-012).
- No new tables, columns, checkpoints, or durable state are introduced by this ADR.

## Operator Semantics

Operators may use both:

- **baseline classification**, and
- **operational assessment**

for:

- filtering
- sorting
- triage
- visual emphasis

but doing so does not change the canonical fact. Operator severity filtering (a prospective WO-037-06 item) would operate over these derived/contextual concepts, not over a canonical mutation.

## Security

Severity/assessment must not bypass existing controls:

- authentication
- authorization
- read-only guarantees
- operator process isolation

## Offline Constraints

This model preserves:

- offline runtime
- no cloud dependency
- no external IdP
- no telemetry

## Protected Core

Without a separate ADR, this model does not permit changes to:

- `CanonicalEvent`
- `DurableCanonicalEvent`
- migrations
- `EventPipeline`
- `DurableDeliveryDispatcher`
- `ReconstructionService`
- projection / checkpoint
- outbox
- retry / dead-letter

## Alternatives Considered

1. **Add `severity` directly to CanonicalEvent** — Rejected. Severity is an assessment, not an immutable fact; embedding it would couple mutable context into the immutable record and create a canonical-semantics change.
2. **Add `severity` to DurableCanonicalEvent (schema change)** — Rejected for MVP. Requires migration and alters the durable record; this ADR deliberately does not authorize schema/durable-state change.
3. **Single global severity field with no baseline/assessment split** — Rejected. Conflates deterministic classification with contextual assessment and enables silent semantic overlap (priority/severity/urgency/confidence).
4. **No severity model at all** — Rejected. Operators cannot filter/triage without a criticality concept.
5. **Three-part model (fact / baseline classification / operational assessment)** — **Adopted.** Cleanly separates immutable fact from deterministic interpretation from mutable context, preserving the canonical core and enabling read-only operator filtering.

## Consequences

Positive:
- Operator can filter/triage on a criticality concept without mutating the canonical event.
- Baseline classification is deterministic, replayable, and independent of operator context.
- No schema change, no new durable state, no protected-core change, no new dependency, offline preserved.

Negative / open:
- Final severity taxonomy is not defined by this ADR (separate decision).
- Concrete baseline-classifier mapping rules and rule ownership are not defined (separate decision).
- Operational assessment persistence/audit model is not defined (separate decision).
- Operator filtering semantics are not yet specified (prospective WO-037-06 scope).

## Open Decisions

The following are intentionally left as separate follow-up decisions (NOT decided by ADR-012):

1. Final severity taxonomy (values, ordering).
2. Baseline classifier rule ownership.
3. Classification-rule versioning.
4. Operational assessment persistence model.
5. Operational assessment lifecycle.
6. Audit model (who/what/when/previous/new/reason) — mechanism, not whether audit is needed.
7. Operator filtering semantics (prospective WO-037-06).

## Non-Goals

- No `severity` field on CanonicalEvent or DurableCanonicalEvent.
- No schema/migration change.
- No new durable state (tables/columns/checkpoints).
- No implementation of a baseline classifier in this ADR.
- No implementation of operational assessment storage.
- No concrete severity taxonomy in this ADR.
- No change to the protected core.
- No new external dependency, no cloud/IdP/telemetry dependency.

## Acceptance / Governance Notes

- ADR-012 is a **Proposed** architecture decision establishing the conceptual model only.
- It authorizes no implementation, no schema change, no new durable state, and no WO-037-06 scope.
- Any subsequent implementation (e.g., operator severity filtering) requires its own Work Order and independent audit, and must comply with the immutability, authority, persistence, security, offline, and protected-core rules above.
