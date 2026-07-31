# MODULE DEPENDENCY GRAPH

**Generated:** 2026-07-27 10:19:21  
**Repository:** /mnt/uploads/TACTICAL_CORE/  
**Scope:** backend/app/

---

## 1. SUMMARY

| Metric | Value |
|--------|-------|
| Total Modules | 140 |
| Entry Points (>5 dependencies) | 0 |
| Core Modules (>2 dependents) | 0 |
| External Dependencies | 0 |

---

## 2. ENTRY POINTS (High Import Count)

Entry points are modules that import many other modules - typically orchestrators or coordinators.

| Module | Imports | Imported By |
|--------|---------|------------|


---

## 3. CORE MODULES (High Dependents Count)

Core modules are heavily depended upon by other modules.

| Module | Dependents | Imports |
|--------|------------|---------|


---

## 4. EXTERNAL DEPENDENCIES

| Package | Usage Count |
|---------|-------------|


---

## 5. PACKAGE-LEVEL DEPENDENCIES

| Package | Modules | Internal Dependencies |
|---------|---------|---------------------|
| `app.core` | 35 | 130 |
| `app.api` | 1 | 3 |
| `app.services` | 1 | 3 |
| `app.models` | 1 | 3 |
| `app.schemas` | 1 | 3 |
| `app.plugins` | 20 | 79 |
| `app.events` | 0 | 0 |


---

## 6. GRAPH VISUALIZATION

```
TYPICAL DEPENDENCY PATTERN:

    [API Routes] → [Services] → [Models/Schemas]
         ↓              ↓              ↓
    [Core/Utils] ←── [Event Service] ←── [Plugins]
```

---

## 7. CIRCULAR DEPENDENCY CHECK

**Status:** NO CIRCULAR DEPENDENCIES DETECTED

---

## 8. MODULE LIST

| Module | File | Dependents |
|--------|------|------------|
| `app.__init__` | `app/__init__.py` | 0 |
| `app.api.__init__` | `app/api/__init__.py` | 0 |
| `app.config.__init__` | `app/config/__init__.py` | 0 |
| `app.config.ai` | `app/config/ai.py` | 0 |
| `app.config.database` | `app/config/database.py` | 0 |
| `app.config.logging` | `app/config/logging.py` | 0 |
| `app.config.media` | `app/config/media.py` | 0 |
| `app.config.mqtt` | `app/config/mqtt.py` | 0 |
| `app.config.pipeline` | `app/config/pipeline.py` | 0 |
| `app.config.plugins` | `app/config/plugins.py` | 0 |
| `app.config.radio` | `app/config/radio.py` | 0 |
| `app.config.scheduler` | `app/config/scheduler.py` | 0 |
| `app.config.security` | `app/config/security.py` | 0 |
| `app.config.settings` | `app/config/settings.py` | 0 |
| `app.config.signal` | `app/config/signal.py` | 0 |
| `app.config.storage` | `app/config/storage.py` | 0 |
| `app.config.websocket` | `app/config/websocket.py` | 0 |
| `app.contracts.__init__` | `app/contracts/__init__.py` | 0 |
| `app.contracts.audio` | `app/contracts/audio.py` | 0 |
| `app.contracts.configuration` | `app/contracts/configuration.py` | 0 |
| `app.contracts.event` | `app/contracts/event.py` | 0 |
| `app.contracts.messaging` | `app/contracts/messaging.py` | 0 |
| `app.contracts.monitoring` | `app/contracts/monitoring.py` | 0 |
| `app.contracts.plugin` | `app/contracts/plugin.py` | 0 |
| `app.contracts.storage` | `app/contracts/storage.py` | 0 |
| `app.core.__init__` | `app/core/__init__.py` | 0 |
| `app.core.event_bus` | `app/core/event_bus.py` | 0 |
| `app.core.event_context` | `app/core/event_context.py` | 0 |
| `app.core.event_dispatcher` | `app/core/event_dispatcher.py` | 0 |
| `app.core.event_engine` | `app/core/event_engine.py` | 0 |
| `app.core.event_exceptions` | `app/core/event_exceptions.py` | 0 |
| `app.core.event_history` | `app/core/event_history.py` | 0 |
| `app.core.event_hooks` | `app/core/event_hooks.py` | 0 |
| `app.core.event_registry` | `app/core/event_registry.py` | 0 |
| `app.core.event_result` | `app/core/event_result.py` | 0 |
| `app.core.health.__init__` | `app/core/health/__init__.py` | 0 |
| `app.core.health.checkers` | `app/core/health/checkers.py` | 0 |
| `app.core.health.component` | `app/core/health/component.py` | 0 |
| `app.core.health.health` | `app/core/health/health.py` | 0 |
| `app.core.health.manager` | `app/core/health/manager.py` | 0 |
| `app.core.metrics.__init__` | `app/core/metrics/__init__.py` | 0 |
| `app.core.metrics.collector` | `app/core/metrics/collector.py` | 0 |
| `app.core.metrics.counter` | `app/core/metrics/counter.py` | 0 |
| `app.core.metrics.metrics` | `app/core/metrics/metrics.py` | 0 |
| `app.core.metrics.timer` | `app/core/metrics/timer.py` | 0 |
| `app.core.middleware.__init__` | `app/core/middleware/__init__.py` | 0 |
| `app.core.middleware.base` | `app/core/middleware/base.py` | 0 |
| `app.core.pipeline.__init__` | `app/core/pipeline/__init__.py` | 0 |
| `app.core.pipeline.ai_stage` | `app/core/pipeline/ai_stage.py` | 0 |
| `app.core.pipeline.base_stage` | `app/core/pipeline/base_stage.py` | 0 |
| `app.core.pipeline.broadcast_stage` | `app/core/pipeline/broadcast_stage.py` | 0 |
| `app.core.pipeline.context` | `app/core/pipeline/context.py` | 0 |
| `app.core.pipeline.dispatch_stage` | `app/core/pipeline/dispatch_stage.py` | 0 |
| `app.core.pipeline.enrichment_stage` | `app/core/pipeline/enrichment_stage.py` | 0 |
| `app.core.pipeline.history_stage` | `app/core/pipeline/history_stage.py` | 0 |
| `app.core.pipeline.persistence_stage` | `app/core/pipeline/persistence_stage.py` | 0 |
| `app.core.pipeline.pipeline` | `app/core/pipeline/pipeline.py` | 0 |
| `app.core.pipeline.plugin_stage` | `app/core/pipeline/plugin_stage.py` | 0 |
| `app.core.pipeline.stage_result` | `app/core/pipeline/stage_result.py` | 0 |
| `app.core.pipeline.validation_stage` | `app/core/pipeline/validation_stage.py` | 0 |
| `app.database.__init__` | `app/database/__init__.py` | 0 |
| `app.database.base` | `app/database/base.py` | 0 |
| `app.database.database` | `app/database/database.py` | 0 |
| `app.database.dependencies` | `app/database/dependencies.py` | 0 |
| `app.database.migration` | `app/database/migration.py` | 0 |
| `app.database.repositories.__init__` | `app/database/repositories/__init__.py` | 0 |
| `app.database.repositories.base_repository` | `app/database/repositories/base_repository.py` | 0 |
| `app.database.session` | `app/database/session.py` | 0 |
| `app.enums.__init__` | `app/enums/__init__.py` | 0 |
| `app.intelligence.entity.__init__` | `app/intelligence/entity/__init__.py` | 0 |
| `app.intelligence.entity.entity` | `app/intelligence/entity/entity.py` | 0 |
| `app.intelligence.entity.entity_manager` | `app/intelligence/entity/entity_manager.py` | 0 |
| `app.intelligence.entity.identity` | `app/intelligence/entity/identity.py` | 0 |
| `app.intelligence.entity.relations` | `app/intelligence/entity/relations.py` | 0 |
| `app.intelligence.entity.types` | `app/intelligence/entity/types.py` | 0 |
| `app.intelligence.event_bus.__init__` | `app/intelligence/event_bus/__init__.py` | 0 |
| `app.intelligence.event_bus.intelligence_bus` | `app/intelligence/event_bus/intelligence_bus.py` | 0 |
| `app.intelligence.event_bus.patterns` | `app/intelligence/event_bus/patterns.py` | 0 |
| `app.intelligence.event_bus.routing` | `app/intelligence/event_bus/routing.py` | 0 |
| `app.intelligence.event_bus.subscriptions` | `app/intelligence/event_bus/subscriptions.py` | 0 |
| `app.intelligence.knowledge.__init__` | `app/intelligence/knowledge/__init__.py` | 0 |
| `app.intelligence.observation.__init__` | `app/intelligence/observation/__init__.py` | 0 |
| `app.intelligence.observation.engine` | `app/intelligence/observation/engine.py` | 0 |
| `app.intelligence.observation.events` | `app/intelligence/observation/events.py` | 0 |
| `app.intelligence.observation.model` | `app/intelligence/observation/model.py` | 0 |
| `app.intelligence.observation.repository` | `app/intelligence/observation/repository.py` | 0 |
| `app.intelligence.observation.schema` | `app/intelligence/observation/schema.py` | 0 |
| `app.intelligence.observation.types` | `app/intelligence/observation/types.py` | 0 |
| `app.intelligence.observation.validation_framework` | `app/intelligence/observation/validation_framework.py` | 0 |
| `app.intelligence.observation.validator` | `app/intelligence/observation/validator.py` | 0 |
| `app.intelligence.pipeline.__init__` | `app/intelligence/pipeline/__init__.py` | 0 |
| `app.intelligence.pipeline.base_stage` | `app/intelligence/pipeline/base_stage.py` | 0 |
| `app.intelligence.pipeline.context` | `app/intelligence/pipeline/context.py` | 0 |
| `app.intelligence.pipeline.event_processor` | `app/intelligence/pipeline/event_processor.py` | 0 |
| `app.intelligence.pipeline.exceptions` | `app/intelligence/pipeline/exceptions.py` | 0 |
| `app.intelligence.pipeline.intelligence_pipeline` | `app/intelligence/pipeline/intelligence_pipeline.py` | 0 |
| `app.intelligence.pipeline.observation_integration` | `app/intelligence/pipeline/observation_integration.py` | 0 |
| `app.intelligence.pipeline.observation_stage` | `app/intelligence/pipeline/observation_stage.py` | 0 |
| `app.intelligence.pipeline.pipeline` | `app/intelligence/pipeline/pipeline.py` | 0 |
| `app.intelligence.pipeline.queue_processor` | `app/intelligence/pipeline/queue_processor.py` | 0 |
| `app.intelligence.pipeline.registry` | `app/intelligence/pipeline/registry.py` | 0 |
| `app.intelligence.pipeline.stages` | `app/intelligence/pipeline/stages.py` | 0 |
| `app.intelligence.pipeline.stages.__init__` | `app/intelligence/pipeline/stages/__init__.py` | 0 |
| `app.intelligence.pipeline.stages.classification_stage` | `app/intelligence/pipeline/stages/classification_stage.py` | 0 |
| `app.intelligence.pipeline.stages.enrichment_stage` | `app/intelligence/pipeline/stages/enrichment_stage.py` | 0 |
| `app.intelligence.pipeline.stages.normalization_stage` | `app/intelligence/pipeline/stages/normalization_stage.py` | 0 |
| `app.intelligence.pipeline.stages.persistence_stage` | `app/intelligence/pipeline/stages/persistence_stage.py` | 0 |
| `app.intelligence.pipeline.stages.publisher_stage` | `app/intelligence/pipeline/stages/publisher_stage.py` | 0 |
| `app.intelligence.pipeline.stages.validation_stage` | `app/intelligence/pipeline/stages/validation_stage.py` | 0 |
| `app.intelligence.timeline.__init__` | `app/intelligence/timeline/__init__.py` | 0 |
| `app.intelligence.timeline.aggregation` | `app/intelligence/timeline/aggregation.py` | 0 |
| `app.intelligence.timeline.event_store` | `app/intelligence/timeline/event_store.py` | 0 |
| `app.intelligence.timeline.projections` | `app/intelligence/timeline/projections.py` | 0 |
| `app.intelligence.timeline.queries` | `app/intelligence/timeline/queries.py` | 0 |
| `app.intelligence.timeline.timeline` | `app/intelligence/timeline/timeline.py` | 0 |
| `app.models.__init__` | `app/models/__init__.py` | 0 |
| `app.plugins.__init__` | `app/plugins/__init__.py` | 0 |
| `app.plugins.discovery.__init__` | `app/plugins/discovery/__init__.py` | 0 |
| `app.plugins.exceptions.__init__` | `app/plugins/exceptions/__init__.py` | 0 |
| `app.plugins.hotreload.__init__` | `app/plugins/hotreload/__init__.py` | 0 |
| `app.plugins.lifecycle.__init__` | `app/plugins/lifecycle/__init__.py` | 0 |
| `app.plugins.loader.__init__` | `app/plugins/loader/__init__.py` | 0 |
| `app.plugins.manager.__init__` | `app/plugins/manager/__init__.py` | 0 |
| `app.plugins.manager.plugin_manager` | `app/plugins/manager/plugin_manager.py` | 0 |
| `app.plugins.manifest.__init__` | `app/plugins/manifest/__init__.py` | 0 |
| `app.plugins.permissions.__init__` | `app/plugins/permissions/__init__.py` | 0 |
| `app.plugins.registry.__init__` | `app/plugins/registry/__init__.py` | 0 |
| `app.plugins.sandbox.__init__` | `app/plugins/sandbox/__init__.py` | 0 |
| `app.plugins.sdk.__init__` | `app/plugins/sdk/__init__.py` | 0 |
| `app.plugins.sdk.base` | `app/plugins/sdk/base.py` | 0 |
| `app.plugins.sdk.capabilities` | `app/plugins/sdk/capabilities.py` | 0 |
| `app.plugins.sdk.context` | `app/plugins/sdk/context.py` | 0 |
| `app.plugins.sdk.manifest` | `app/plugins/sdk/manifest.py` | 0 |
| `app.plugins.signal_reference_plugin` | `app/plugins/signal_reference_plugin.py` | 0 |
| `app.plugins.templates.example_plugin.__init__` | `app/plugins/templates/example_plugin/__init__.py` | 0 |
| `app.plugins.validator.__init__` | `app/plugins/validator/__init__.py` | 0 |
| `app.schemas.__init__` | `app/schemas/__init__.py` | 0 |
| `app.services.__init__` | `app/services/__init__.py` | 0 |
| `app.utils.__init__` | `app/utils/__init__.py` | 0 |
| `app.websocket.__init__` | `app/websocket/__init__.py` | 0 |


---

*Generated by Senior Software Engineer per WO-007-MAINTENANCE*
