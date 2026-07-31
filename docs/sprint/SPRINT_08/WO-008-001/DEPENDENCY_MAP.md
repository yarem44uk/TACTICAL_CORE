# WO-008-001 - DEPENDENCY MAP

**Work Order:** WO-008-001  
**Created:** 2026-07-27 13:08:45  
**Status:** COMPLETE

---

## 1. SUBSYSTEM DEPENDENCIES

### 1.1 Core Dependencies

EventBus -> EventDispatcher -> EventEngine
     ^
     EventContext

| Component | Depends On | Type |
|-----------|-----------|------|
| EventDispatcher | EventBus | Hard |
| EventEngine | EventDispatcher | Hard |
| EventEngine | EventContext | Hard |

### 1.2 Intelligence Dependencies

IntelligencePipeline
     - ObservationEngine
     - EntityManager
     - Core Pipeline

### 1.3 Plugin Dependencies

PluginManager
     - PluginRegistry
     - PluginLoader
     - PluginLifecycle
     - PluginSandbox

### 1.4 Database Dependencies

DatabaseManager
     - SessionManager
     - BaseModel
     - Migrations

## 2. EXTERNAL DEPENDENCIES

### 2.1 Python Standard Library

| Module | Usage |
|--------|-------|
| asyncio | Async operations |
| logging | Logging infrastructure |
| threading | Thread safety |
| queue | Event queuing |
| typing | Type hints |

### 2.2 Third-Party Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| fastapi | 0.x | Web framework |
| sqlalchemy | 2.x | ORM |
| pydantic | 2.x | Data validation |
| uvicorn | latest | ASGI server |
| alembic | latest | Migrations |

## 3. DEPENDENCY RULES

| Rule | Description | Enforcement |
|------|-------------|-------------|
| DR-01 | No direct module-to-module coupling | EventBus only |
| DR-02 | All inter-module communication via events | EventBus pattern |
| DR-03 | CF1/CF2 separation | Model vs Validator |
| DR-04 | Plugin isolation via sandbox | PluginSandbox |

## 4. PREVENTION RULES

1. EventBus NEVER imports EventEngine
2. Core NEVER imports PluginManager directly
3. All cross-subsystem calls via EventBus.publish()

## 5. SPRINT 08 DEPENDENCIES

| Component | Purpose | Dependencies |
|-----------|---------|--------------|
| MF1 | New integration | EventBus, ObservationEngine |
| MF2 | New integration | EventBus, PluginManager |

## 6. INTERFACE DEPENDENCY MATRIX

| Consumer to Producer | EventBus | ObsEngine | PluginManager |
|---------------------|----------|-----------|---------------|
| EventEngine | Uses | Uses | No |
| IntelligencePipeline | Uses | Uses | Uses |
| PluginStage | Uses | No | Uses |
| ObservationEngine | Publishes | Internal | No |
| API Routes | Uses | Uses | No |

*Document Status: COMPLETE*