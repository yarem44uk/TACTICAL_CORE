# Deprecation Lifecycle Policy

**Document Type:** Lifecycle Management  
**Authority:** Chief Systems Architect  
**Date:** 2026-07-27 10:13:34  
**Status:** ACTIVE

---

## Purpose

This document defines the lifecycle states and transition criteria for deprecated components in TACTICAL CORE.

---

## Lifecycle States

```
ACTIVE ─────────► CANONICAL ─────────► DEPRECATED ─────────► REMOVAL CANDIDATE ─────────► REMOVED
   │                  │                    │                     │                        │
   │                  │                    │                     │                        │
   │             Full production      Maintenance only      Ready for          Successfully
   │             use, new features    No new features       removal             removed from
   │             supported            Bug fixes only        Approval required    codebase
```

---

## State Definitions

### ACTIVE

| Attribute | Description |
|-----------|-------------|
| **Description** | Component is actively developed and recommended for use |
| **New Features** | YES |
| **Bug Fixes** | YES |
| **Migration Support** | N/A |
| **Documentation** | Maintained |

---

### CANONICAL

| Attribute | Description |
|-----------|-------------|
| **Description** | Component is the officially recommended implementation |
| **New Features** | YES |
| **Bug Fixes** | YES |
| **Migration Support** | N/A |
| **Documentation** | Full |
| **Usage** | Required for new development |

**Transition TO Canonical:**
- Architecture review passed
- Chief Systems Architect approval
- ADR created

---

### DEPRECATED

| Attribute | Description |
|-----------|-------------|
| **Description** | Component is maintained for backward compatibility but NOT recommended for new use |
| **New Features** | NO |
| **Bug Fixes** | YES (critical only) |
| **Migration Support** | YES |
| **Documentation** | Warning labels added |
| **Usage** | Discouraged |

**Transition TO Deprecated:**
- New canonical implementation available
- Migration path exists
- Chief Systems Architect approval
- Warning issued to consumers

**Required Actions:**
1. Add deprecation warning to documentation
2. Add `@deprecated` decorator/code comments
3. Add deprecation notice in README
4. Create migration guide
5. Notify affected teams

---

### REMOVAL CANDIDATE

| Attribute | Description |
|-----------|-------------|
| **Description** | Component is ready for removal pending final approval |
| **New Features** | NO |
| **Bug Fixes** | NO |
| **Migration Support** | Completed |
| **Documentation** | Archived |
| **Usage** | Prohibited for new code |

**Transition TO Removal Candidate:**
- Production imports = 0
- Test imports = 0
- All consumers migrated
- Rollback procedures documented
- Chief Systems Architect approval required

**Required Verification:**
```bash
# Verify zero production imports
grep -r "from app.core.pipeline\|import app.core.pipeline" --include="*.py" TACTICAL_CORE/backend/app/

# Verify zero test imports
grep -r "from app.core.pipeline\|import app.core.pipeline" --include="*.py" TACTICAL_CORE/backend/tests/
```

---

### REMOVED

| Attribute | Description |
|-----------|-------------|
| **Description** | Component no longer exists in codebase |
| **New Features** | NO |
| **Bug Fixes** | NO |
| **Migration Support** | NO |
| **Documentation** | Archived with replacement reference |
| **Usage** | Not possible |

**Transition TO Removed:**
- Final architecture review
- Chief Systems Architect approval
- ADR update with removal record
- Code removed from repository

---

## Approval Requirements

| Transition | Required Approvals |
|------------|-------------------|
| ACTIVE → CANONICAL | Chief Systems Architect |
| CANONICAL → DEPRECATED | Chief Systems Architect |
| DEPRECATED → REMOVAL CANDIDATE | Chief Systems Architect + QA Lead |
| REMOVAL CANDIDATE → REMOVED | Chief Systems Architect + Technical Committee |

---

## System A: `app.core.pipeline` Lifecycle Status

| State | Status | Date |
|-------|--------|------|
| CANONICAL | COMPLETE | Prior to WO-ARCH-001 |
| DEPRECATED | COMPLETE | WO-ARCH-001 completion |
| REMOVAL CANDIDATE | PENDING | Upon KPI-001, KPI-002 = 0 |
| REMOVED | PENDING | Upon EventEngine migration + approval |

---

## References

- **Pipeline Status:** [PIPELINE_STATUS.md](../architecture/pipeline/PIPELINE_STATUS.md)
- **Migration Policy:** [PIPELINE_MIGRATION_POLICY.md](./PIPELINE_MIGRATION_POLICY.md)
- **Migration KPI:** [PIPELINE_MIGRATION_KPI.md](./PIPELINE_MIGRATION_KPI.md)
- **Architecture Decision:** [ADR-010](../adr/ADR-010-PIPELINE-CANONICAL-STATUS.md)

---

**APPROVED BY:** Chief Systems Architect  
**EFFECTIVE DATE:** 2026-07-27 10:13:34
