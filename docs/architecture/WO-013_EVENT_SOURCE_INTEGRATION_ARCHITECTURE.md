# TACTICAL CORE
# WO-013 — Event Source Integration Layer

**Status:** APPROVED FOR IMPLEMENTATION
**Version:** 1.0
**Date:** 2026-08-07
**Author:** Chief Systems Architect
**Auditor:** Independent Architecture Review

---

## 1. Purpose

External Source Integration Framework.

WO-013 provides a unified ingestion layer that connects external event sources (Telegram, Signal, MQTT, Radio, ATAK, etc.) to the internal Event Processing Pipeline (WO-012).

---

## 2. Relationship with WO-012

| Layer | WO | Responsibility |
|-------|----|----------------|
| Event Processing | WO-012 | Internal event pipeline, filtering, dispatch, persistence |
| Event Ingestion | WO-013 | External source adapters, canonicalization, ingestion |

**Direction:** WO-013 → WO-012

WO-013 produces canonical events that feed into the WO-012 Event Pipeline.
WO-012 has no knowledge of external sources.
WO-013 depends on WO-012 interfaces only.

---

## 3. Architecture Diagram

```
┌─────────────────────────────────────────────────┐
│                   External Sources               │
│  (Telegram, Signal, MQTT, Radio, ATAK, etc.)    │
└──────────────────────┬──────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────┐
│              Source Adapter Layer                 │
│                                                  │
│  ┌────────────┐  ┌────────────┐  ┌───────────┐  │
│  │ Telegram   │  │ Signal     │  │ MQTT      │  │
│  │ Adapter    │  │ Adapter    │  │ Adapter   │  │
│  └─────┬──────┘  └─────┬──────┘  └─────┬─────┘  │
│        │               │               │        │
│        └───────┬───────┘───────┬───────┘        │
│                │               │                │
│        ┌───────▼───────────────▼───────┐        │
│        │    Source Registry            │        │
│        │  (discovery, lifecycle)       │        │
│        └───────┬───────────────────────┘        │
└────────────────┼───────────────────────────────┘
                 │ Raw Events
                 ▼
┌─────────────────────────────────────────────────┐
│               Event Factory                      │
│                                                  │
│  Raw Data  →  Timestamp Normalization            │
│                Source Identification             │
│                Metadata Extraction               │
│                Protocol Fields → Metadata        │
│                                                  │
│  Output: Canonical Event                         │
└────────────────┬───────────────────────────────┘
                 │ Canonical Events
                 ▼
┌─────────────────────────────────────────────────┐
│          WO-012 Event Pipeline                   │
│                                                  │
│  Before Middleware → Filters → Dispatcher        │
│  → After Middleware → Repository → EventBus      │
└─────────────────────────────────────────────────┘
```

---

## 4. Architectural Principles

### 4.1 Core Isolation

The WO-013 ingestion layer is isolated from the WO-012 processing layer.
WO-012 must not import from WO-013 packages.
WO-013 imports only WO-012 interfaces.

### 4.2 Dependency Direction

```
WO-013 (Source Adapters)
    ↓ depends on
WO-012 (Event Pipeline, EventBus, Repository interfaces)
    ↓ depends on
Core (Event models, types)
```

No reverse dependencies. No circular imports.

### 4.3 Plugin Model

Each source adapter is independently:
- Discoverable via the Source Registry
- Lifecycle-managed (start/stop/health)
- Configurable via configuration or constructor
- Replaceable without affecting other adapters

### 4.4 Lifecycle Management

Source adapters expose a uniform lifecycle:
- `start()` — begin ingestion
- `stop()` — graceful shutdown with drain
- `health()` — operational status check

The Source Registry coordinates lifecycle for all registered adapters.

### 4.5 Failure Isolation

A failure in one adapter MUST NOT:
- Stop other adapters
- Crash the ingestion layer
- Block the event pipeline

Each adapter runs in isolation. Failures are logged and reported via health checks.

### 4.6 Backpressure

When the downstream pipeline is saturated:
- Adapters MUST support backpressure signals
- Adapters MAY throttle ingestion rate
- Adapters MUST NOT silently drop events
- Dropped events MUST be logged with reason

---

## 5. Interfaces

### 5.1 IEventSourceAdapter

```python
from abc import ABC, abstractmethod
from typing import AsyncIterator, List, Dict, Any, Optional
from datetime import datetime

class IEventSourceAdapter(ABC):
    """Interface for external event source adapters."""

    @abstractmethod
    async def start(self) -> None:
        """Begin event ingestion from the source."""
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Gracefully stop event ingestion."""
        ...

    @abstractmethod
    async def health(self) -> Dict[str, Any]:
        """Return operational status and metrics."""
        ...

    @abstractmethod
    async def read_events(self) -> AsyncIterator[Dict[str, Any]]:
        """Yield raw events from the source."""
        ...

    @abstractmethod
    def source_name(self) -> str:
        """Return unique source identifier."""
        ...
```

---

## 6. Source Registry

The Source Registry is responsible for:

1. **Registration** — adapters register themselves at startup
2. **Discovery** — registry provides list of active adapters
3. **Lifecycle coordination** — start/stop all adapters uniformly
4. **Health monitoring** — aggregate health from all adapters
5. **Configuration** — per-adapter configuration management

The Registry does NOT:
- Contain protocol-specific logic
- Transform events
- Store events

---

## 7. Event Factory

The Event Factory converts raw source data to Canonical Events.

### 7.1 Input

Raw dictionary from any source adapter. May contain:
- Protocol-specific fields
- Non-standard timestamps
- Missing metadata
- Nested structures

### 7.2 Processing Rules

1. **Timestamp normalization** — all timestamps converted to UTC ISO 8601
2. **Source identification** — adapter source_name becomes event.source
3. **Metadata extraction** — protocol-specific fields moved to metadata dict
4. **Required fields** — event_id, timestamp, source, type populated
5. **No protocol-specific fields in core** — raw fields stripped or moved to metadata

### 7.3 Output

Canonical Event matching WO-012 Event model:

```python
{
    "event_id": str,          # unique identifier
    "timestamp": datetime,    # UTC normalized
    "source": str,            # source_name from adapter
    "type": str,              # event type classification
    "metadata": dict,         # source-specific extra fields
    "data": dict,             # normalized event payload
    "correlation_id": str,    # if applicable
}
```

---

## 8. WO-013-001 Scope

### 8.1 INCLUDED (WO-013-001)

- `IEventSourceAdapter` interface
- `SourceRegistry` implementation
- Lifecycle management (start/stop/health)
- Event Factory contract and base implementation
- Canonical Event model alignment with WO-012
- Unit tests for all components
- Integration tests with WO-012 pipeline interfaces

### 8.2 EXCLUDED (future Work Orders)

- Telegram adapter (WO-013-002)
- Signal adapter (WO-013-003)
- MQTT adapter (WO-013-004)
- Radio adapter (WO-013-005)
- ATAK adapter (WO-013-006)
- MPU5 adapter (WO-013-007)

---

## 9. Acceptance Criteria

### CV1: Identity-First Resolution
All events carry source identity. No anonymous events enter the pipeline.

### CV2: Non-Destructive Operations
Adapter failures do not destroy pipeline state. Graceful degradation only.

### CV3: UNKNOWN Initial Status
New adapters start in UNKNOWN state until first health check succeeds.

### CV4: Confidence Validation
Source reliability tracked per-adapter. Confidence scores [0.0, 1.0].

### CV5: Dependency Isolation
WO-013 imports only WO-012 interfaces. No core modifications required.

### CV6: No Protocol Leakage
Protocol-specific fields never appear in Canonical Event core.

### CV7: Thread Safety
Source Registry and Event Factory are thread-safe. Concurrent adapter operations supported.

---

## 10. Git Workflow

### Branch
```
WO-013-001-source-adapter-framework
```

### Flow
```
Implementation
    ↓
Unit Tests
    ↓
Integration Tests with WO-012
    ↓
Independent Architecture Review
    ↓
Chief Systems Architect Approval
    ↓
Merge into main
    ↓
Tag: WO-013-001
```

### Protected Files
WO-013-001 MUST NOT modify:
- `backend/app/event_pipeline/` (WO-012-007)
- `backend/app/event_filter/` (WO-012-006)
- `backend/app/event_bus/` (WO-012-003)
- `backend/app/event_repository/` (WO-012-002)
- `backend/app/event_service/` (WO-012-005)
- `backend/app/event_dispatcher/` (WO-012-004)

---

## 11. Directory Structure (WO-013-001)

```
backend/app/event_source/
    __init__.py
    interfaces/
        __init__.py
        i_event_source_adapter.py
    source_registry.py
    event_factory.py
backend/tests/test_source_registry.py
backend/tests/test_event_factory.py
```

---

## 12. Version History

| Version | Date | Change |
|---------|------|--------|
| 1.0 | 2026-08-07 | Initial architecture document |

---

*This document is the Source of Truth for WO-013 implementation.*
*All implementation decisions must reference this document.*
*Changes require Chief Systems Architect approval.*
