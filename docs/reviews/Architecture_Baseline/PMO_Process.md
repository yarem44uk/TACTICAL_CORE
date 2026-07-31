# PMO Process

**Document ID:** DOC-008
**Version:** 1.0
**Status:** COMPLETE
**Date:** 2026-07-23

---

## Purpose

This document describes the Program Management Office process for TACTICAL CORE.

---

## PMO Responsibilities

The PMO is responsible for:
- Sprint Planning
- Work Order Management
- Dependency Management
- Risk Management
- Progress Tracking
- Release Readiness
- Roadmap Management

---

## Sprint Planning

### Pre-Sprint Activities

1. Review Architecture Baseline
2. Review approved Work Orders
3. Assess dependencies
4. Estimate effort
5. Assign owners

### Sprint Backlog Structure

| WO | Name | Priority | Dependencies | Owner | Status |
|----|------|-----------|---------------|-------|--------|
| WO-007 | Observation Engine | Critical | - | TODO | READY |
| WO-008 | Driver Framework | Critical | WO-007 | TODO | WAITING |
| WO-009 | Operator Audio Driver | High | WO-008 | TODO | WAITING |
| WO-010 | Speech Recognition | High | WO-009 | TODO | WAITING |
| WO-011 | Callsign Detection | High | WO-010 | TODO | WAITING |
| WO-012 | Identity Resolution | Critical | WO-011 | TODO | WAITING |
| WO-013 | Entity Manager | Critical | WO-012 | TODO | WAITING |
| WO-014 | Timeline Engine | High | WO-013 | TODO | WAITING |
| WO-015 | Tactical Wall MVP | High | WO-014 | TODO | WAITING |

### Sprint Execution Order

Work Orders SHALL be executed sequentially as per dependency order.
PMO may authorize parallel execution only if:
1. Dependencies are satisfied
2. Chief Systems Architect approves
3. No architectural conflicts

---

## Work Order Lifecycle

| State | Description |
|-------|-------------|
| DRAFT | Work Order being prepared |
| APPROVED | Authorized by Chief Systems Architect |
| IN_PROGRESS | Implementation started |
| UNDER_REVIEW | QA verification in progress |
| VERIFIED | QA approved |
| COMPLETED | Released |
| ARCHIVED | Historical reference |

---

## Dependency Management

### Dependency Rules

1. No Work Order begins until all prerequisite Work Orders are VERIFIED
2. Circular dependencies are prohibited
3. Missing dependencies must be reported to Chief Systems Architect
4. Dependency changes require Chief Systems Architect approval

### Dependency Matrix

| From | To | Type |
|------|-----|------|
| WO-007 | WO-008 | Required |
| WO-008 | WO-009 | Required |
| WO-009 | WO-010 | Required |
| WO-010 | WO-011 | Required |
| WO-011 | WO-012 | Required |
| WO-012 | WO-013 | Required |
| WO-013 | WO-014 | Required |
| WO-014 | WO-015 | Required |

---

## Risk Management

### Risk Register Format

| ID | Description | Probability | Impact | Owner | Mitigation | Status |
|----|-------------|-------------|--------|-------|------------|--------|
| R001 | Observation Engine complexity | MEDIUM | HIGH | TODO | Careful design | OPEN |
| R002 | Speech recognition accuracy | MEDIUM | MEDIUM | TODO | Testing with synthetic data | OPEN |

### Risk Review

PMO reviews risks:
- Weekly during Sprint
- Before each release
- When new risks identified

---

## Milestones

| Milestone | Target | Work Orders | Status |
|-----------|--------|-------------|--------|
| MVP Core | Sprint 7 | WO-007 - WO-015 | PLANNED |
| Signal Integration | Sprint 8 | TBD | PLANNED |
| Knowledge Graph | Sprint 9 | TBD | PLANNED |

---

## Acceptance Gates

### Sprint Start Gate

Sprint may begin only if:
- Architecture approved
- Constitution stable
- Work Orders approved
- Repository ready
- Documentation prepared

### Sprint End Gate

Sprint may finish only if:
- All Critical Work Orders VERIFIED
- QA reports PASS
- Documentation updated
- Sprint Report completed
- Release decision recorded

---

## Progress Tracking

### Weekly Status Report

| Metric | Value |
|--------|-------|
| Work Orders Completed | X/Y |
| Work Orders Blocked | X |
| Architecture Questions | X |
| QA Findings | X |
| Days Remaining | X |

### Overall Program Health

| Category | Status |
|----------|--------|
| Architecture | ON_TRACK / AT_RISK / BLOCKED |
| Engineering | ON_TRACK / AT_RISK / BLOCKED |
| Documentation | ON_TRACK / AT_RISK / BLOCKED |
| QA | ON_TRACK / AT_RISK / BLOCKED |
| Repository | ON_TRACK / AT_RISK / BLOCKED |
| Schedule | ON_TRACK / AT_RISK / BLOCKED |

---

## Cross-References

| Document | Reference |
|----------|-----------|
| Sprint Order | docs/sprint/SPRINT_07/SPRINT_07_EXECUTION_ORDER.md |
| Engineering Workflow | docs/reviews/Architecture_Baseline/Engineering_Workflow.md |
| QA Process | docs/reviews/Architecture_Baseline/QA_Verification_Process.md |
| Authority Hierarchy | docs/reviews/Architecture_Baseline/Authority_Hierarchy.md |

---

*Document prepared by Senior Documentation Engineer*
