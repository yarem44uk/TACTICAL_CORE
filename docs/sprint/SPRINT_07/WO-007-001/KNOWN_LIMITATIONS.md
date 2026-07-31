# KNOWN LIMITATIONS

## WO-007-001-REWORK

---

## Runtime Verification Status

| Category | Status |
|----------|--------|
| Static Verification | ✅ PASS |
| Runtime Verification | ❌ UNAVAILABLE |

**Limitation:** Pyodide browser environment does not support subprocess execution required for pytest.

---

## Pending Architecture Decisions

### MF1: Soft-Delete Semantics

**Status:** ARCHITECTURE DECISION REQUIRED

**Issue:** Conflict identified between:
- Observation soft-delete implementation (is_deleted field)
- ENTITY-001 Constitutional rule: "correction is a new Observation"

**Required Action:** Architectural decision by Chief Systems Architect

**DO NOT:** Remove is_deleted, add is_deleted, or change deletion semantics

---

### MF2: Processing Status Mutation

**Status:** ARCHITECTURE DECISION REQUIRED

**Issue:** Conflict identified between:
- Mutable processing_status attribute
- Immutable Observation semantics per ENTITY-001

**Note:** Existing immutable event model may already represent lifecycle transitions

**Required Action:** Architectural decision by Chief Systems Architect

**DO NOT:** Remove processing_status, replace with event-derived state, or modify event architecture

---

## Verification Environment Limitations

| Limitation | Impact | Mitigation |
|------------|--------|------------|
| Pyodide environment | Cannot execute pytest | Execute locally |
| Browser sandbox | No subprocess access | Manual verification required |
| No local Python | Runtime tests blocked | Use local environment |

---

## Verification Status

| Finding | Remediation | Status |
|---------|-------------|--------|
| CF1: SQLAlchemy metadata collision | Renamed to observation_metadata | ✅ COMPLETE |
| CF2: ValidationError shadowing | Renamed to ObservationValidationError | ✅ COMPLETE |
| CF3: Test evidence | Clear documentation of UNAVAILABLE status | ✅ COMPLETE |
| CF4: Invalid GIT patch | Documented as CHANGE MANIFEST | ✅ COMPLETE |

---

## Next Steps for Complete Verification

1. **Local pytest execution:**
   ```bash
   cd /mnt/uploads/TACTICAL_CORE/backend
   pytest -v --tb=short
   ```

2. **Architecture decision on MF1**

3. **Architecture decision on MF2**

4. **Independent re-verification**

---

## Final Status

**REWORK COMPLETE — PENDING RUNTIME VERIFICATION AND INDEPENDENT RE-VERIFICATION**

---

**Document:** WO-007-001-REWORK  
**Generated:** 2026-07-25  
**Status:** PENDING RUNTIME VERIFICATION
