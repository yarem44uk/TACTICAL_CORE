# CHANGELOG

## WO-007-009 — Sprint 07 Final

**Date:** 2026-01-27  
**Status:** COMPLETE

### Changes
- Removed duplicate `app.intelligence.pipeline` (IntelligencePipeline)
- Canonical pipeline: `app.core.pipeline.Pipeline` (used by Event Engine)
- Repository cleaned
- Event Bus flow verified: ObservationEngine → EventBus → Pipeline → Repository
