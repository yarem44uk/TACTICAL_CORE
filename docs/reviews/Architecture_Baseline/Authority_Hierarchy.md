# Authority Hierarchy

**Document ID:** DOC-003  
**Version:** 1.0  
**Status:** COMPLETE  
**Date:** 2026-07-23

---

## Purpose

This document describes the complete decision authority hierarchy for TACTICAL CORE. Every artifact in the project is governed by a specific authority level, and lower-level artifacts MUST NOT contradict higher-level artifacts.

---

## Absolute Authority Hierarchy

```
┌─────────────────────────────────────────────────────────────┐
│ LEVEL 1: CONSTITUTION (Highest Authority)                    │
│ Entity-001 Constitutional Architecture Revision 2.2          │
│ Immutable. Cannot be violated.                              │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ LEVEL 2: CHIEF SYSTEMS ARCHITECT                            │
│ Architecture decisions, Work Order approval, ADR authority  │
│ Can amend Constitution (formal process)                     │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ LEVEL 3: ARCHITECTURE DECISIONS (ADR)                      │
│ ADR-001 through ADR-006+                                    │
│ Documented decisions, binding for implementation            │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ LEVEL 4: WORK ORDERS                                        │
│ WO-001, WO-002, WO-003...                                   │
│ Implementation authorization, scope definition             │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ LEVEL 5: ENGINEERING IMPLEMENTATION                         │
│ Code, tests, documentation                                  │
│ Must conform to all higher levels                          │
└─────────────────────────────────────────────────────────────┘
```

---

## Level 1: Constitution

**Authority:** ENTITY-001 Constitutional Architecture Revision 2.2

The Constitution is the supreme law of TACTICAL CORE. It defines:
- 13 Constitutional Principles
- 9 Future Architecture Constraints
- 17 Core Concepts
- Intelligence Philosophy
- Amendment Process

**Who can change:** Chief Systems Architect only, through formal Constitutional Amendment

**Location:** `docs/architecture/constitution/ENTITY-001-Constitutional-Architecture-Revision-2.2.md`

---

## Level 2: Chief Systems Architect

**Authority:** All architectural decisions

The Chief Systems Architect owns:
- Architecture (approved and pending)
- Domain model
- Intelligence concepts
- System behavior
- Work Order sequencing
- Approval authority

**Current:** Chief Systems Architect role (unassigned to specific name)

---

## Level 3: Architecture Decisions (ADR)

**Authority:** Documented in ADR registry

ADRs document specific architectural decisions including:
- Decision
- Context
- Alternatives considered
- Consequences
- Status

**Current ADRs:**
- ADR-001: Canonical Repository Selection
- ADR-002: ENTITY-001 Constitutional Baseline
- ADR-003: Authority Hierarchy
- ADR-004: Repository Governance
- ADR-005: Documentation Organization
- ADR-006: Sprint Governance

**Location:** `docs/architecture/adr/` (future)

---

## Level 4: Work Orders

**Authority:** Assigned by Chief Systems Architect

Work Orders authorize specific implementation:
- WO-001: Observation Engine
- WO-002: Driver Framework
- And so on...

**Scope:** Implementation must stay within Work Order scope

---

## Level 5: Engineering Implementation

**Authority:** Senior Software Engineer

Implementation responsibilities:
- Code according to Work Order
- Tests according to requirements
- Documentation updates
- Verification Package preparation

---

## QA Authority

**Authority:** QA & Verification Engineer

QA has authority to:
- Verify implementation against Work Order
- Reject non-compliant implementations
- Report architectural violations

---

## Release Authority

**Authority:** Chief Systems Architect (with QA input)

Release decisions require:
- All Work Orders VERIFIED
- QA reports PASS
- Documentation complete

---

## Cross-Reference Validation

Every lower-level artifact must reference its governing higher-level artifact:

| Artifact Level | Must Reference |
|---------------|----------------|
| Work Order | ADR, Constitution |
| Implementation | Work Order, ADR, Constitution |
| Documentation | Architecture Document, Constitution |
| QA Report | Work Order, Constitution |

---

## Violation Detection

If a lower-level artifact contradicts a higher-level artifact:
1. STOP immediately
2. Report to Chief Systems Architect
3. Do NOT proceed without resolution

---

*Document prepared by Senior Documentation Engineer*
