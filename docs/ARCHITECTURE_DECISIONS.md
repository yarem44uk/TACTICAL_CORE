# Architecture Decisions
## Tactical Core v1.0

---

## ADR-001: Event-Driven Architecture

**Date:** Initial Design  
**Status:** Accepted

### Decision

All modules communicate ONLY through the Event Engine. No direct module-to-module coupling is allowed.

### Context

Tactical Core must support multiple input sources (Radio, Signal, Camera, REST API, plugins) and multiple output destinations (Dashboard, AI, Plugins, external systems). Direct coupling between modules would create a complex web of dependencies.

### Decision

Implement Event-Driven Architecture where every module publishes events to the Event Engine, and the Event Engine distributes events to interested subscribers.

### Consequences

- **Positive:** Loose coupling, extensibility, easy testing, clear data flow
- **Negative:** Additional latency, complexity in tracing, eventual consistency

### Trade-offs

Event processing adds latency but enables parallel development and independent scaling.

---

## ADR-002: Pipeline Architecture for Event Processing

**Date:** TASK-003.5  
**Status:** Accepted

### Decision

Event processing is organized into a configurable pipeline of processing stages.

### Context

The original EventEngine contained all business logic in a single method (147 lines). This violated Single Responsibility Principle and made testing difficult.

### Decision

Split event processing into independent stages:
- ValidationStage
- EnrichmentStage
- PersistenceStage
- HistoryStage
- BroadcastStage
- DispatchStage
- AIStage
- PluginStage

Each stage inherits from BaseStage and implements a single `_execute()` method.

### Consequences

- **Positive:** Testable stages, configurable pipeline, easy to add/remove stages
- **Negative:** Additional abstraction overhead, potential performance impact

### Trade-offs

Minor performance overhead is acceptable for improved maintainability and testability.

---

## ADR-003: Repository Pattern for Data Access

**Date:** TASK-002  
**Status:** Accepted

### Decision

All database access goes through repository classes using the Repository Pattern.

### Context

SQLAlchemy ORM directly in services would create tight coupling to the database layer.

### Decision

Implement BaseRepository with generic CRUD operations. Specific repositories (EventRepository) inherit from BaseRepository.

### Consequences

- **Positive:** Testable with mocks, database-agnostic service layer, clean separation
- **Negative:** Additional abstraction layer, potential query complexity

---

## ADR-004: Contract Interfaces for Plugin System

**Date:** TASK-Refactor  
**Status:** Accepted

### Decision

All plugin interfaces are defined in a dedicated `contracts/` package.

### Context

Plugins should not depend on internal implementation details. Only contract interfaces should be used.

### Decision

Create `contracts/` package with interfaces:
- IPlugin, IPluginManager
- IEventPublisher, IEventSubscriber
- IAudioSource, IAudioSink, ITranscriber
- IMessageSource, IMessageSink
- IStorage
- IHealthCheck, IMetricsCollector, ILogger
- IConfigurationProvider

### Consequences

- **Positive:** Clear plugin API, independent development, version compatibility
- **Negative:** Additional abstraction layer

---

## ADR-005: Modular Configuration Management

**Date:** TASK-Refactor  
**Status:** Accepted

### Decision

Configuration is split into logical modules instead of a single config file.

### Context

A single config.py file with 50+ settings becomes difficult to maintain.

### Decision

Create `config/` package with modules:
- settings.py (main settings)
- database.py
- storage.py
- security.py
- logging.py
- pipeline.py

### Consequences

- **Positive:** Organized configuration, easier maintenance, type safety per module
- **Negative:** More files to manage

---

## ADR-006: Health Monitoring System

**Date:** TASK-003.5  
**Status:** Accepted

### Decision

System health is monitored through a centralized HealthManager with component-level status.

### Context

Need to track health of multiple components (database, pipeline, plugins, storage) for operational awareness.

### Decision

HealthManager tracks ComponentHealth objects with status levels (HEALTHY, WARNING, CRITICAL, OFFLINE). Specific checkers (DatabaseHealthChecker, PipelineHealthChecker) provide component status.

### Consequences

- **Positive:** Centralized health monitoring, clear status reporting
- **Negative:** Additional complexity in health tracking

---

## ADR-007: Metrics Collection System

**Date:** TASK-003.5  
**Status:** Accepted

### Decision

Metrics are collected through a centralized MetricsCollector.

### Context

Need to track performance metrics (events/sec, latency, error rates) for monitoring and optimization.

### Decision

MetricsCollector provides counters, timers, and gauges. Metrics are aggregated in-memory for summary reporting.

### Consequences

- **Positive:** Performance visibility, easy to add new metrics
- **Negative:** In-memory storage (not persistent), needs external system for long-term storage

---

## ADR-008: SQLite for Development, PostgreSQL Ready

**Date:** TASK-002  
**Status:** Accepted

### Decision

Initial deployment uses SQLite, designed for PostgreSQL migration.

### Context

Development environment needs simple setup without database server dependencies.

### Decision

SQLAlchemy with generic types, UUID as String(36), no SQLite-specific SQL. Connection string easily swappable.

### Consequences

- **Positive:** Easy development setup, clear migration path
- **Negative:** SQLite limitations for production scale

---

## Future Architecture Decisions

### Planned: Async Database Support

Currently using synchronous SQLAlchemy. Future: Add async session support for high-scale deployments.

### Planned: Distributed Event Bus

Currently in-memory EventBus. Future: Kafka, RabbitMQ, or Redis Streams for distributed deployment.

### Planned: Plugin Sandbox

Future plugins may need isolation for security. Consider containerization or restricted execution environment.

---

*Document Version: 1.0*
*Last Updated: Current*
