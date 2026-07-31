# WO-008-001 — ENTRY POINTS

**Work Order:** WO-008-001  
**Created:** 2026-07-27 13:07:35  
**Status:** COMPLETE

---

## 1. APPLICATION ENTRY POINTS

### 1.1 FastAPI Application

**Discovery:** Pattern-based search in codebase

| File | Pattern Matched | Purpose |
|------|-----------------|---------|
| `backend/app/database/dependencies.py` | `@app.get/post/etc` | FastAPI app definition |

**Status:** Entry point discovered in dependencies.py

---

### 1.2 Database Entry Points

| File | Function | Purpose |
|------|---------|---------|
| `backend/app/database/session.py` | `get_session_local()` | Session management |
| `backend/app/database/session.py` | `get_session_manager()` | Manager retrieval |
| `backend/app/database/dependencies.py` | `get_db()` | FastAPI dependency injection |

---

## 2. SERVICE ENTRY POINTS

### 2.1 Event Bus Entry

| File | Class | Method |
|------|-------|--------|
| `backend/app/core/event_bus.py` | `EventBus` | `publish()` |

**Usage:**
```python
from app.core.event_bus import EventBus
from app.core.event_context import EventContext

event_bus = EventBus()
event_bus.publish("event.type", event_data, context)
```

---

### 2.2 Event Engine Entry

| File | Class | Method |
|------|-------|--------|
| `backend/app/core/event_engine.py` | `EventEngine` | `process()` |

**Purpose:** High-level event processing orchestration

---

### 2.3 Observation Engine Entry

| File | Class | Method |
|------|-------|--------|
| `backend/app/intelligence/observation/engine.py` | `ObservationEngine` | `receive()` |

**Usage:**
```python
from app.intelligence.observation.engine import ObservationEngine

engine = ObservationEngine(db_session)
observation = engine.receive(raw_event)
```

---

## 3. PLUGIN ENTRY POINTS

### 3.1 Plugin Manager

| File | Class | Method |
|------|-------|--------|
| `backend/app/plugins/manager/plugin_manager.py` | `PluginManager` | `initialize()` |

**Lifecycle Entry:**
```python
manager = PluginManager()
manager.initialize()
manager.register_plugin(plugin)
manager.start_all()
```

---

### 3.2 Plugin SDK

| File | Class | Purpose |
|------|-------|---------|
| `backend/app/plugins/sdk/base.py` | `PluginBase` | Plugin base class |
| `backend/app/plugins/sdk/context.py` | `PluginContext` | Plugin execution context |
| `backend/app/plugins/sdk/manifest.py` | `PluginManifest` | Plugin metadata |

---

## 4. PIPELINE ENTRY POINTS

### 4.1 Intelligence Pipeline

| File | Class | Method |
|------|-------|--------|
| `backend/app/intelligence/pipeline/intelligence_pipeline.py` | `IntelligencePipeline` | `process()` |

**Usage:**
```python
pipeline = IntelligencePipeline(config)
result = await pipeline.process(event, context)
```

---

### 4.2 Core Pipeline

| File | Class | Method |
|------|-------|--------|
| `backend/app/core/pipeline/pipeline.py` | `Pipeline` | `execute()` |

**Stage-based processing**

---

## 5. WEB API ENTRY POINTS

### 5.1 REST API Routes

**Pattern:** FastAPI routers

| Location | Purpose |
|----------|---------|
| `backend/app/api/` | API route definitions |

---

### 5.2 WebSocket Entry

| Location | Purpose |
|----------|---------|
| `backend/app/websocket/` | WebSocket event streaming |

---

## 6. DATABASE ENTRY POINTS

### 6.1 Session Management

| File | Function | Purpose |
|------|---------|---------|
| `backend/app/database/session.py` | `get_session_local()` | Get local session manager |
| `backend/app/database/session.py` | `get_database_manager()` | Get DB manager singleton |

---

## 7. INITIALIZATION FLOW

```
Application Startup
        ↓
1. Load Configuration
        ↓
2. Initialize Database
        ↓
3. Create Event Bus
        ↓
4. Create Event Engine
        ↓
5. Initialize Plugin Manager
        ↓
6. Load Plugins
        ↓
7. Initialize Intelligence Pipeline
        ↓
8. Start WebSocket Server
        ↓
Application Running
```

---

## 8. DEPENDENCY INJECTION

### FastAPI Dependencies

| Function | Provides |
|----------|----------|
| `get_db()` | SQLAlchemy Session |
| `get_event_bus()` | EventBus instance |
| `get_observation_engine()` | ObservationEngine instance |

---

*Document Status: COMPLETE*
