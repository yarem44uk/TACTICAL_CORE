# WO-013-005 — Architecture Decision

## 1. Status

PROPOSED — REQUIRES CHIEF SYSTEMS ARCHITECT APPROVAL / INDEPENDENT AUDIT

This document formally defines the scope and architectural perimeter of Work Order
WO-013-005. It is an Architecture Decision Document (ADD), not an implementation.
No production code is authorized by this document alone; implementation is authorized
only within the perimeter defined by this Architecture Decision and after the
implementation gate is approved.

## 2. Work Order

WO-013-005 — Signal Source Adapter

## 3. Purpose

Create the first protocol-specific adapter that implements the existing WO-013 Source
Adapter architecture. WO-013-005 delivers a Signal source adapter that:

- implements the existing `IEventSourceAdapter` contract;
- lives under the event_sources adapter architecture;
- integrates through the existing `AdapterFactory` / `SourceRegistry`;
- runs under the existing `AdapterRuntime` / `AdapterSupervisor`;
- produces canonical Event objects;
- feeds the existing Event Processing Pipeline.

## 4. Scope

WO-013-005 = SIGNAL SOURCE ADAPTER.

The adapter is the first concrete, protocol-specific adapter built on top of the
already-existing WO-013 Source Adapter architecture. It converts Signal-originated
input into canonical Event objects and delivers them to the Event Processing Pipeline
through the established adapter/runtime path.

This WO does NOT introduce any new generic runtime, supervisor, configuration
subsystem, or Event model. It reuses all existing WO-013 and WO-012 contracts.

## 5. Architectural Context

The WO-013 architecture is composed of the following layers, in dependency order:

    core / interfaces
        |
        v
    AdapterFactory / SourceRegistry / Source Configuration
        |
        v
    AdapterRuntime / AdapterSupervisor
        |
        v
    IEventSourceAdapter implementations (SignalSourceAdapter)
        |
        v
    EventFactory
        |
        v
    canonical Event
        |
        v
    Event Processing Pipeline

The SignalSourceAdapter sits at the concrete-adapter layer. It depends on existing
abstractions/contracts; generic core never depends on Signal-specific implementation.

## 6. Legacy Signal Boundary

An existing legacy Signal connector lives at:

    backend/app/connectors/signal/

This legacy subsystem is OUTSIDE the implementation scope of WO-013-005. It is
coupled directly to the Event Bus and predates the WO-013 Source Adapter
architecture.

WO-013-005 MUST NOT silently:
- delete it;
- rewrite it;
- move it;
- replace it;
- change its EventBus integration;
- couple the new SignalSourceAdapter to it.

The new `SignalSourceAdapter` is a separate, architecturally distinct path. Any
migration/removal of the legacy connector requires a separate Architecture Decision
explicitly authorizing it.

## 7. Allowed Perimeter

The future implementation may create/modify ONLY:

- the Signal adapter implementation (a protocol-specific adapter that implements
  `IEventSourceAdapter`);
- directly required adapter-specific helper files for the Signal adapter;
- directly required adapter registration/wiring using the existing
  `AdapterFactory` / `SourceRegistry` mechanisms;
- adapter-specific tests for the Signal adapter;
- architecture/evidence documentation required by this WO.

The concrete package perimeter (subject to final determination at the implementation
gate, expressed as a package boundary rather than invented file names):

    backend/app/event_sources/adapters/   (Signal adapter and its direct helpers)
    backend/tests/                        (Signal adapter tests)
    docs/architecture/                    (this WO's evidence/documentation)

No other files may be created or modified.

## 8. Protected Perimeter

WO-013-005 MUST NOT modify:

- backend/app/event/
- backend/app/event_pipeline/
- backend/app/event_bus/
- backend/app/database/
- backend/app/api/
- backend/app/event_sources/runtime/
- backend/app/event_sources/registry/source_registry.py
- backend/app/event_sources/adapters/base_adapter.py
- backend/app/event_sources/interfaces/i_event_source_adapter.py
- backend/app/event_sources/factory/event_factory.py
- backend/app/connectors/signal/

These are protected unless a separate Architecture Decision explicitly authorizes
modification.

## 9. Existing Contracts

WO-013-005 MUST NOT change:

- canonical Event contract;
- EventFactory contract;
- `IEventSourceAdapter` contract;
- EventBus contract;
- Event Processing Pipeline contract;
- Source Configuration Management contract;
- AdapterRuntime contract;
- AdapterSupervisor contract.

If implementation appears to require any contract change, implementation MUST STOP
and report the required change to the Chief Systems Architect. No contract change is
authorized within this WO.

## 10. Dependency Direction

The required architectural direction is:

    canonical core / interfaces
        |
        v
    factory / registry / configuration
        |
        v
    runtime / supervisor
        |
        v
    SignalSourceAdapter
        |
        v
    canonical Event
        |
        v
    Event Processing Pipeline

Generic core MUST NOT import Signal-specific code. Protocol-specific behavior is
contained entirely inside the SignalSourceAdapter. There must be no reverse
dependency from generic layers to the Signal adapter.

## 11. Lifecycle Authority

WO-013-005 reuses the existing lifecycle authority:

- AdapterRuntime — owns one-adapter execution, poll loop, state machine;
- AdapterSupervisor — owns N runtime orchestration, health aggregation, restart.

WO-013-005 MUST NOT create a second runtime or supervisor, must not introduce its own
polling/threading, and must not re-implement restart or lifecycle logic. The
SignalSourceAdapter implements only the `IEventSourceAdapter` lifecycle methods
(start, stop, health/readiness, read_events, source_name) and relies on the runtime
for actual lifecycle management.

## 12. Failure Isolation

Documented expected behavior:

- malformed Signal input: the adapter read path surfaces errors to the runtime; a
  malformed event is dropped, the runtime remains alive;
- adapter read failure: handled as a recoverable read failure by the existing runtime
  (DEGRADED, retry, no restart-budget consumption) per established WO-013-003
  semantics;
- adapter degraded state: reported through the existing runtime health path;
- runtime failure: handled by AdapterRuntime/AdapterSupervisor bounded-restart policy;
- a Signal adapter failure must NOT terminate unrelated adapters and must NOT corrupt
  the Event Processing Pipeline.

Failure isolation is provided by the existing runtime/supervisor architecture; the
Signal adapter does not add its own isolation mechanism.

## 13. Security Boundary

- No credentials or secrets may be hardcoded;
- no secrets may be committed to Git;
- no secrets may be embedded in tests;
- credentials are referenced only through the existing configuration / credential
  reference mechanism;
- no new secret-store / secret-management subsystem is authorized in this WO;
- no credential logging.

## 14. Test Strategy

The future implementation tests MUST cover:

- `IEventSourceAdapter` interface compliance;
- adapter construction;
- adapter registration through AdapterFactory / SourceRegistry;
- lifecycle (start, stop, health/readiness);
- valid Signal input;
- malformed Signal input;
- conversion to canonical Event;
- failure handling;
- isolation / restart behavior;
- no leakage of protocol-specific implementation into generic core;
- regression of existing WO-013 components.

## 15. Explicit OUT OF SCOPE

Explicitly excluded from WO-013-005:

- MQTT adapter;
- Radio adapter;
- ATAK adapter;
- MPU5 adapter;
- REST adapter;
- Telegram adapter;
- Email adapter;
- Event model redesign;
- Event Bus redesign;
- Event Processing Pipeline redesign;
- database redesign;
- runtime redesign;
- supervisor redesign;
- Source Configuration redesign;
- legacy Signal connector migration;
- secret-store implementation.

## 16. Architecture Acceptance Criteria

WO-013-005 is considered architecturally accepted when:

- the Signal adapter implements the existing `IEventSourceAdapter` contract unchanged;
- the adapter integrates through the existing AdapterFactory / SourceRegistry without
  modifying them;
- the adapter runs under the existing AdapterRuntime / AdapterSupervisor without
  introducing a second runtime/supervisor;
- the adapter produces canonical Event objects for the existing pipeline;
- no protected file/package is modified;
- no contract is changed;
- generic core contains no Signal-specific imports;
- credentials are reference-only, with no secrets committed;
- all required tests pass and existing WO-013 components regress cleanly.

## 17. Implementation Authorization

Implementation is authorized only within the perimeter defined by this Architecture
Decision.

This document alone does not authorize implementation. Implementation proceeds only
after this Architecture Decision is approved and the implementation gate is passed.
