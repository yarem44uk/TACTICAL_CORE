# TACTICAL CORE

## WO-013 — Event Source Integration Layer

**Status:** APPROVED FOR IMPLEMENTATION

---

## 1. Purpose

WO-013 introduces an External Source Integration Framework that enables TACTICAL CORE to ingest events from heterogeneous external systems through a standardized adapter model.

The layer provides:
- Protocol-agnostic event ingestion
- Standardized adapter lifecycle management
- Canonical event transformation from raw source data
- Adapter runtime execution and supervision
- Integration with WO-012 Event Processing Pipeline

---

## 2. Relationship with WO-012

```
WO-013 (Event Ingestion Layer)          WO-012 (Event Processing Layer)
─────────────────────────               ─────────────────────────────

Raw Data        → Source Adapter        │
           → Event Factory              │
           → Canonical Event ────────────┼──→ Pipeline
                                        │
                                        │         ↓
                                        │    Filter → Dispatcher
                                        │         ↓
                                        │    EventBus → Repository
```

**WO-013 = Ingestion.** Responsible for connecting to external sources, reading raw data, and producing canonical events.

**WO-012 = Processing.** Responsible for filtering, dispatching, persisting, and broadcasting events that have already been normalized.

Boundary: WO-013 delivers a canonical `Event` to the WO-012 `IEventPipeline`. No back-flow.

---

## 3. Architecture Diagram

```
┌─────────────────────────────────────────────────┐
│               EXTERNAL SOURCES                   │
│  Telegram │ REST API │ MQTT │ Signal │ Radio     │
└────┬────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────┐
│            SOURCE ADAPTER LAYER                  │
│  ┌──────────────┐  ┌──────────────┐             │
│  │ Adapter #1   │  │ Adapter #2   │  ...        │
│  │ (IEventSource│  │ (IEventSource│             │
│  │  Adapter)    │  │  Adapter)    │             │
│  └──────┬───────┘  └──────┬───────┘             │
└─────────┼──────────────────┼─────────────────────┘
          │                  │
          ▼                  ▼
┌─────────────────────────────────────────────────┐
│          Source Registry (catalog)               │
│  register / get / list / remove / start_all /    │
│  stop_all / count                                │
└─────────────────────┬───────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────┐
│      AdapterSupervisor (runtime orchestration)   │
│  one AdapterRuntime per adapter                  │
│  poll loop / restart / health aggregation        │
└─────────────────────┬───────────────────────────┘
                      │ canonical Event (WO-012)
                      ▼
┌─────────────────────────────────────────────────┐
│          WO-012 Event Pipeline                   │
│  (Filter → Dispatcher → EventBus → Repository)   │
└─────────────────────────────────────────────────┘
```

---

## 4. Architectural Principles

### 4.1 Core Isolation

WO-013 components must not depend on WO-012 implementation details. Dependency direction is strictly outward:

```
WO-013 Adapter → IEventPipeline (interface only)
```

WO-013 knows nothing about Filters, Dispatcher, Repository, or EventBus internals.

### 4.2 Dependency Direction

```
Source Adapter
      ↓
Adapter Runtime
      ↓
Event Factory
      ↓
Event Pipeline
      ↓
Event Dispatcher / Service / Repository / Bus
```

Core (event/, pipeline, dispatcher, service, repository, bus) never imports concrete source adapters. The runtime depends only on interfaces: `IEventSourceAdapter`, `IEventFactory`, `IEventPipeline`.

### 4.3 Plugin Model

Each external source is implemented as an independent adapter. Adapters are:
- Registered via the Source Registry (registration catalog)
- Executed by the Adapter Supervisor (one runtime thread per adapter)
- Isolated from each other
- Added or replaced without core modification

A new adapter is added without changing core by implementing `IEventSourceAdapter` and registering it. Runtime and supervisor operate through interfaces only.

### 4.4 Lifecycle Management

Each adapter exposes `start()`, `stop()`, `health()`, `read_events()`, `source_name()`.

The `AdapterRuntime` owns exactly one adapter and drives it through an explicit lifecycle state machine (see section 6). The `AdapterSupervisor` orchestrates N runtimes.

### 4.5 Failure Isolation

A single adapter failure must not propagate:
- Exceptions from one adapter are caught at the runtime boundary
- A malformed event is dropped; processing continues
- A single bad event does not restart the adapter
- Runtime-level failures drive bounded auto-restart
- Other adapters continue operating independently

### 4.6 Backpressure (future WO)

Backpressure is NOT implemented in WO-013-001/002/003. When WO-012 Pipeline cannot accept events, the only current behaviour is per-event drop with logging. Rate limiting, buffers, and persistent queues are a separate future Work Order.

---

## 5. Interfaces

### 5.1 IEventSourceAdapter (merged contract)

```python
class IEventSourceAdapter(ABC):
    def start(self) -> None: ...
    def stop(self) -> None: ...
    def health(self) -> bool: ...
    def read_events(self) -> list[dict[str, Any]]: ...
    def source_name(self) -> str: ...
```

- `health()` returns a plain `bool` (running/operational or not).
- `read_events()` returns a list of raw event dictionaries (protocol-specific), which the EventFactory normalizes into canonical Events.

### 5.2 IEventFactory (merged contract)

```python
class IEventFactory(ABC):
    def create_event(
        self,
        raw_data: dict[str, Any],
        source_name: str,
        event_type: EventType | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Event: ...
```

Returns a real WO-012 `Event` instance (frozen dataclass), not a dictionary.

### 5.3 Canonical Event (shared with WO-012)

The canonical event is the WO-012 `Event` model (`app.event.event.Event`). There is no separate `CanonicalEvent` class and no `RawEvent` class. Raw source data is a plain `dict`; it becomes a canonical `Event` via `EventFactory.create_event()`.

---

## 6. Adapter Runtime Lifecycle

The `AdapterRuntime` (one adapter) uses an explicit state machine.

### 6.1 States

```
STOPPED
STARTING
RUNNING
DEGRADED
STOPPING
FAILED
```

There is no UNKNOWN state. Initial state is STOPPED.

### 6.2 Transitions

```
STOPPED → STARTING → RUNNING
RUNNING ⇄ DEGRADED
RUNNING/DEGRADED → STOPPING → STOPPED
RUNNING/DEGRADED → FAILED
FAILED → STARTING   (manual recovery only)
```

Forbidden:
- `FAILED → RUNNING` (must pass through STARTING)
- `STOPPED → RUNNING` (must pass through STARTING)

### 6.3 Semantics

- `start()`: STOPPED → STARTING → RUNNING. Idempotent — a no-op while STARTING, RUNNING, or DEGRADED. Refuses to start while STOPPING. While FAILED, `start()` raises; manual recovery uses `restart()`.
- `stop()`: RUNNING/DEGRADED → STOPPING → STOPPED. Idempotent. Joins the runtime thread so no background thread remains. Legal from STARTING/FAILED/STOPPING too (via the transition table, never by force assignment).
- `restart()`: manual, allowed only from FAILED. Resets the restart budget.
- All transitions are thread-safe (guarded by RLock) and go through the authoritative transition table — the state machine is never bypassed by forced assignment.

### 6.4 Read Failure vs Runtime Failure (corrected)

The runtime strictly distinguishes two failure classes:

**Recoverable read failure** — `adapter.read_events()` raises:

```
RUNNING → DEGRADED
log error
retry polling in the SAME runtime thread
does NOT consume the restart budget
does NOT force FAILED
on a later successful read → DEGRADED → RUNNING
```

A read failure never terminates the runtime and never permanently exhausts the restart budget.

**Runtime-level failure** — `adapter.start()` raises, or an unexpected exception escapes the polling loop:

```
RUNNING/DEGRADED → FAILED
consume ONE restart-budget unit
if budget remains → FAILED → STARTING → create a NEW runtime thread
if budget exhausted → remain FAILED (manual recovery only)
```

---

## 7. Data Flow

```
adapter.read_events()
        ↓
raw dict
        ↓
IEventFactory.create_event(...)
        ↓
canonical Event
        ↓
IEventPipeline.process(event)
```

Per-event error isolation:

```python
try:
    event = factory.create_event(...)
    pipeline.process(event)
except factory/pipeline error:
    log
    drop event
    continue
```

A single bad event never stops the runtime.

---

## 8. Source Registry (merged contract)

### Purpose

`SourceRegistry` is the **registration catalog** for source adapters. It does NOT run polling loops.

### Responsibilities

```
register(adapter)
unregister(name)
get(name)
list_sources()
start_all()
stop_all()
count()
```

- `start_all()`/`stop_all()` drive adapter lifecycle start/stop with failure isolation (one adapter failure does not stop others).
- The registry does NOT implement `collect_events()` and does NOT perform event aggregation.

### Boundary with AdapterSupervisor

```
SourceRegistry.start_all()  = adapter lifecycle start (catalog)
AdapterSupervisor           = runtime/thread/poll-loop/restart orchestration
```

The supervisor may USE the registry as a source of adapters but does not replace it. No double-start: the registry starts adapters, the supervisor starts runtime threads.

---

## 9. Adapter Runtime & Supervisor

### 9.1 AdapterRuntime

Owns exactly ONE adapter. Collaborators injected:
- `IEventSourceAdapter`
- `IEventFactory`
- `IEventPipeline`

One runtime = one dedicated thread (no asyncio, no shared worker pool, no global executor). Provides a structured health snapshot:

```python
{
    "name": ...,
    "state": ...,
    "healthy": ...,
    "restarts": ...,
    "restart_budget_remaining": ...,
    "last_error": ...,
    "last_success_at": ...,
    "events_processed": ...,
}
```

`IEventSourceAdapter.health() -> bool` is unchanged.

### 9.2 AdapterSupervisor

Owns N runtimes. Responsibilities:
```
create/attach runtime
start_all
stop_all
restart(name)
get_health()  (aggregate)
shutdown
```

### 9.3 Restart Policy (bounded)

- Finite budget (`max_restarts`, default 3), finite `restart_delay`.
- `max_restarts` = maximum number of ACTUAL automatic runtime restart attempts (each creating a new thread).
- With `max_restarts = N`: N restarts occur before the (N+1)th runtime-level failure leaves the runtime FAILED.
- No `while True: restart()`.
- Counter increases ONLY on runtime-level failure (a real restart is required). It is NEVER consumed by recoverable `read_events()` failures.
- Resets after a sustained healthy RUNNING period, and on manual `restart()`.
- When budget is exhausted → FAILED. No automatic infinite restart.
- Recovery from FAILED is manual: `supervisor.restart(name)`.

Important distinction: a bad event is dropped (continue), NOT a reason to restart the adapter; a `read_events()` error degrades (DEGRADED) and retries in the same thread. Auto-restart (new thread) applies ONLY to runtime-level failures (start failure / poll-loop crash).

### 9.4 Threading Model

- **One dedicated thread per `AdapterRuntime`.** One runtime == one active polling thread. No asyncio, no shared worker pool, no global executor in WO-013-003.
- The `AdapterSupervisor` owns multiple runtimes, each with its own thread.
- The `SourceRegistry` is a registration catalog only — it does NOT spawn polling threads.
- A runtime-level restart creates a **brand-new `threading.Thread` object**; it is not a same-thread `continue` or a mere counter increment.
- During a restart the old thread terminates before the new thread begins normal operation — the old thread never calls `adapter.stop()` after handing off to a restarted thread, so there is no old-thread-cleanup / new-thread-startup race on the adapter.
- `stop()` performs a `join(timeout=...)` and guarantees no active runtime thread remains after a successful stop within the timeout.
- There is never more than one active polling thread for the same adapter. Repeated `start()` calls while active are no-ops and do not create extra threads.
- Sibling runtimes are isolated: one adapter's thread/failure does not affect another's.

---

## 10. WO-013-001 Scope (implemented)

### INCLUDED

- `IEventSourceAdapter` interface
- `BaseEventSourceAdapter`
- `SourceRegistry`
- `IEventFactory` + `EventFactory`
- Unit tests

### EXCLUDED (future Work Orders)

- Signal adapter
- MQTT adapter
- Radio/ATAK adapter
- MPU5 integration
- Any protocol-specific adapter code
- Configuration management for sources

---

## 11. WO-013-002 Scope (implemented)

- `EventFactory` integrated with WO-012 canonical `Event` model
- `IEventFactory.create_event(...) -> Event`
- Integration tests

---

## 12. WO-013-003 Scope (implemented)

- `AdapterRuntime` (one adapter, one thread, lifecycle state machine)
- `AdapterSupervisor` (N runtimes orchestration)
- Bounded restart policy
- Health snapshots / aggregate health
- Documentation aligned to merged implementation

### NOT implemented in WO-013-003

- Backpressure (queues, rate limiters, buffers)
- Any concrete protocol adapter
- Changes to WO-012 core

---

## 13. Acceptance Criteria

All criteria from Architecture Constitution apply:

| ID | Criterion |
|----|-----------|
| CV1 | Identity-first resolution — all entities use unique identifiers |
| CV2 | Non-destructive operations — no deletion of active adapters at runtime |
| CV3 | Explicit state management — STOPPED initial state, no UNKNOWN, no implicit PENDING |
| CV4 | Confidence validation — health/confidence in valid range |
| CV5 | Dependency isolation — adapters depend only on shared interfaces |
| CV6 | Backward compatibility — canonical Event schema preserved across versions |
| CV7 | Audit trail — all adapter state changes logged with timestamps |

---

## 14. Git Workflow

**WO-013-001 Branch:** `WO-013-001-source-adapter-framework`
**WO-013-002 Branch:** `WO-013-002-event-factory-integration`
**WO-013-003 Branch:** `WO-013-003-adapter-runtime-supervisor`

**Flow:**

```
Implementation
  ↓
Tests
  ↓
Independent Audit
  ↓
Integration Review
  ↓
Merge to main
```

**Constraints:**
- Work only on the feature branch
- No direct changes to main
- No force push
- No history rewrite
- Protected files unchanged

---

## 15. File Structure

```
backend/app/event_sources/
  __init__.py
  interfaces/
    __init__.py
    i_event_source_adapter.py
    i_event_factory.py
  adapters/
    __init__.py
    base_adapter.py
  registry/
    __init__.py
    source_registry.py
  factory/
    __init__.py
    event_factory.py
  runtime/
    __init__.py
    adapter_runtime.py
    adapter_supervisor.py
    lifecycle.py
    restart_policy.py

backend/tests/
  test_event_sources.py
  test_event_factory_integration.py
  test_adapter_runtime.py
  test_adapter_supervisor.py
```

---

## 16. Dependencies

WO-013 depends on:
- WO-012 Event Pipeline interface (`IEventPipeline`)
- WO-012 canonical `Event` model
- No external library dependencies for framework layer

WO-012 does NOT depend on WO-013.

---

## 17. Document Version

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-08-07 | Chief Systems Architect | Initial approved architecture |
| 1.1 | 2026-08-10 | Chief Systems Architect | Aligned to merged implementation (WO-013-001/002/003); removed RawEvent/dict-health/collect_events dual contract; documented Runtime & Supervisor |
| 1.2 | 2026-08-10 | Chief Systems Architect | Corrected per independent audit (B2/B3/B4/M1): lifecycle state machine authoritative (no forced assignment); read_events failure -> DEGRADED without consuming restart budget or forcing FAILED; real new-thread runtime auto-restart within bounded budget; start() while DEGRADED is a no-op; documented Threading Model |

---

**End of Document**
