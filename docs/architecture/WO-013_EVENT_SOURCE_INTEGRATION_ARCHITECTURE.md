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

Boundary: WO-013 delivers a `CanonicalEvent` to the WO-012 `IEventPipeline`. No back-flow.

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
│                                                  │
│  ┌──────────────┐  ┌──────────────┐             │
│  │ Adapter #1   │  │ Adapter #2   │  ...        │
│  │ (IEventSource│  │ (IEventSource│             │
│  │  Adapter)    │  │  Adapter)    │             │
│  └──────┬───────┘  └──────┬───────┘             │
│         │                 │                      │
│         ▼                 ▼                      │
│  ┌──────────────────────────────────┐            │
│  │       Source Registry            │            │
│  │  - Adapter discovery             │            │
│  │  - Lifecycle management          │            │
│  │  - Health monitoring             │            │
│  └────────────┬─────────────────────┘            │
└───────────────┼──────────────────────────────────┘
                │ RawEvent (source, raw_data, ts)
                ▼
┌─────────────────────────────────────────────────┐
│              EVENT FACTORY                       │
│                                                  │
│  RawEvent → CanonicalEvent                       │
│  - timestamp normalization                       │
│  - source identification                         │
│  - metadata enrichment                           │
│  - schema validation                             │
└───────────────┬──────────────────────────────────┘
                │ CanonicalEvent
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
Core Event Model (shared)
    ↑
WO-012 Pipeline
    ↑
WO-013 Adapters
```

All adapters depend on the shared Canonical Event model, never on each other.

### 4.3 Plugin Model

Each external source is implemented as an independent adapter. Adapters are:
- Discovered via the Source Registry
- Loaded on demand
- Isolated from each other
- Replaced without core modification

### 4.4 Lifecycle Management

Each adapter manages its own connection state:
- `start()` — initialize connection, begin reading
- `stop()` — graceful shutdown, flush pending data
- `health()` — connection status, last read timestamp

The Source Registry coordinates lifecycle across all adapters.

### 4.5 Failure Isolation

A single adapter failure must not propagate:
- Adapter exceptions are caught at the registry boundary
- Failed adapters are marked unhealthy, not restarted automatically
- Other adapters continue operating independently
- Canonical Event delivery is unaffected by adapter state

### 4.6 Backpressure

When WO-012 Pipeline cannot accept events:
- Adapters throttle their read rate
- Source Registry enforces per-adapter rate limits
- No unbounded buffers in the pipeline
- Events are dropped with audit logging, not queued indefinitely

---

## 5. Interfaces

### 5.1 IEventSourceAdapter

```python
class IEventSourceAdapter(Protocol):
    """
    Contract for external source adapters.
    
    Each adapter implements this interface to provide
    raw event data to the Event Factory.
    """
    
    def start(self) -> None:
        """
        Initialize the adapter connection and begin reading.
        Called by Source Registry during startup.
        Must complete within connection timeout.
        """
        ...
    
    def stop(self) -> None:
        """
        Gracefully shut down the adapter.
        Flush pending data, close connections.
        Called by Source Registry during shutdown.
        """
        ...
    
    def health(self) -> dict:
        """
        Return adapter health status.
        
        Returns:
            dict with keys:
            - status: "healthy" | "degraded" | "unhealthy"
            - last_read: datetime | None
            - connection_state: str
            - error_count: int
        """
        ...
    
    def read_events(self) -> list[RawEvent]:
        """
        Read available events from the source.
        Non-blocking — returns immediately with available data.
        Returns empty list if no events available.
        
        Returns:
            list of RawEvent objects
        """
        ...
    
    def source_name(self) -> str:
        """
        Return unique identifier for this source.
        Used for correlation and audit logging.
        
        Returns:
            str — source identifier (e.g., "telegram-channel-1", "mqtt-broker-a")
        """
        ...
```

### 5.2 RawEvent

```python
@dataclass
class RawEvent:
    """
    Raw event from an external source.
    Contains unprocessed data before canonical transformation.
    """
    source: str
    raw_data: dict
    received_at: datetime
```

### 5.3 CanonicalEvent (shared with WO-012)

```python
@dataclass
class CanonicalEvent:
    """
    Normalized event accepted by WO-012 Pipeline.
    All external sources produce this format.
    """
    event_id: str
    event_type: str
    source: str
    timestamp: datetime
    correlation_id: str
    metadata: dict
    payload: dict
```

---

## 6. Source Registry

### Purpose

Centralized management of all active source adapters.

### Responsibilities

1. **Adapter Discovery** — register new adapters by class or factory function
2. **Lifecycle Coordination** — start/stop all adapters in sequence
3. **Health Monitoring** — poll health() on all adapters, report status
4. **Event Aggregation** — collect events from all adapters, forward to Event Factory
5. **Rate Limiting** — enforce per-adapter throughput limits
6. **Failure Handling** — isolate failed adapters, log errors, continue operation

### Design

```python
class SourceRegistry:
    def register(adapter: IEventSourceAdapter) -> None: ...
    def unregister(source_name: str) -> None: ...
    def start_all() -> None: ...
    def stop_all() -> None: ...
    def get_health() -> dict: ...
    def collect_events() -> list[RawEvent]: ...
```

---

## 7. Event Factory

### Purpose

Transform RawEvent from adapters into CanonicalEvent for the WO-012 Pipeline.

### Transformation Rules

1. **Timestamp Normalization** — all timestamps converted to UTC ISO 8601
2. **Source Identification** — source field set from adapter source_name()
3. **Metadata Handling** — adapter-specific metadata preserved in metadata dict
4. **Payload Extraction** — protocol-specific fields extracted into payload dict
5. **No Protocol-Specific Fields** — canonical event contains no references to HTTP, MQTT, Signal, etc.

### Design

```python
class EventFactory:
    def create(raw: RawEvent) -> CanonicalEvent: ...
```

### Rules

- Event ID generation uses UUID4
- Correlation ID inherited from source or generated
- Schema validation against CanonicalEvent structure
- Invalid events logged and dropped, never passed to pipeline

---

## 8. WO-013-001 Scope

### INCLUDED (WO-013-001)

- `IEventSourceAdapter` interface definition
- `SourceRegistry` implementation
- `EventFactory` implementation
- `RawEvent` data model
- Adapter lifecycle management (start/stop/health)
- Unit tests for all components
- Integration test with WO-012 Pipeline interface

### EXCLUDED (future Work Orders)

- Signal adapter implementation
- MQTT adapter implementation
- Radio/ATAC adapter implementation
- MPU5 integration
- Any protocol-specific adapter code
- Configuration management for sources

WO-013-001 delivers the framework. Protocol adapters follow as separate Work Orders.

---

## 9. Acceptance Criteria

All criteria from Architecture Constitution apply:

| ID | Criterion |
|----|-----------|
| CV1 | Identity-first resolution — all entities use unique identifiers |
| CV2 | Non-destructive operations — no deletion of active adapters at runtime |
| CV3 | Explicit state management — UNKNOWN initial status, no implicit PENDING |
| CV4 | Confidence validation — health scores in range [0.0, 1.0] |
| CV5 | Dependency isolation — adapters depend only on shared interfaces |
| CV6 | Backward compatibility — CanonicalEvent schema preserved across versions |
| CV7 | Audit trail — all adapter state changes logged with timestamps |

---

## 10. Git Workflow

**Branch:** `WO-013-001-source-adapter-framework`

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
- Work only on branch `WO-013-001-source-adapter-framework`
- No direct changes to main
- No force push
- No history rewrite
- Protected files unchanged
- Commit message: `WO-013-001: Implement Source Adapter Framework`

---

## 11. File Structure

```
backend/app/event_source/
  __init__.py
  interfaces/
    __init__.py
    i_event_source_adapter.py
  models/
    __init__.py
    raw_event.py
  source_registry.py
  event_factory.py

backend/tests/
  test_source_registry.py
  test_event_factory.py
  test_event_source_adapter.py
```

---

## 12. Dependencies

WO-013 depends on:
- WO-012 Event Pipeline interface (`IEventPipeline`)
- Shared Canonical Event model (from WO-012)
- No external library dependencies for framework layer

WO-012 does NOT depend on WO-013.

---

## 13. Document Version

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-08-07 | Chief Systems Architect | Initial approved architecture |

---

**End of Document**
