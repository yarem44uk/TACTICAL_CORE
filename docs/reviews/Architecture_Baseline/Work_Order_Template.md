# Work Order Template

**Document ID:** DOC-009
**Version:** 1.0
**Status:** COMPLETE (Reference)
**Date:** 2026-07-23

---

## Purpose

This document is a reference to the Work Order template location and format.

---

## Work Order Template Location

The official Work Order template is located at:
`docs/templates/work_order/`

---

## Work Order Format

Each Work Order follows this structure:

```
WORK ORDER WO-XXX

TITLE: [Name]
PRIORITY: [Critical/High/Medium/Low]
STATUS: [DRAFT/APPROVED/IN_PROGRESS/VERIFIED/COMPLETED]

AUTHORITY
========
This Work Order inherits from:
1. ENTITY-001 Constitutional Architecture
2. Sprint XX Execution Order
3. [Other ADRs]

MISSION
=======
[What this Work Order implements]

SCOPE
=====
This Work Order SHALL implement ONLY:
- [Item 1]
- [Item 2]

This Work Order SHALL NOT implement:
- [Out of scope item 1]
- [Out of scope item 2]

DEPENDENCIES
============
Requires: [Dependency WO]
Produces: [Output]

DELIVERABLES
============
- Implementation
- Unit tests
- Integration tests
- Documentation

ACCEPTANCE CRITERIA
===================
1. [Criterion 1]
2. [Criterion 2]

CONSTRAINTS
===========
- DO NOT modify Constitution
- DO NOT introduce new architectural concepts
- DO NOT violate Architectural Invariants

STOP CONDITIONS
===============
- Constitution is ambiguous
- Work Order contradicts Constitution
- Required interfaces missing
- Implementation requires architectural changes

OUTPUT
======
Upon completion:
1. Implementation Summary
2. Files Modified
3. Public Interfaces
4. Test Results
5. Documentation Updated
6. Known Limitations
7. Architecture Questions (if any)
8. Ready for QA: YES/NO

FINAL STATUS
============
ALLOWED: READY, IN_PROGRESS, IMPLEMENTED, VERIFIED, REQUIRES REWORK
```

---

## Current Work Orders

| WO | Title | Priority | Status |
|----|-------|----------|--------|
| WO-007 | Observation Engine | Critical | READY |
| WO-008 | Driver Framework | Critical | WAITING |
| WO-009 | Operator Audio Driver | High | WAITING |
| WO-010 | Speech Recognition Pipeline | High | WAITING |
| WO-011 | Callsign Detection Engine | High | WAITING |
| WO-012 | Identity Resolution Engine | Critical | WAITING |
| WO-013 | Entity Manager | Critical | WAITING |
| WO-014 | Timeline Engine | High | WAITING |
| WO-015 | Tactical Wall MVP | High | WAITING |

---

## Cross-References

| Document | Reference |
|----------|-----------|
| Constitution | docs/architecture/constitution/ENTITY-001-Constitutional-Architecture-Revision-2.2.md |
| Sprint Order | docs/sprint/SPRINT_07/SPRINT_07_EXECUTION_ORDER.md |
| Engineering Workflow | docs/reviews/Architecture_Baseline/Engineering_Workflow.md |

---

*Document prepared by Senior Documentation Engineer*
