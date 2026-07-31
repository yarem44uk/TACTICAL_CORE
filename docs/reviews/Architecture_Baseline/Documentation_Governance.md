# Documentation Governance

**Document ID:** DOC-006
**Version:** 1.0
**Status:** COMPLETE
**Date:** 2026-07-23

---

## Purpose

This document establishes the documentation governance rules for TACTICAL CORE.

---

## Document Ownership

| Document Type | Owner | Can Modify |
|--------------|-------|------------|
| Constitution | Chief Systems Architect | Chief Systems Architect only |
| ADR | Chief Systems Architect | Chief Systems Architect only |
| Architecture Review | Chief Systems Architect | Chief Systems Architect only |
| Work Order | Chief Systems Architect | Chief Systems Architect only |
| Sprint Order | Chief Systems Architect | Chief Systems Architect only |
| Sprint Report | PMO | PMO, with review |
| Template | Documentation Architect | Documentation Architect |
| Governance Doc | Documentation Architect | Documentation Architect |
| Engineering Doc | Senior Software Engineer | Senior Software Engineer |

---

## Versioning

All documents use semantic versioning:

| Document Type | Version Format | Example |
|---------------|---------------|---------|
| Constitution | Revision X.X | Revision 2.2 |
| ADR | ADR-XXX vX.X | ADR-001 v1.0 |
| Work Order | WO-XXX vX.X | WO-007 v1.0 |
| Sprint | Sprint XX | Sprint 7 |
| Template | Template vX.X | Template 1.0 |
| Governance | vX.X | v1.0 |

---

## Review Process

### Architecture Documents
1. Draft by owner
2. Independent Review Board review
3. Chief Systems Architect approval
4. Published to canonical location

### Engineering Documents
1. Draft by author
2. Peer review
3. QA verification (if applicable)
4. Published

### Sprint Documents
1. Draft by PMO
2. Chief Systems Architect review
3. Published

---

## Approval Process

| Document Type | Approval Required |
|---------------|------------------|
| Constitution | Chief Systems Architect only |
| ADR | Chief Systems Architect only |
| Work Order | Chief Systems Architect only |
| Sprint Order | Chief Systems Architect only |
| Sprint Report | PMO + Chief Systems Architect |
| Template | Documentation Architect |
| Governance | Documentation Architect |

---

## Cross-Reference Policy

Every document MUST reference:

1. Work Order references ADR + Constitution
2. Sprint Report references Sprint Order + Work Orders
3. ADR references Constitution
4. Template references Constitution + relevant Governance
5. Governance Doc references Constitution

Example:
```
This document inherits from:
- ENTITY-001 Constitutional Architecture
- ADR-001 (if applicable)
- Sprint 07 Execution Order (if applicable)
```

---

## Traceability

Every architectural statement must be traceable to:

```
Architecture (Constitution)
        |
        v
ADR (Architecture Decision)
        |
        v
Work Order (Implementation Authorization)
        |
        v
Implementation (Code + Tests)
        |
        v
Verification (QA Report)
        |
        v
Sprint Report (Completion)
```

No orphan documentation allowed.

---

## Document Status Values

| Status | Meaning |
|--------|---------|
| DRAFT | In development |
| REVIEW | Under review |
| APPROVED | Approved, active |
| DEPRECATED | Superseded, do not use |
| ARCHIVED | Historical reference |

---

## Cross-References

| Document | Reference |
|----------|-----------|
| Constitution | docs/architecture/constitution/ENTITY-001-Constitutional-Architecture-Revision-2.2.md |
| Authority Hierarchy | docs/reviews/Architecture_Baseline/Authority_Hierarchy.md |
| Engineering Workflow | docs/reviews/Architecture_Baseline/Engineering_Workflow.md |

---

*Document prepared by Senior Documentation Engineer*
