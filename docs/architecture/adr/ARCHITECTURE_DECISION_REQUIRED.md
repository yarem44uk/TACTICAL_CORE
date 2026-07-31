# ARCHITECTURE DECISION REQUEST

## ADR-008-003

**Project:** TACTICAL CORE  
**Author:** Chief Systems Architect  
**Status:** AWAITING DECISION  
**Date:** 2026-05-09

---

## CONTEXT

During the independent technical review of WO-008-001, an architectural ambiguity was identified regarding the canonical integration pattern for external connectors.

The current repository contains a Signal Connector implementation that follows one pattern, but the relationship between external connectors and the Observation Engine has not been formally defined.

**Examples of connectors requiring integration:**
- Signal
- Telegram
- ATAK
- MQTT
- Email
- REST

---

## QUESTION

**How shall ALL external connectors integrate with the system?**

---

## OPTIONS

### OPTION A: Connector → Observation Engine → Observation → Event Bus

```
┌─────────────────┐
│    Connector    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Observation     │
│ Engine          │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Observation    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   Event Bus     │
└─────────────────┘
```

**Characteristics:**
- Connector sends raw data to Observation Engine
- Observation Engine owns Observation creation
- Observation is published to Event Bus after creation
- Connector has no Event Bus awareness

### OPTION B: Connector → Event Bus → Observation Service → Observation

```
┌─────────────────┐
│    Connector    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   Event Bus     │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Observation     │
│ Service         │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Observation    │
└─────────────────┘
```

**Characteristics:**
- Connector publishes to Event Bus immediately
- Observation Service subscribes to connector events
- Observation Service owns Observation creation
- Connector is decoupled from Observation logic

---

## DECISION REQUIRED FROM CSA

The Chief Systems Architect shall determine the canonical architecture by defining:

### 1. Canonical Entry Point
Where does external data first enter the system?

### 2. Ownership of Observation Creation
Which component is responsible for creating Observations?

### 3. Required Responsibilities of Every Future Connector
What must ALL connectors implement?

### 4. Required Responsibilities of Observation Engine
What must the Observation Engine provide?

### 5. Required Event Bus Behaviour
How must the Event Bus handle connector events?

---

## CURRENT IMPLEMENTATION STATUS

**WO-008-001 (Signal Connector Tests)**
- Implementation: Complete
- Independent Review: Pending
- Issue: Architecture clarification required

**Current Signal Connector Pattern:**
- Connector receives raw Signal payload
- Connector parses to SignalMessage
- Connector normalizes to SignalEvent
- Connector publishes to Event Bus (signal.message)
- No direct Observation Engine integration

---

## CONSTRAINTS

1. **No source code modifications shall be performed until CSA issues the canonical decision.**

2. **The existing WO-008-001 implementation is technically valid** but operates in an architecture ambiguity.

3. **Future connectors (Telegram, ATAK, MQTT, Email, REST) must follow the canonical pattern** once defined.

---

## REFERENCES

- ENTITY-001 Constitutional Architecture Revision 2.2
- Current Signal Connector: `backend/app/connectors/signal/`
- Observation Engine: `backend/app/intelligence/observation/engine.py`
- Event Bus: `backend/app/core/event_bus.py`

---

## STATUS

**AWAITING CHIEF SYSTEMS ARCHITECT DECISION**
