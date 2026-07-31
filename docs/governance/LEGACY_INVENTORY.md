# LEGACY INVENTORY

**Generated:** 2026-07-27 10:19:43  
**Repository:** /mnt/uploads/TACTICAL_CORE/  
**Scope:** backend/app/

---

## 1. SUMMARY

| Category | Count |
|----------|-------|
| Total Modules | 140 |
| Legacy-Marked Modules | 0 |
| Orphan Modules (unused) | 140 |

---

## 2. LEGACY-MARKED MODULES

Modules explicitly marked as LEGACY or @deprecated.

| Module | Reason | Lines | Consumers |
|--------|--------|-------|----------|
| - | No legacy-marked modules found | - | - |


---

## 3. ORPHAN MODULES

Modules not imported by any other module (potential candidates for removal or integration).

| Module | Lines | Status | Recommendation |
|--------|-------|--------|----------------|
| `app.__init__` | 1 | UTIL | May be safe to remove |
| `app.api.__init__` | 1 | UTIL | May be safe to remove |
| `app.config.__init__` | 42 | UTIL | May be safe to remove |
| `app.config.ai` | 33 | UTIL | May be safe to remove |
| `app.config.database` | 48 | UTIL | May be safe to remove |
| `app.config.logging` | 42 | UTIL | May be safe to remove |
| `app.config.media` | 31 | UTIL | May be safe to remove |
| `app.config.mqtt` | 31 | UTIL | May be safe to remove |
| `app.config.pipeline` | 65 | INACTIVE | CSA decision required for removal |
| `app.config.plugins` | 29 | UTIL | May be safe to remove |
| `app.config.radio` | 33 | UTIL | May be safe to remove |
| `app.config.scheduler` | 27 | UTIL | May be safe to remove |
| `app.config.security` | 39 | UTIL | May be safe to remove |
| `app.config.settings` | 65 | INACTIVE | CSA decision required for removal |
| `app.config.signal` | 29 | UTIL | May be safe to remove |
| `app.config.storage` | 35 | UTIL | May be safe to remove |
| `app.config.websocket` | 25 | UTIL | May be safe to remove |
| `app.contracts.__init__` | 42 | UTIL | May be safe to remove |
| `app.contracts.audio` | 138 | INACTIVE | CSA decision required for removal |
| `app.contracts.configuration` | 43 | UTIL | May be safe to remove |
| `app.contracts.event` | 105 | INACTIVE | CSA decision required for removal |
| `app.contracts.messaging` | 62 | INACTIVE | CSA decision required for removal |
| `app.contracts.monitoring` | 131 | INACTIVE | CSA decision required for removal |
| `app.contracts.plugin` | 109 | INACTIVE | CSA decision required for removal |
| `app.contracts.storage` | 52 | INACTIVE | CSA decision required for removal |
| `app.core.__init__` | 121 | INACTIVE | CSA decision required for removal |
| `app.core.event_bus` | 577 | INACTIVE | CSA decision required for removal |
| `app.core.event_context` | 329 | INACTIVE | CSA decision required for removal |
| `app.core.event_dispatcher` | 514 | INACTIVE | CSA decision required for removal |
| `app.core.event_engine` | 270 | INACTIVE | CSA decision required for removal |


---

## 4. MIGRATION STATUS

| Module | Current State | Action Required |
|--------|---------------|-----------------|
| `app.config.pipeline` | Unused | CSA decision required |


---

## 5. REMOVAL ANALYSIS

### Can Be Removed (No Consumers, < 50 lines)

```
- app.__init__ (1 lines)
- app.api.__init__ (1 lines)
- app.config.__init__ (42 lines)
- app.config.ai (33 lines)
- app.config.database (48 lines)
- app.config.logging (42 lines)
- app.config.media (31 lines)
- app.config.mqtt (31 lines)
- app.config.plugins (29 lines)
- app.config.radio (33 lines)
- app.config.scheduler (27 lines)
- app.config.security (39 lines)
- app.config.signal (29 lines)
- app.config.storage (35 lines)
- app.config.websocket (25 lines)
- app.contracts.__init__ (42 lines)
- app.contracts.configuration (43 lines)
- app.core.health.__init__ (25 lines)
- app.core.health.component (42 lines)
- app.core.metrics.__init__ (20 lines)
- app.core.metrics.counter (41 lines)
- app.core.middleware.__init__ (23 lines)
- app.core.pipeline.__init__ (27 lines)
- app.core.pipeline.ai_stage (48 lines)
- app.core.pipeline.broadcast_stage (41 lines)
- app.core.pipeline.enrichment_stage (49 lines)
- app.core.pipeline.plugin_stage (47 lines)
- app.database.repositories.__init__ (26 lines)
- app.enums.__init__ (1 lines)
- app.intelligence.entity.__init__ (28 lines)
- app.intelligence.event_bus.__init__ (24 lines)
- app.intelligence.knowledge.__init__ (31 lines)
- app.intelligence.pipeline.stages.__init__ (24 lines)
- app.intelligence.timeline.__init__ (29 lines)
- app.models.__init__ (1 lines)
- app.plugins.__init__ (18 lines)
- app.plugins.discovery.__init__ (1 lines)
- app.plugins.hotreload.__init__ (1 lines)
- app.plugins.lifecycle.__init__ (1 lines)
- app.plugins.loader.__init__ (1 lines)
- app.plugins.manager.__init__ (14 lines)
- app.plugins.manifest.__init__ (1 lines)
- app.plugins.permissions.__init__ (1 lines)
- app.plugins.registry.__init__ (1 lines)
- app.plugins.sandbox.__init__ (1 lines)
- app.plugins.sdk.__init__ (35 lines)
- app.plugins.templates.example_plugin.__init__ (1 lines)
- app.plugins.validator.__init__ (1 lines)
- app.schemas.__init__ (1 lines)
- app.services.__init__ (1 lines)
- app.utils.__init__ (1 lines)
- app.websocket.__init__ (1 lines)
```

### Requires CSA Decision (> 50 lines)

```
- app.config.pipeline (65 lines)
- app.config.settings (65 lines)
- app.contracts.audio (138 lines)
- app.contracts.event (105 lines)
- app.contracts.messaging (62 lines)
- app.contracts.monitoring (131 lines)
- app.contracts.plugin (109 lines)
- app.contracts.storage (52 lines)
- app.core.__init__ (121 lines)
- app.core.event_bus (577 lines)
- app.core.event_context (329 lines)
- app.core.event_dispatcher (514 lines)
- app.core.event_engine (270 lines)
- app.core.event_exceptions (398 lines)
- app.core.event_history (531 lines)
- app.core.event_hooks (502 lines)
- app.core.event_registry (577 lines)
- app.core.event_result (267 lines)
- app.core.health.checkers (132 lines)
- app.core.health.health (192 lines)
- app.core.health.manager (129 lines)
- app.core.metrics.collector (112 lines)
- app.core.metrics.metrics (209 lines)
- app.core.metrics.timer (63 lines)
- app.core.middleware.base (145 lines)
- app.core.pipeline.base_stage (152 lines)
- app.core.pipeline.context (138 lines)
- app.core.pipeline.dispatch_stage (57 lines)
- app.core.pipeline.history_stage (52 lines)
- app.core.pipeline.persistence_stage (55 lines)
- app.core.pipeline.pipeline (335 lines)
- app.core.pipeline.stage_result (191 lines)
- app.core.pipeline.validation_stage (77 lines)
- app.database.__init__ (80 lines)
- app.database.base (182 lines)
- app.database.database (390 lines)
- app.database.dependencies (204 lines)
- app.database.migration (533 lines)
- app.database.session (377 lines)
- app.database.repositories.base_repository (771 lines)
- app.intelligence.entity.entity (285 lines)
- app.intelligence.entity.entity_manager (379 lines)
- app.intelligence.entity.identity (303 lines)
- app.intelligence.entity.relations (178 lines)
- app.intelligence.entity.types (88 lines)
- app.intelligence.event_bus.intelligence_bus (379 lines)
- app.intelligence.event_bus.patterns (398 lines)
- app.intelligence.event_bus.routing (328 lines)
- app.intelligence.event_bus.subscriptions (353 lines)
- app.intelligence.observation.__init__ (139 lines)
- app.intelligence.observation.engine (372 lines)
- app.intelligence.observation.events (289 lines)
- app.intelligence.observation.model (222 lines)
- app.intelligence.observation.repository (258 lines)
- app.intelligence.observation.schema (232 lines)
- app.intelligence.observation.types (147 lines)
- app.intelligence.observation.validation_framework (674 lines)
- app.intelligence.observation.validator (270 lines)
- app.intelligence.pipeline.__init__ (107 lines)
- app.intelligence.pipeline.base_stage (165 lines)
- app.intelligence.pipeline.context (179 lines)
- app.intelligence.pipeline.event_processor (252 lines)
- app.intelligence.pipeline.exceptions (144 lines)
- app.intelligence.pipeline.intelligence_pipeline (380 lines)
- app.intelligence.pipeline.observation_integration (300 lines)
- app.intelligence.pipeline.observation_stage (294 lines)
- app.intelligence.pipeline.pipeline (314 lines)
- app.intelligence.pipeline.queue_processor (385 lines)
- app.intelligence.pipeline.registry (177 lines)
- app.intelligence.pipeline.stages (277 lines)
- app.intelligence.pipeline.stages.classification_stage (140 lines)
- app.intelligence.pipeline.stages.enrichment_stage (175 lines)
- app.intelligence.pipeline.stages.normalization_stage (90 lines)
- app.intelligence.pipeline.stages.persistence_stage (126 lines)
- app.intelligence.pipeline.stages.publisher_stage (191 lines)
- app.intelligence.pipeline.stages.validation_stage (117 lines)
- app.intelligence.timeline.aggregation (170 lines)
- app.intelligence.timeline.event_store (173 lines)
- app.intelligence.timeline.projections (148 lines)
- app.intelligence.timeline.queries (126 lines)
- app.intelligence.timeline.timeline (180 lines)
- app.plugins.signal_reference_plugin (340 lines)
- app.plugins.exceptions.__init__ (102 lines)
- app.plugins.manager.plugin_manager (365 lines)
- app.plugins.sdk.base (246 lines)
- app.plugins.sdk.capabilities (91 lines)
- app.plugins.sdk.context (69 lines)
- app.plugins.sdk.manifest (93 lines)
```

---

## 6. RECOMMENDATIONS

1. **Legacy modules with active consumers**: Document migration paths before removal
2. **Orphan modules**: Evaluate if they should be integrated or removed
3. **Large orphan files (>50 lines)**: Require CSA decision before action

---

*Generated by Senior Software Engineer per WO-007-MAINTENANCE*
