# WO-032 — Production Process Entrypoint

**WO:** WO-032
**TITLE:** Production Process Entrypoint
**STATUS:** IMPLEMENTED
**Predecessor:** WO-030 (durable production delivery wiring) + WO-031 (event reconstruction)

---

## Summary

WO-032 introduces the single authoritative production **process entrypoint** that
turns the already-proven production runtime composition into a real long-lived
operating-system process.  It does NOT redesign any component — it consumes the
existing `ProductionRuntime` through its existing public lifecycle API and the
existing source-registration mechanism.

## Implementation

**Authoritative entrypoint file:** `backend/main.py`

The entrypoint has a minimal responsibility boundary:

```
process entrypoint
      |
      +-- construct runtime        (create_production_runtime, require_durable_delivery=True)
      |
      +-- register sources         (existing ProductionSourceRegistrar mechanism)
      |
      +-- install signal handlers  (SIGINT / SIGTERM)
      |
      +-- runtime.start()
      |
      +-- wait for shutdown signal (threading.Event)
      |
      +-- runtime.stop()
```

Public functions exposed by `backend/main.py`:

- `create_production_entrypoint_runtime(require_durable_delivery=True)` — constructs
  the production runtime via the existing `create_production_runtime()`, always
  requesting durable delivery (fail-closed).
- `register_sources(runtime, provider, factory)` — registers every enabled source
  through the existing `ProductionSourceRegistrar` / `add_source` path.
- `install_signal_handlers(shutdown_event)` — installs minimal SIGINT/SIGTERM
  handlers that request graceful shutdown by setting the process-lifetime event.
- `run_production_process(...)` — drives the full lifecycle: register sources →
  install handlers → start → wait → stop.
- `main()` — the real process entrypoint (`python -m backend.main`).

## Durable Delivery (Fail-Closed)

The production process constructs the runtime with `require_durable_delivery=True`.
If durable post-commit delivery cannot be established (no configured
`DatabaseSessionManager`), `create_production_runtime` raises a `RuntimeError` and
the process **refuses to start** rather than silently downgrading to the legacy
non-durable path.  Startup failure is never caught or suppressed.

## Source Configuration Gap

The repository provides the authoritative source-registration *mechanism*
(`ProductionSourceRegistrar` / `register_production_sources`) but does not ship a
concrete production `ISourceConfigProvider` (no static source catalog, no
env/YAML/JSON loader).  `backend/main.py` therefore wires the registration
boundary and registers whatever enabled source definitions an embedding provider
supplies.  It does NOT fabricate a hidden production source catalog and does NOT
redesign source adapters (out of WO-032 scope).  This limitation is documented as
`SOURCE_CONFIGURATION_GAP = True` in the entrypoint.

## Lifecycle / Signals

- Process lifetime is held open with a `threading.Event` (no new framework).
- SIGINT and SIGTERM both set the shutdown event → wake the wait → `runtime.stop()`
  → clean process exit.
- No `os._exit()`; no abrupt termination; `ProductionRuntime.stop()` is never
  bypassed.

## Tests

Focused lifecycle tests: `backend/tests/test_wo032_production_entrypoint.py`
covering entrypoint construction, mandatory durable delivery, source
registration, runtime start/stop, SIGINT graceful shutdown, SIGTERM graceful
shutdown, and durable-delivery fail-closed (non-bypass).

## Out of Scope (unchanged)

EventPipeline core, dispatcher, durable event repository, outbox, retry/dead-letter,
event reconstruction, projection/checkpoint, plugin delivery, entity/relation
persistence, and all WO-029 / WO-030 / WO-031 implementation remain unchanged.
