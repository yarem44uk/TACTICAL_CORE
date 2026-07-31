# Documentation Structure

**Document ID:** DOC-005
**Version:** 1.0
**Status:** COMPLETE
**Date:** 2026-07-23

---

## Purpose

This document describes the documentation organization for TACTICAL CORE.

---

## Documentation Hierarchy

```
TACTICAL CORE Documentation
|
|-- Architecture
|   |-- Constitution (ENTITY-001)
|   |-- ADR (Architecture Decision Records)
|   |-- Reviews (Architecture Reviews)
|
|-- Work Orders
|   |-- WO-001, WO-002, ...
|
|-- Sprint Documentation
|   |-- Sprint 07
|   |   |-- Execution Order
|   |   |-- Backlog
|   |   |-- Weekly Reports
|   |   |-- Daily Reports
|   |   |-- Issues
|   |   |-- Retrospective
|   |   |-- Review
|   |   |-- Completion Report
|   |-- [Future Sprints]
|
|-- Templates
|   |-- Verification Package
|   |-- Work Order
|   |-- ADR
|   |-- Review Report
|   |-- Architecture Document
|
|-- Governance
|   |-- Repository Governance
|   |-- Documentation Governance
|   |-- Engineering Workflow
|   |-- QA Process
|   |-- PMO Process
|
|-- Roadmaps
    |-- [Project Roadmaps]
```

---

## Directory Structure

```
tactical_core/docs/
|
|-- architecture/
|   |-- constitution/
|   |   |-- ENTITY-001-Constitutional-Architecture-Revision-2.2.md
|   |-- adr/
|   |   |-- ADR-001.md
|   |   |-- ADR-002.md
|   |   |-- [future ADRs]
|   |-- reviews/
|       |-- [review documents]
|
|-- work_orders/
|   |-- WO-001.md
|   |-- WO-002.md
|   |-- [future Work Orders]
|
|-- sprint/
|   |-- SPRINT_07/
|   |   |-- SPRINT_07_EXECUTION_ORDER.md
|   |   |-- SPRINT_07_BACKLOG.md
|   |   |-- SPRINT_07_WEEKLY_REPORT_W1.md
|   |   |-- SPRINT_07_WEEKLY_REPORT_W2.md
|   |   |-- SPRINT_07_ISSUES.md
|   |   |-- SPRINT_07_RETROSPECTIVE.md
|   |   |-- SPRINT_07_REVIEW.md
|   |   |-- SPRINT_07_COMPLETION_REPORT.md
|   |   |-- Verification_Package_Template/
|   |-- [future Sprints]
|
|-- templates/
|   |-- verification_package/
|   |   |-- README.md
|   |   |-- MANIFEST.md
|   |   |-- IMPLEMENTATION_REPORT.md
|   |   |-- [16 files total]
|   |-- work_order/
|   |-- adr/
|   |-- review_report/
|   |-- architecture_document/
|
|-- roadmap/
|   |-- [roadmap documents]
|
|-- [existing docs]
    |-- ARCHITECTURE_BLOCKER.md
    |-- ARCHITECTURE_DECISIONS.md
    |-- ARCHITECTURE_PROGRESS.md
    |-- ARCHITECTURE_REVIEW.md
    |-- [other sprint 6 docs]
```

---

## Document Types

| Type | Location | Owner | Format |
|------|----------|-------|--------|
| Constitution | architecture/constitution/ | Chief Systems Architect | Markdown |
| ADR | architecture/adr/ | Chief Systems Architect | Markdown |
| Architecture Review | architecture/reviews/ | Chief Systems Architect | Markdown |
| Work Order | work_orders/ | Chief Systems Architect | Markdown |
| Sprint Order | sprint/SPRINT_XX/ | Chief Systems Architect | Markdown |
| Sprint Report | sprint/SPRINT_XX/ | PMO | Markdown |
| Template | templates/ | Documentation Architect | Markdown |
| Governance | reviews/Architecture_Baseline/ | Documentation Architect | Markdown |
| Baseline Package | reviews/Architecture_Baseline/ | Documentation Architect | Markdown |

---

## Cross-References

| Document | Location |
|----------|----------|
| Constitution | docs/architecture/constitution/ENTITY-001-Constitutional-Architecture-Revision-2.2.md |
| Sprint 7 Order | docs/sprint/SPRINT_07/SPRINT_07_EXECUTION_ORDER.md |
| Templates | docs/templates/ |
| Baseline Package | docs/reviews/Architecture_Baseline/ |

---

*Document prepared by Senior Documentation Engineer*
