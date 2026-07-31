# ADR-006: Dependency Rules

**Date:** TASK-Sprint-004  
**Status:** Accepted  
**Deciders:** Architecture Team

---

## Context

To maintain Clean Architecture and prevent architectural decay, clear dependency rules must be established and enforced.

---

## Decision

Establish the following dependency rules:

### Layer Dependencies

```
contracts/     ← No dependencies (leaf)
    ↓
core/          ← Depends on contracts
    ↓
services/      ← Depends on core, database, models
    ↓
api/           ← Depends on core, services, schemas
    ↓
app/           ← Top level, orchestrates everything
```

### Module Dependencies

| Module | Can Depend On |
|--------|---------------|
| contracts | None (interface only) |
| core | contracts, enums |
| database | core, models |
| models | core, enums, contracts (interfaces only) |
| schemas | enums, contracts (interfaces only) |
| services | core, database, models, repositories |
| api | core, services, schemas |
| plugins | contracts, enums |

### Forbidden Patterns

- ✗ Models importing from services
- ✗ Core importing from api
- ✗ Database importing from plugins
- ✗ Circular imports between any modules
- ✗ Global mutable state (except singleton managers)

---

## Motivation

- **Maintainability:** Clear where to find code
- **Testability:** Easy to mock dependencies
- **Scalability:** Independent module evolution
- **Onboarding:** New developers understand structure

---

## Alternatives Considered

1. **No Rules:** Rejected - Leads to spaghetti dependencies
2. **Strict DI Container:** Rejected - Too complex for this project
3. **Monolithic:** Rejected - Limits scalability

---

## Trade-offs

| Positive | Negative |
|----------|----------|
| Clear structure | Import restrictions |
| Easy testing | Some forward references needed |
| Parallel development | Need discipline to enforce |
| Reduced coupling | Learning curve for new developers |

---

## Enforcement

1. Code review for dependency violations
2. Static analysis (import checks)
3. Architecture tests
4. Documentation of dependency rules

---

## Future Consequences

- **Positive:** Easy to understand codebase
- **Positive:** Safe to refactor within layers
- **Neutral:** May need occasional refactoring
- **Need:** Dependency visualization tool

---

## Implementation Notes

- Use relative imports within packages
- Use absolute imports between packages
- Follow PEP 8 for import ordering
- Keep imports at module level, not inside functions
