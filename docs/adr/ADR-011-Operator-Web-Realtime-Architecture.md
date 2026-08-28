# ADR-011: Operator Web / Realtime Architecture

**Date:** 2026-08-27
**Status:** Accepted
**Deciders:** Chief Systems Architect

## 1. Context

TACTICAL CORE has an established durable event and projection architecture: canonical events, durable event persistence and delivery, reconstruction, entity/relation projections, production source configuration, and a long-lived production runtime (`backend/main.py`).

The current production runtime is not an operator-facing web application. Architecture discovery against baseline `f53435ec23ce1a297e12825add963f3e1a253a68` established:

- No existing Flask application.
- No Flask-SocketIO server.
- No Socket.IO server.
- No operator HTTP server.
- No operator frontend.
- No application factory.

Therefore the operator web architecture must not assume Flask or Flask-SocketIO as existing infrastructure. This ADR establishes the architecture required before implementation of WO-037. This ADR is an architecture decision only; it does not authorize WO-037 implementation by itself.

## 2. Problem

TACTICAL CORE requires an operator-facing consumption boundary through which operators can inspect:

- durable canonical events;
- projected entities;
- projected relations;
- authoritative operational health;
- realtime event notifications.

The operator layer must not become a dependency of source ingestion, EventPipeline, durable event persistence, DurableDeliveryDispatcher, reconstruction, projection writes, or source adapters. Operator availability must be architecturally independent from durable-core availability.

## 3. Decision Drivers

The architecture shall prioritize:

1. hard isolation from the durable core;
2. one authoritative source of truth;
3. read-only operator access;
4. offline / air-gapped operation;
5. deterministic API behavior;
6. testability;
7. minimal justified framework footprint;
8. explicit runtime topology;
9. no modification of durable event semantics;
10. no undocumented architectural assumptions.

## 4. Options Considered

### Option A — FastAPI Operator Service, Separate Process (SELECTED)

A dedicated FastAPI application shall provide the operator HTTP and realtime consumption boundary. The service shall run independently from `backend/main.py`. Advantages: typed HTTP API; explicit request validation; native asynchronous architecture; suitable realtime transport; testable application boundary; independent lifecycle; suitable for offline deployment. The architectural footprint of a new web subsystem is explicitly accepted because the operator product is a new capability and process isolation is required.

### Option B — Flask + Flask-SocketIO (REJECTED)

No Flask/Flask-SocketIO application architecture exists in the baseline. Introducing it would add an unnecessary second web framework and would rely on infrastructure that is not present.

### Option C — Python standard-library HTTP server (REJECTED)

Although dependency-light, it is not an appropriate foundation for the required typed API, validation, realtime transport, testing, and future operator expansion.

### Option D — Operator HTTP inside `backend/main.py` (REJECTED)

`backend/main.py` is the durable-core runtime lifecycle. Embedding the operator server into this process would couple operator availability and lifecycle to the durable core, violating the required isolation boundary.

## 5. Architectural Decision

The selected architecture is a **FastAPI-based Operator Service running as a separate process**.

```
Sources -> EventPipeline -> Durable Event Store
                                |
                                +----> Durable Delivery
                                |
                                +----> Projection
                                           |
                                           +----> EntityRepository
                                           +----> RelationRepository
                                           +----> Projection Checkpoint
                                                    |
                                                    | READ ONLY
                                                    v
                                         +----------------------+
                                         |   OPERATOR SERVICE   |
                                         |   FastAPI / ASGI     |
                                         |   REST API           |
                                         |   SSE                |
                                         |   Offline UI         |
                                         +----------------------+
```

There is no reverse dependency from the Operator Service into the durable processing path.

## 6. Process Isolation

The Operator Service shall have an independent lifecycle. Mandatory guarantees:

1. Operator Service startup failure must not prevent durable-core startup.
2. Operator Service shutdown must not stop ingestion.
3. Operator Service shutdown must not stop durable delivery.
4. HTTP failures must not roll back durable persistence.
5. SSE failures must not affect durable delivery.
6. Operator Service may be restarted independently.
7. Operator Service may be unavailable while the durable core continues operating.

A dedicated application factory and ASGI runtime entrypoint are part of the future WO-037 implementation boundary.

## 7. API Boundary

The operator API shall use `/api/v1/operator/*`. MVP endpoints:

```
GET /api/v1/operator/events
GET /api/v1/operator/events/{event_id}
GET /api/v1/operator/entities
GET /api/v1/operator/entities/{entity_id}
GET /api/v1/operator/entities/{entity_id}/relations
GET /api/v1/operator/health
```

The API is read-only. It shall not expose mutation operations for canonical events, durable events, entities, relations, source configuration, delivery state, reconstruction, or C2/tasking. Unsupported mutation methods shall be rejected rather than silently accepted.

## 8. Authoritative Data Sources

The Operator Service shall consume existing authoritative repositories and stores.

| Capability | Authoritative source |
| --- | --- |
| Event feed/detail | EventStoreRepository / durable event store |
| Entity state | EntityRepository |
| Relation state | RelationRepository |
| Delivery state | Existing durable delivery/outbox/dead-letter state |
| Projection progress | Existing projection checkpoint |
| Source state | Existing production source configuration/registration |

No second source-of-truth database, operator-specific event store, entity store, or relation store is permitted.

## 9. Repository Query Boundary

Operator requirements may require additional repository methods. Such methods shall be read-only, additive, deterministic, backward-compatible, and free of persistence side effects. They must not modify database schema, event persistence semantics, delivery semantics, projection semantics, or reconstruction semantics.

## 10. Pagination

Durable event queries shall use deterministic keyset/cursor pagination rather than unrestricted offset pagination. The exact ordering identity and cursor implementation must be validated against the live EventStoreRepository during WO-037 implementation. The operator layer must not introduce a new event ordering model.

## 11. Filtering

The MVP operator event feed may support source, event type, severity, UTC time range, page size, and cursor. All timestamps exposed through the operator API shall use ISO-8601 UTC representation.

## 12. Realtime Transport

The selected MVP realtime transport is **Server-Sent Events (SSE)**. SSE is selected because the operator consumption requirement is primarily server-to-client notification. Socket.IO is not introduced. Realtime publication is explicitly best effort.

Guarantees:

- durable persistence does not depend on SSE;
- SSE failure cannot fail ingestion;
- SSE failure cannot trigger durable retry;
- SSE failure cannot trigger dead-letter behavior;
- SSE failure cannot modify projection state;
- SSE publication occurs only after relevant durable state is committed/visible;
- REST remains the authoritative fallback;
- reconnect behavior is deterministic.

SSE is not a replacement for DurableDeliveryDispatcher.

## 13. Offline Operator UI

The Operator Service shall provide a local operator web interface. The UI shall use only local HTML/CSS/JavaScript, contain no CDN dependencies, no external runtime JavaScript dependencies, no external fonts, no telemetry dependency, operate on an air-gapped network, and remain usable when SSE is unavailable through REST polling. The MVP presentation shall be structured/tabular/card based. Full GIS and tactical symbol rendering are deferred.

## 14. Health Semantics

The health endpoint shall expose only metrics for which an authoritative source exists. Possible MVP metrics: registered sources; enabled source state; outbox backlog/depth; dead-letter count; projection checkpoint/progress. A source `last_ingestion_timestamp` shall not be fabricated. If that information is not authoritatively persisted, the API shall report it as unavailable/not tracked. No new heartbeat subsystem shall be created solely for the MVP health endpoint.

## 15. Security Boundary

The operator layer is read-only by architecture. The implementation shall validate all query parameters, bound page sizes, prevent unbounded resource consumption, reject unsupported mutation methods, never expose credentials, and preserve existing `credentials_ref` semantics. Optional local bearer/header authorization may be implemented. Full RBAC is outside the MVP. Authentication must never become a dependency of durable ingestion.

## 16. Failure Modes

- Operator Service unavailable: durable core continues operating normally.
- Operator database/read failure: operator API returns structured service-unavailable behavior; failure must not modify durable-core state.
- SSE disconnect: client falls back to REST polling.
- Malformed event during operator serialization: the operator read layer may log the failure, skip the affected record, and expose a deterministic skipped-record count. This applies only to operator reads and must never be introduced into reconstruction, durable event processing, or durable delivery.

## 17. Protected Architecture

WO-037 shall not modify the semantics of CanonicalEvent, DurableCanonicalEvent, EventPipeline, DurableDeliveryDispatcher, outbox, retry, dead-letter, ReconstructionService, projection writes, checkpoint semantics, source adapters, source configuration, durable schemas, migrations, or entity/relation source-of-truth semantics. Only additive read/query methods are permitted where necessary for operator consumption.

## 18. MVP Boundary

Included: operator REST API; event feed; event inspection; entity inspection; relation inspection; health view; filtering; cursor pagination; SSE realtime notification; REST fallback; offline local UI.

Deferred: MIL-STD-2525 / APP-6 rendering; interactive GIS; map tile infrastructure; timeline replay; operator annotations; event acknowledgement; full RBAC; autonomous decision support; C2 tasking; bidirectional mission control.

## 19. Implementation Boundary for WO-037

WO-037 may introduce: FastAPI application factory; ASGI runtime entrypoint; operator router; operator query/service layer; additive repository query methods; SSE stream manager/notifier; local operator HTML/CSS/JavaScript assets; operator-specific tests; required web runtime dependencies. The exact file structure must be derived from the live repository. No Flask-derived file structure shall be assumed.

## 20. Testing Requirements

WO-037 shall include deterministic tests covering: application startup; all operator REST endpoints; request validation; pagination; filtering; event inspection; entity reads; relation reads; health semantics; read-only method enforcement; SSE publication; SSE disconnect/fallback; operator failure isolation; offline asset availability; regression against the existing test suite. The tests must demonstrate that operator-service failure cannot interrupt durable-core processing.

## 21. Consequences

Positive: establishes an explicit operator product boundary; preserves durable-core isolation; avoids unsupported Flask assumptions; provides a typed/testable web architecture; supports offline and air-gapped operation; keeps existing repositories as authoritative sources; provides realtime consumption without coupling to durable delivery.

Negative: introduces a new web application subsystem; introduces an independent runtime process; requires explicit web runtime dependencies; requires an ASGI entrypoint; requires additional operator query methods; adds frontend and realtime test surfaces.

Accepted trade-off: the additional process and web subsystem are intentionally accepted because operator availability must never become a dependency of the durable tactical core.

## 22. Non-Goals

This ADR does not authorize Flask, Flask-SocketIO, Socket.IO, modification of durable event semantics, modification of durable delivery, modification of reconstruction, a second database, C2 write-back, GIS infrastructure in MVP, full RBAC, AI tactical decision support, external secret-management infrastructure, or deployment orchestration unless separately authorized.

## 23. Relationship to WO-037

WO-037 shall be finalized against ADR-011 before implementation authorization. WO-037 shall define exact API contracts, response schemas, UI behavior, repository query contracts, SSE event schema, offline asset structure, acceptance criteria, and test cases. If WO-037 conflicts with ADR-011, implementation shall stop until the conflict is resolved.

## 24. Status

Accepted — architecture established. ADR-011 authorizes preparation of the corrected WO-037. ADR-011 does not authorize implementation of WO-037.
