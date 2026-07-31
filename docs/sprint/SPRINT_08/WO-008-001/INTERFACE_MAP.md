# WO-008-001 — INTERFACE MAP

**Work Order:** WO-008-001  
**Created:** 2026-07-27 13:07:52  
**Status:** COMPLETE

---

## 1. STABLE INTERFACES (MUST REMAIN STABLE)

These interfaces are locked and MUST NOT be modified during Sprint 08:

### 1.1 Event Bus Interface

```python
class IEventBus(Protocol):
    def publish(event_type: str, event: Any, context: EventContext) -> None
    def subscribe(event_types: Set[str], handler: Callable, subscriber_id: str) -> str
    def unsubscribe(subscription_id: str) -> None
    def get_subscriptions(event_type: str) -> List[Subscription]
```

### 1.2 Event Context Interface

```python
class EventContext:
    id: str
    timestamp: datetime
    source: str
    metadata: Dict[str, Any]
```

### 1.3 Observation Engine Interface

```python
class IObservationEngine(Protocol):
    def receive(raw_event: Dict) -> Observation
    def validate(observation: Observation) -> bool
    def store(observation: Observation, db: Session) -> Observation
    def forward(observation: Observation) -> None
```

### 1.4 Plugin Interface

```python
class IPlugin(Protocol):
    @property
    def manifest() -> PluginManifest
    def initialize(context: PluginContext) -> None
    def start() -> None
    def stop() -> None
```

---

## 2. INTERNAL INTERFACES

### 2.1 Pipeline Stages

```python
class IStage(Protocol):
    async def execute(context: PipelineContext) -> StageResult
    @property
    def stage_type() -> StageType
```

### 2.2 Entity Interface

```python
class IEntity(Protocol):
    @property
    def id() -> UUID
    @property
    def entity_type() -> EntityType
    @property
    def identity() -> Identity
```

---

## 3. INTERFACE DEPENDENCIES

```
┌─────────────────────────────────────────────────────────────┐
│                     Web API Layer                          │
│  REST Routes + WebSocket                                   │
└──────────────────┬────────────────────────────────────────┘
                   │
┌──────────────────▼────────────────────────────────────────┐
│                  Service Layer                            │
│  ObservationEngine │ EventEngine │ PluginManager           │
└──────────────────┬────────────────────────────────────────┘
                   │
┌──────────────────▼────────────────────────────────────────┐
│                  Core Layer                              │
│  EventBus │ Pipeline │ EventDispatcher                  │
└──────────────────┬────────────────────────────────────────┘
                   │
┌──────────────────▼────────────────────────────────────────┐
│                  Data Layer                             │
│  Database │ EventRepository │ EntityRepository           │
└─────────────────────────────────────────────────────────────┘
```

---

## 4. INTEGRATION POINTS

### 4.1 Event Bus → Event Engine

| From | To | Method |
|------|-----|--------|
| EventBus | EventEngine | `event_bus.publish()` → `engine.process()` |

### 4.2 Event Engine → Observation Engine

| From | To | Method |
|------|-----|--------|
| EventEngine | ObservationEngine | `engine.receive()` |

### 4.3 Plugin Manager → Event Bus

| From | To | Method |
|------|-----|--------|
| PluginManager | EventBus | `manager.set_event_bus()` |

### 4.4 Pipeline → Plugins

| From | To | Method |
|------|-----|--------|
| Pipeline | PluginStage | `stage.execute()` → `plugin.process()` |

---

## 5. MESSAGE FLOWS

### 5.1 Event Processing Flow

```
External Event
    ↓
REST API / WebSocket
    ↓
Event Engine (validation)
    ↓
Event Bus (publish)
    ↓
EventDispatcher (routing)
    ↓
┌─────────┴─────────┐
↓                   ↓
Pipeline          Plugin
    ↓                   ↓
Observation      Event Handler
Engine
    ↓
Database (persist)
```

### 5.2 Observation Flow

```
Raw Intelligence Event
    ↓
ObservationEngine.receive()
    ↓
ObservationValidator (CF2)
    ↓
ObservationRepository (store)
    ↓
ObservationStoredEvent (emit)
    ↓
Pipeline (enrich)
    ↓
EntityManager (link)
```

---

## 6. CONTRACT INTERFACES

### 6.1 Plugin Contracts

| File | Interface | Purpose |
|------|----------|---------|
| `backend/app/contracts/plugin.py` | `IPlugin` | Plugin contract |
| `backend/app/contracts/plugin.py` | `IPluginManager` | Manager contract |

---

## 7. INTERFACE STABILITY RULES

| Interface | Stability | Modification Allowed |
|-----------|----------|-------------------|
| IEventBus | HIGH | NO |
| IEventContext | HIGH | NO |
| IObservationEngine | HIGH | NO |
| IPlugin | MEDIUM | Extensions only |
| IStage | MEDIUM | Extensions only |

---

*Document Status: COMPLETE*
