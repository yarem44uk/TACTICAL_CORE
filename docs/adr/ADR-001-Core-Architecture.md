# ADR-001: Core Architecture

**Date:** Initial Design  
**Status:** Accepted  
**Deciders:** Architecture Team

---

## Context

Tactical Core is a modular tactical information management platform that must support multiple input sources (Radio, Signal, Camera, REST API, plugins) and multiple output destinations (Dashboard, AI, Plugins, external systems).

Direct coupling between modules would create a complex web of dependencies that would be difficult to maintain and extend.

---

## Decision

Implement Event-Driven Architecture where:
1. Every module publishes events to the Event Engine
2. The Event Engine processes events through a configurable pipeline
3. The Event Engine distributes events to interested subscribers
4. No direct module-to-module communication is allowed

---

## Motivation

- **Loose Coupling:** Modules only depend on the Event Engine, not on each other
- **Extensibility:** New modules can be added without modifying existing code
- **Testability:** Events can be mocked and tested independently
- **Parallel Development:** Teams can work on different modules simultaneously
- **Clear Data Flow:** All data flows through a single point, making tracing easy

---

## Alternatives Considered

1. **Direct Module Communication:** Rejected - Creates tight coupling, N×M dependencies
2. **Message Queue Only:** Rejected - Adds infrastructure complexity without benefit
3. **Event Bus without Pipeline:** Rejected - No processing logic organization

---

## Trade-offs

| Positive | Negative |
|----------|----------|
| Loose coupling | Additional latency |
| Easy testing | Complexity in tracing |
| Extensibility | Eventual consistency |
| Parallel development | Potential message loss |

---

## Future Consequences

- **Positive:** New modules (Radio, Signal, AI) can be added by publishing events
- **Positive:** Dashboard can subscribe to specific event types
- **Neutral:** Requires monitoring for event processing latency
- **Need:** Distributed event bus for multi-instance deployment

---

## Implementation Notes

- EventEngine is the single entry point for all events
- Pipeline provides configurable processing stages
- EventBus handles subscription-based distribution
- All events are stored in history for replay capability
