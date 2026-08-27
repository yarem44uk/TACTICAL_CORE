# WO-035 — Production Source Configuration Governance

Work Order: WO-035
Title: Production Source Configuration Governance
Status: Accepted / Architecture Approved
Classification: Architecture / Governance
Implementation Status: Definition Only
Implementation Authorization: Not Granted
Baseline: 0d6a9c89cf874c636f0cb980d2b93bc241143c57

## Purpose

WO-035 is an architecture/governance Work Order. It defines the controlled production source configuration boundary. It does NOT authorize production implementation.

WO-036 is the future implementation Work Order. WO-035 does NOT authorize WO-036 implementation.

## Architectural Objective

Define the controlled production source configuration boundary:

```
Static Source Catalog
        ↓
ISourceConfigProvider
        ↓
Production Composition
        ↓
Configured AdapterFactory
        ↓
Existing Adapter Registration Helpers
        ↓
Existing Adapter Runtime
```

The architecture reuses existing source and adapter abstractions. It does not introduce a second source configuration mechanism.

## Architectural Basis

The architecture references these existing primitives:

- ISourceConfigProvider
- SourceDefinition
- AdapterFactory
- ProductionSourceRegistrar

And these existing adapter registration helpers:

- register_atak_adapter
- register_mqtt_adapter
- register_signal_adapter
- register_radio_adapter
- register_telegram_adapter

## Future Implementation Boundary (WO-036)

The future WO-036 implementation is limited to:

- backend/app/event_sources/config/production_source_config.py
- backend/main.py
- backend/tests/test_wo036_production_source_config.py

Any change outside this boundary requires re-scoping and fresh architectural authorization.

## Protected Scope

The following are protected and must NOT be redesigned by WO-036:

- EventPipeline
- DurableCanonicalEvent
- DurableDeliveryDispatcher
- outbox
- retry
- dead-letter
- projection
- checkpoint
- EntityRepository
- RelationRepository
- adapter internals
- adapter schemas
- deployment/runtime infrastructure

## Fail-Closed Rules

The future WO-036 implementation must fail closed on:

- missing catalog
- malformed catalog
- duplicate source identity
- unknown adapter
- missing/invalid source configuration
- missing/invalid credentials_ref
- plaintext credentials
- duplicate adapter registration
- partial registration failure

Valid special cases:

- empty catalog → zero configured sources
- disabled-only catalog → zero active sources

## Credential Governance

credentials_ref = reference only.

The catalog must not contain plaintext secrets. No new secret manager. No new credential subsystem. Existing credential-resolution architecture is reused.

## Durable Delivery Invariant

require_durable_delivery=True must remain protected. WO-036 must not disable, weaken, bypass, or replace durable delivery.

## Future WO-036 Test Governance

The future WO-036 tests must cover:

- concrete provider
- static catalog
- empty catalog
- disabled-only catalog
- missing catalog
- malformed catalog
- duplicate source
- unknown adapter
- invalid configuration
- missing/invalid credentials_ref
- plaintext credential rejection
- five adapter registrations
- duplicate registration
- partial registration
- production provider wiring
- configured AdapterFactory
- SOURCE_CONFIGURATION_GAP closure
- require_durable_delivery=True

Tests are NOT created by WO-035.

## Acceptance Criteria

- AC-01 — Production source configuration boundary defined.
- AC-02 — Single static-catalog ISourceConfigProvider architecture defined.
- AC-03 — Existing AdapterFactory/ProductionSourceRegistrar reused.
- AC-04 — Five existing adapter registration helpers identified.
- AC-05 — Fail-closed semantics defined.
- AC-06 — credentials_ref reference-only rule defined.
- AC-07 — require_durable_delivery=True protected.
- AC-08 — Protected architecture scope defined.
- AC-09 — Future WO-036 implementation boundary defined.
- AC-10 — Future WO-036 test surface defined.
- AC-11 — Git verification requirements defined.
- AC-12 — WO-035 does not authorize implementation.

## Governance Boundary

WO-035 = governance / architecture definition
WO-036 = future implementation
WO-035 does NOT authorize WO-036 implementation.
