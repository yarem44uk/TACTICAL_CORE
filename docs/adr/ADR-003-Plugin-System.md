# ADR-003: Plugin System

**Date:** TASK-Sprint-004  
**Status:** Accepted  
**Deciders:** Architecture Team

---

## Context

Tactical Core must support extensibility through plugins. Plugins should be able to:
- Publish events to the system
- Subscribe to events from the system
- Provide additional processing logic
- Be developed independently from the core

---

## Decision

Implement plugin system based on contracts (interfaces):
1. All plugin functionality is defined through interfaces in `contracts/` package
2. Plugins implement these interfaces
3. The PluginManager handles plugin lifecycle
4. Plugins communicate only through the Event Engine

---

## Motivation

- **Separation of Concerns:** Core and plugins have clear boundaries
- **Version Compatibility:** Interface versioning allows core updates without breaking plugins
- **Security:** Plugins can be sandboxed if needed
- **Testing:** Plugins can be mocked for core testing
- **Development Speed:** Teams can work in parallel

---

## Alternatives Considered

1. **Direct Plugin Registration:** Rejected - Too coupled to core
2. **Scripting Language Plugins:** Rejected - Adds complexity, reduces type safety
3. **Shared Library Plugins:** Rejected - Version conflicts, loading issues

---

## Trade-offs

| Positive | Negative |
|----------|----------|
| Clean boundaries | Additional abstraction layer |
| Version compatibility | Interface maintenance overhead |
| Mockability | Plugin API versioning complexity |
| Sandbox capability | Performance for inter-process plugins |

---

## Future Consequences

- **Positive:** Third-party plugins can be developed independently
- **Positive:** Plugin marketplace becomes possible
- **Neutral:** Plugin SDK documentation required
- **Need:** Plugin versioning strategy

---

## Implementation Notes

- Plugin contracts in `app/contracts/plugin.py`
- PluginManager handles registration/lifecycle
- Plugins subscribe to events through IEventSubscriber
- Plugins publish through IEventPublisher
