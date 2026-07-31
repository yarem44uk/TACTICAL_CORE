# Architecture Decision Log

**Document ID:** DOC-010
**Version:** 1.0
**Status:** COMPLETE
**Date:** 2026-07-23

---

## Purpose

This document is the registry of all Architecture Decisions (ADRs) for TACTICAL CORE.

---

## ADR Format

Each ADR follows this structure:

```markdown
# ADR-XXX: [Title]

## Decision
[What was decided]

## Context
[Why this decision was needed]

## Alternatives Considered
1. [Alternative 1]
2. [Alternative 2]
3. [Alternative 3]

## Consequences
### Positive
- [Benefit 1]
- [Benefit 2]

### Negative
- [Cost 1]
- [Cost 2]

## Status
APPROVED / PROPOSED / DEPRECATED
```

---

## ADR Registry

| ADR | Title | Date | Status |
|-----|-------|------|--------|
| ADR-001 | Canonical Repository Selection | 2026-07-23 | APPROVED |
| ADR-002 | ENTITY-001 Constitutional Baseline | 2026-07-23 | APPROVED |
| ADR-003 | Authority Hierarchy | 2026-07-23 | APPROVED |
| ADR-004 | Repository Governance | 2026-07-23 | APPROVED |
| ADR-005 | Documentation Organization | 2026-07-23 | APPROVED |
| ADR-006 | Sprint Governance | 2026-07-23 | APPROVED |

---

## ADR-001: Canonical Repository Selection

### Decision
`tactical_core/` is designated as the single canonical repository.

### Context
During Sprint 6, multiple repositories existed with overlapping functionality:
- tactical_core/ (Platform Foundation VERIFIED)
- TACTICAL_CORE/ (Full Platform, empty docker/frontend)
- tactical_core_fixed/ (Fix branch)

### Alternatives Considered
1. Keep both tactical_core/ and TACTICAL_CORE/ as parallel repositories
2. Merge tactical_core/ and TACTICAL_CORE/ into one
3. Create new repository combining both

### Consequences
**Positive:**
- Single source of truth
- No confusion about canonical location
- Simpler governance
- Clear development path

**Negative:**
- Some historical content in TACTICAL_CORE/ not immediately available
- Docker/Frontend need separate development

### Status: APPROVED

---

## ADR-002: ENTITY-001 Constitutional Baseline

### Decision
ENTITY-001 Constitutional Architecture Revision 2.2 becomes the immutable constitutional baseline.

### Context
TACTICAL CORE requires a stable, immutable architectural foundation that all future development inherits from.

### Alternatives Considered
1. Keep Constitution mutable during development
2. Use external reference for Constitution
3. Version Constitution with each sprint

### Consequences
**Positive:**
- Stable foundation
- Clear inheritance model
- Prevents architectural drift
- Enables long-term planning

**Negative:**
- Requires formal amendment process for changes
- Slower evolution of core concepts

### Status: APPROVED

---

## ADR-003: Authority Hierarchy

### Decision
Establish 5-level authority hierarchy: Constitution > Chief Systems Architect > ADR > Work Order > Implementation

### Context
TACTICAL CORE requires clear decision authority to prevent conflicts and ensure architectural integrity.

### Alternatives Considered
1. Flat authority with voting
2. Single person authority (Chief Systems Architect only)
3. Committee-based authority

### Consequences
**Positive:**
- Clear decision authority
- Prevents conflicts
- Enables independent work streams
- Traceable decisions

**Negative:**
- Potential bottlenecks at Chief Systems Architect level
- Requires careful document maintenance

### Status: APPROVED

---

## ADR-004: Repository Governance

### Decision
Establish governance rules for canonical repository including branch policy, merge policy, and archive policy.

### Context
Multiple legacy repositories created confusion. Governance rules prevent future issues.

### Alternatives Considered
1. No formal governance (trust-based)
2. Heavy governance with many rules
3. Gradual governance establishment

### Consequences
**Positive:**
- Clear rules for all participants
- Prevents unauthorized changes
- Enables long-term maintenance

**Negative:**
- Initial governance setup effort
- Documentation overhead

### Status: APPROVED

---

## ADR-005: Documentation Organization

### Decision
Establish structured documentation hierarchy with templates for all document types.

### Context
TACTICAL CORE requires organized documentation for 10-15 year lifecycle.

### Alternatives Considered
1. Minimal documentation
2. Ad-hoc documentation
3. Heavy documentation requirements

### Consequences
**Positive:**
- Organized documentation
- Easy to find information
- Templates ensure consistency

**Negative:**
- Initial documentation effort
- Templates require maintenance

### Status: APPROVED

---

## ADR-006: Sprint Governance

### Decision
Establish Sprint workflow with formal execution order, gate checks, and verification process.

### Context
TACTICAL CORE requires structured development process for multiple Work Orders.

### Alternatives Considered
1. Agile with minimal process
2. Waterfall approach
3. Hybrid approach

### Consequences
**Positive:**
- Structured development
- Clear dependencies
- Quality gates

**Negative:**
- Process overhead
- Less flexibility

### Status: APPROVED

---

## Future ADRs

The following ADRs are anticipated for Sprint 8+:
- ADR-007: Observation Engine Architecture
- ADR-008: Driver Framework Design
- ADR-009: Speech Recognition Pipeline
- ADR-010: Identity Resolution Algorithm
- ADR-011: Entity Manager Design
- ADR-012: Timeline Engine Architecture

---

## Cross-References

| Document | Reference |
|----------|-----------|
| Constitution | docs/architecture/constitution/ENTITY-001-Constitutional-Architecture-Revision-2.2.md |
| Authority Hierarchy | docs/reviews/Architecture_Baseline/Authority_Hierarchy.md |
| Repository Governance | docs/reviews/Architecture_Baseline/Repository_Governance.md |

---

*Document prepared by Senior Documentation Engineer*
