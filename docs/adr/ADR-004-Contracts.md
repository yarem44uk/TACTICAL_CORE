# ADR-004: Contract Interfaces

**Date:** TASK-Sprint-004  
**Status:** Accepted  
**Deciders:** Architecture Team

---

## Context

The plugin system and internal modules need clear interfaces to communicate without depending on implementations.

---

## Decision

Create `app/contracts/` package with abstract base classes (ABCs) for all public interfaces:

| Interface | Purpose |
|-----------|---------|
| IPlugin, IPluginManager | Plugin lifecycle |
| IPluginContext | Plugin execution context |
| IPluginLifecycle | Start/stop hooks |
| IEventPublisher | Event publishing |
| IEventSubscriber | Event subscription |
| IEventBus | Event distribution |
| IEventPipeline | Pipeline management |
| IAudioSource, IAudioOutput | Audio handling |
| ITranscriber | Speech-to-text |
| IVoiceDetector | Voice activity detection |
| IMessageSource, IMessageOutput | Messaging |
| IStorage | File storage |
| IDatabase | Database operations |
| ILogger | Logging |
| IMetricsCollector | Metrics collection |
| IHealthChecker | Health checks |
| IConfigurationProvider | Configuration |
| IWebSocketBroadcaster | WebSocket |
| IEventHistory | Event history |
| IAIProcessor | AI processing |
| IMediaSource | Media sources |

---

## Motivation

- **Dependency Inversion:** High-level modules depend on abstractions
- **Mockability:** Easy to create mock implementations for testing
- **Documentation:** Clear API specification
- **Plugin Development:** Plugins know exactly what to implement

---

## Alternatives Considered

1. **Protocol Classes:** Rejected - Less explicit
2. **Type Hints Only:** Rejected - No enforcement
3. **Plugin Adapters:** Rejected - Adds complexity

---

## Trade-offs

| Positive | Negative |
|----------|----------|
| Clear API boundaries | More files to maintain |
| Type safety | Must keep interfaces updated |
| Easy mocking | Potential over-engineering |
| Self-documenting | Learning curve for contributors |

---

## Future Consequences

- **Positive:** Clear extension points for new modules
- **Positive:** IDE autocomplete for plugin developers
- **Neutral:** Interface changes require major version bump
- **Need:** Interface versioning strategy

---

## Implementation Notes

- All contracts use `ABC` from `abc` module
- Methods are decorated with `@abstractmethod`
- Optional methods have default implementations
- Contracts include docstrings for all methods
