# WORK ORDER WO-032

TITLE: Production Process Entrypoint
PRIORITY: High
STATUS: DEFINED

---

## AUTHORITY

This Work Order inherits from:
1. ENTITY-001 Constitutional Architecture
2. Verified WO-030 baseline (main = `d78dc2e55b2be025fa59ae3668871efc4008a5f1`)
3. WO-031 event reconstruction (parent of WO-030: `f24cc1c8342fabae08670fbda906478b220d0553`)
4. WO-030 durable production delivery wiring (single wiring owner, fail-closed durable delivery)

**Predecessor:** WO-030
**Required architectural baseline:** WO-030 durable production delivery wiring + WO-031 event reconstruction

---

## MISSION

Define and implement a minimal real production process entrypoint that turns the already-proven
production runtime composition into an executable long-lived process. WO-032 consumes the existing
production runtime; it MUST NOT redesign or modify the durable event pipeline.

---

## SCOPE

This Work Order SHALL implement ONLY:

1. Production process entrypoint (one authoritative entrypoint file).
2. Construction of the existing production runtime via `create_production_runtime()`.
3. Mandatory invocation with `require_durable_delivery=True`.
4. Explicit source registration using the existing source registration/configuration mechanisms.
5. Runtime startup (`runtime.start()`).
6. Process lifetime management (process remains alive after startup until a shutdown signal).
7. SIGINT handling.
8. SIGTERM handling.
9. Graceful runtime shutdown (`runtime.stop()` then clean process exit).
10. Focused tests for the entrypoint lifecycle.

**Preferred entrypoint location:** `backend/main.py`
**Alternative:** `backend/app/runtime_entrypoint.py`
(The implementation must choose exactly ONE authoritative entrypoint.)

---

## FORBIDDEN SCOPE

This Work Order SHALL NOT implement or modify the architectural implementation of:

- Event
- EventFactory
- EventPipeline durable path
- DurableDeliveryDispatcher
- Durable event repository
- SQLAlchemy event persistence
- durable outbox
- retry logic
- dead-letter logic
- event reconstruction
- entity projection
- relation projection
- checkpoint logic
- plugin delivery
- WO-029 implementation
- WO-030 implementation
- WO-031 implementation
- existing production composition wiring

If implementation appears to require changes to those components:
**STOP and report:** `WO-032_SCOPE_VIOLATION`
Do not silently expand scope.

---

## DEPENDENCIES

Requires: WO-030 (durable production delivery wiring), WO-031 (event reconstruction)
Produces: a real, executable production process entrypoint + focused lifecycle tests

---

## DELIVERABLES

- Production process entrypoint
- Unit/integration tests for the entrypoint lifecycle
- Documentation update reflecting the entrypoint

---

## ACCEPTANCE CRITERIA

1. **AC-01 — Real entrypoint:** A real non-test production entrypoint exists.
2. **AC-02 — Production runtime:** The entrypoint uses the existing `create_production_runtime()`.
3. **AC-03 — Durable delivery mandatory:** Production startup explicitly uses `require_durable_delivery=True`.
4. **AC-04 — Source registration:** Existing source registration/configuration mechanisms are used.
5. **AC-05 — Long-lived process:** The process remains alive after successful startup.
6. **AC-06 — SIGINT:** SIGINT causes graceful shutdown.
7. **AC-07 — SIGTERM:** SIGTERM causes graceful shutdown.
8. **AC-08 — Runtime lifecycle:** Existing `runtime.start()` / `runtime.stop()` lifecycle is respected.
9. **AC-09 — No core redesign:** WO-029 / WO-030 / WO-031 durable architecture remains unchanged.
10. **AC-10 — Focused tests:** All WO-032 focused tests pass.
11. **AC-11 — Existing regression protection:** Existing WO-029 / WO-030 / WO-031 focused suites remain green.
12. **AC-12 — Scope:** Only files explicitly required for the entrypoint and its focused tests are modified.

---

## TEST REQUIREMENTS

Focused WO-032 tests covering at minimum:

1. **Entrypoint construction** — verifies the entrypoint constructs the production runtime.
2. **Durable delivery requirement** — verifies the entrypoint requests `require_durable_delivery=True`.
3. **Startup** — verifies runtime startup is invoked.
4. **Shutdown** — verifies runtime shutdown is invoked.
5. **SIGINT** — verifies SIGINT requests graceful shutdown.
6. **SIGTERM** — verifies SIGTERM requests graceful shutdown.
7. **Process lifetime** — verifies the entrypoint does not terminate immediately after startup.

Tests must use the real production composition where practical. Do not weaken tests with broad mocks
merely to obtain green results.

---

## CONSTRAINTS

- DO NOT modify the durable event pipeline or delivery architecture.
- DO NOT introduce a new framework for process lifetime management.
- DO NOT introduce a new source-adapter framework.
- DO NOT silently fall back to legacy non-durable delivery.
- If the repository lacks sufficient production source configuration for a real source, document that
  limitation; do not redesign source adapters as part of WO-032.

---

## STOP CONDITIONS

- Implementation requires changes to WO-029 / WO-030 / WO-031 components.
- Implementation requires modifying the durable event pipeline or delivery architecture.
- A second database owner or second dispatcher would be required.
- The production runtime cannot be constructed with `require_durable_delivery=True`.

---

## OUTPUT

Upon completion:
1. Implementation Summary
2. Files Modified
3. Public Interfaces
4. Test Results
5. Documentation Updated
6. Known Limitations
7. Architecture Questions (if any)
8. Ready for QA: YES/NO

---

## FINAL STATUS

ALLOWED: DEFINED, IN_PROGRESS, IMPLEMENTED, VERIFIED, REQUIRES REWORK
Current status: **DEFINED**
