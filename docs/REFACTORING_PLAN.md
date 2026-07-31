# Refactoring Plan
## Tactical Core v1.0

**Purpose:** Document planned refactoring activities to improve code quality and maintainability.

---

## 1. EventEngine.publish() Refactoring

### Problem
The publish() method is 147 lines and handles multiple responsibilities:
- Validation
- Event enrichment
- Persistence
- Dispatch
- Broadcasting
- Notifications
- Result construction

### Proposed Solution
Extract into focused private methods.

### Methods to Extract
1. _validate_event(event_data)
2. _enrich_event(event_data, context)
3. _prepare_event(event_data, context, event_type)
4. _persist_event(event_data)
5. _store_history(event, context, result)
6. _dispatch_event(event, context, event_type)
7. _broadcast_websocket(event, context)
8. _notify_ai_engine(event, context)
9. _notify_plugins(event, context, event_type)
10. _build_result(event_data, context, ...)

### Effort: 4-6 hours

---

## 2. Add Async Database Repository

### Problem
Current repository is synchronous. High-scale deployments will block on I/O.

### Proposed Solution
Create async version following same interface using SQLAlchemy async.

### Files to Create
- backend/app/database/repositories/async_base_repository.py
- backend/app/database/repositories/async_event_repository.py

### Effort: 2-3 days

---

## 3. Plugin Interface Definition

### Problem
Plugin system exists but interface is undefined.

### Proposed Solution
Define abstract base class (ABC) for plugins.

### Required Methods
- plugin_id property
- plugin_name property
- register(event_engine)
- unregister()
- on_event(event, context)

### Optional Methods
- on_startup()
- on_shutdown()
- get_subscriptions()

### Files to Create
- backend/app/plugins/interfaces.py
- backend/app/plugins/base.py

### Effort: 1-2 days

---

## 4. Test Suite Structure

### Problem
No tests exist, creating risk for future development.

### Proposed Structure
- tests/conftest.py - Pytest fixtures
- tests/unit/ - Unit tests for core components
- tests/integration/ - Integration tests
- tests/fixtures/ - Shared test data

### Priority Tests
1. EventEngine.publish() lifecycle
2. EventBus subscribe/publish
3. EventRegistry registration
4. Repository CRUD operations
5. Validation logic

### Effort: 3-5 days

---

## Refactoring Order

| Phase | Item | Effort |
|-------|------|--------|
| 1 | EventEngine.publish() refactor | 4-6h |
| 2 | Plugin Interface | 1-2d |
| 3 | Test Structure | 3-5d |
| 4 | Async Repository | 2-3d |

---

## Success Criteria

- No method > 100 lines
- Test coverage > 80%
- All public APIs have type hints
- All public APIs have docstrings
- Plugin interface documented

---

*Refactoring plan created as part of Architecture Review.*