# Repository Structure

**Document ID:** DOC-001  
**Version:** 1.0  
**Status:** COMPLETE  
**Date:** 2026-07-23

---

## Purpose

This document describes the canonical repository structure for TACTICAL CORE v1.0 as established during Sprint 6.

---

## Canonical Repository

**Location:** `tactical_core/`

The canonical repository is the **ONLY active development repository**. All implementation work occurs within this repository.

---

## Repository Tree

```
tactical_core/
│
├── backend/                          # Main application code
│   ├── app/                          # Application core
│   │   ├── api/                      # REST API endpoints
│   │   ├── config/                  # Configuration management
│   │   ├── contracts/                # Interface contracts (ABCs)
│   │   ├── core/                     # Core event system
│   │   │   ├── event_bus.py          # Event distribution
│   │   │   ├── event_engine.py      # Event processing
│   │   │   ├── event_dispatcher.py   # Event routing
│   │   │   ├── event_registry.py     # Event registration
│   │   │   ├── event_history.py      # Event history
│   │   │   ├── event_hooks.py        # Event hooks
│   │   │   ├── event_exceptions.py   # Event exceptions
│   │   │   ├── event_context.py      # Event context
│   │   │   ├── event_result.py       # Event results
│   │   │   ├── health/               # Health monitoring
│   │   │   ├── metrics/             # Metrics collection
│   │   │   ├── middleware/           # Middleware
│   │   │   └── pipeline/             # Event pipeline stages
│   │   ├── database/                # Database layer
│   │   │   ├── base.py              # SQLAlchemy Base
│   │   │   ├── database.py          # Database connection
│   │   │   ├── dependencies.py      # Dependency injection
│   │   │   ├── migration.py         # Alembic migrations
│   │   │   ├── session.py           # Session management
│   │   │   └── repositories/        # Repository pattern
│   │   ├── enums/                   # Enumerations
│   │   ├── intelligence/            # Intelligence Core
│   │   │   ├── entity/              # Entity management
│   │   │   ├── event_bus/           # Intelligence event bus
│   │   │   ├── knowledge/           # Knowledge management
│   │   │   ├── pipeline/            # Intelligence pipeline
│   │   │   └── timeline/           # Timeline engine
│   │   ├── models/                 # Data models
│   │   ├── plugins/                # Plugin system
│   │   │   ├── base_plugin.py       # Base plugin class
│   │   │   ├── signal_reference_plugin.py  # Reference plugin
│   │   │   └── manager/             # Plugin manager
│   │   ├── schemas/                # Pydantic schemas
│   │   ├── services/              # Service layer
│   │   ├── utils/                  # Utilities
│   │   └── websocket/              # WebSocket support
│   ├── migrations/                 # Alembic migrations
│   ├── tests/                      # Tests
│   ├── requirements.txt             # Python dependencies
│   ├── config.py                   # Configuration
│   └── conftest.py                 # Pytest configuration
│
├── docs/                           # Documentation
│   ├── architecture/
│   │   ├── constitution/           # Constitutional documents
│   │   │   └── ENTITY-001-Constitutional-Architecture-Revision-2.2.md
│   │   ├── adr/                    # Architecture Decision Records
│   │   └── reviews/                # Architecture reviews
│   ├── sprint/                     # Sprint documentation
│   │   └── SPRINT_07/             # Sprint 7
│   │       ├── SPRINT_07_EXECUTION_ORDER.md
│   │       ├── README.md
│   │       ├── SPRINT_07_BACKLOG.md
│   │       ├── Verification_Package_Template/
│   │       └── [sprint files]
│   ├── templates/                 # Document templates
│   │   ├── verification_package/
│   │   ├── work_order/
│   │   ├── adr/
│   │   ├── review_report/
│   │   └── architecture_document/
│   ├── work_orders/               # Work Order documents
│   └── [existing docs]
│
├── plugins/                       # Plugin directory
│   └── __init__.py
│
├── scripts/                       # Utility scripts
│   └── generate_evidence.py
│
├── tests/                         # Additional tests
│   └── __init__.py
│
├── .github/
│   └── workflows/                 # CI/CD workflows
│       └── foundation-repair.yml
│
├── .gitignore
├── LICENSE
└── README.md
```

---

## Directory Purpose Summary

| Directory | Purpose | Owner |
|----------|---------|-------|
| backend/ | Main application code | Engineering |
| docs/ | All documentation | Documentation Architect |
| plugins/ | Plugin directory | Engineering |
| scripts/ | Utility scripts | Engineering |
| tests/ | Additional tests | QA |
| .github/ | CI/CD configuration | DevOps |

---

## Cross-References

- Constitution: `docs/architecture/constitution/ENTITY-001-Constitutional-Architecture-Revision-2.2.md`
- Sprint 7: `docs/sprint/SPRINT_07/SPRINT_07_EXECUTION_ORDER.md`
- Templates: `docs/templates/`

---

*Document prepared by Senior Documentation Engineer*
