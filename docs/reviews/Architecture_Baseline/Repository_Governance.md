# Repository Governance

**Document ID:** DOC-002  
**Version:** 1.0  
**Status:** COMPLETE  
**Date:** 2026-07-23

---

## Purpose

This document establishes the repository governance rules for TACTICAL CORE.

---

## Repository Purpose

The canonical repository (`tactical_core/`) serves as the single source of truth for all project artifacts including:
- Source code
- Configuration
- Documentation
- Tests
- Templates
- Scripts

---

## Canonical Repository

**Repository:** `tactical_core/`  
**Status:** ACTIVE  
**Purpose:** Single source of truth for development  
**Location:** `/mnt/uploads/tactical_core/`

---

## Legacy Repositories

The following repositories are classified as LEGACY and MUST NOT be used for active development:

| Repository | Classification | Reason | Action |
|------------|---------------|--------|--------|
| TACTICAL_CORE/ | LEGACY | Production snapshot with empty docker/frontend | Archive |
| tactical_core_fixed/ | LEGACY | Contains fixes merged to main | Archive |
| TACTICAL_CORE.zip | ARCHIVE | Old build | Remove |
| TACTICAL_CORE_FIXED.zip | ARCHIVE | Old fixed build | Remove |
| TACTICAL_CORE (1).zip | ARCHIVE | Old build v1 | Remove |

---

## Archive Policy

After Sprint 7 stabilizes:
1. Legacy repositories become READ-ONLY
2. Archive status is documented in PACKAGE_STATUS.md
3. No new development in archived repositories
4. Archives preserved for historical reference

---

## Naming Conventions

### Files
- Python files: `snake_case.py`
- Markdown files: `SCREAMING_SNAKE_CASE.md`
- Configuration: `snake_case.yml`

### Directories
- Use snake_case for directories
- Group related files by functionality

### Work Orders
- Format: `WO-XXX`
- Example: `WO-007`, `WO-008`

### ADRs
- Format: `ADR-XXX`
- Example: `ADR-001`, `ADR-002`

---

## Directory Ownership

| Directory | Primary Owner | Secondary Owner |
|-----------|--------------|-----------------|
| backend/ | Senior Software Engineer | Chief Systems Architect |
| docs/ | Documentation Architect | Chief Systems Architect |
| plugins/ | Senior Software Engineer | Chief Systems Architect |
| scripts/ | Senior Software Engineer | QA |
| tests/ | QA | Senior Software Engineer |
| .github/ | DevOps | Chief Systems Architect |

---

## Review Policy

All changes to the canonical repository require:
1. Work Order authorization
2. Code review (if applicable)
3. QA verification
4. Documentation update (if applicable)

---

## Branch Policy

**Current Policy:** Single branch development (main)  
**Rationale:** Small team, architectural baseline phase  
**Future:** Branch policy may be established in Sprint 8+

---

## Merge Policy

Merges occur when:
1. Work Order is VERIFIED by QA
2. Chief Systems Architect approves
3. Documentation is updated

No direct pushes to main without verification.

---

## Access Control

| Role | Access Level |
|------|-------------|
| Chief Systems Architect | Full |
| Senior Software Engineer | Read/Write |
| QA & Verification Engineer | Read |
| Documentation Architect | Read/Write (docs) |
| PMO | Read |

---

*Document prepared by Senior Documentation Engineer*
