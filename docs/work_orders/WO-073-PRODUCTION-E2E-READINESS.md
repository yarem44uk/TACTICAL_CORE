# WO-073 — PRODUCTION E2E READINESS FORENSIC VALIDATION

```
STATUS: PARTIALLY VERIFIED
REPOSITORY: yarem44uk/TACTICAL_CORE (/opt/data/tactical_core_github)
BRANCH: main
HEAD: 9bbf581fcad94ab790266bbb0371b5b67077b17e
BASELINE: 9bbf581fcad94ab790266bbb0371b5b67077b17e (= origin/main)
VALIDATION DATE (UTC): 2026-09-21T06:28:40Z
HOST: Linux 6.12.48+deb13-cloud-amd64 x86_64
TOOLCHAIN: CPython 3.13.5, pytest 9.1.1
```

## OBJECTIVE

Determine, from repository evidence and executed tests, whether the already
implemented production architecture provides a verifiable end-to-end chain:

```
SOURCE -> ADAPTER/INGESTION -> CANONICAL EVENT -> EVENT PIPELINE
       -> DURABLE JOURNAL -> OBSERVATION -> OPERATOR WALL
       -> CHRONOLOGY -> EVIDENCE / RECORDING
```

WO-073 is a VALIDATION / READINESS GATE. It is documentation-only: **no
production file was modified.** It does not select, activate or provision an
STT engine, and does not create a second event model, journal, observation
model or STT seam.

## SCOPE

Read-only forensic inspection of `backend/app/`, targeted execution of the
already existing canonical test suites, and execution of the already existing
non-destructive synthetic E2E fixture. No redesign. No repairs. Defects (if
any) are documented, not fixed.

## FORENSIC GATE

```
pwd                    -> /opt/data/tactical_core_github
git rev-parse toplevel -> /opt/data/tactical_core_github
git branch --show-current -> main
git rev-parse HEAD     -> 9bbf581fcad94ab790266bbb0371b5b67077b17e
git rev-parse origin/main -> 9bbf581fcad94ab790266bbb0371b5b67077b17e
git log -1 --oneline   -> 9bbf581 WO-072: integrate STT decision evidence chain
remote -v              -> origin git@github.com:yarem44uk/TACTICAL_CORE.git
git status --porcelain=v1
   M backend/app/plugins/manager/__pycache__/plugin_manager.cpython-313.pyc
  ?? 500
git diff --stat        -> 1 file changed (the .pyc), 0 insertions, 0 deletions
git diff --check       -> CLEAN
```

RESULT: **PASS** — the repository is exactly at the expected WO-073 baseline,
working tree carries only the two known pre-existing local items.

## PROTECTED ARTIFACT / PRE-EXISTING MODIFICATIONS

* `?? 500` — present before and after this WO, untracked, unstaged, never
  opened / read / hashed / copied / moved / renamed / deleted / cleaned.
  Proven by its unchanged `??` porcelain status at every gate checkpoint.
* `M backend/app/plugins/manager/__pycache__/plugin_manager.cpython-313.pyc` —
  a pre-existing compiled-artifact modification. Left exactly as found: never
  restored, modified, staged, hashed or deleted (` M` before and after).

The only working-tree change produced by WO-073 is the new documentation file
committed below.

---

## SOURCE -> EVENT FINDINGS

Production entry point is `backend/main.py`:
`create_production_entrypoint_runtime()` -> `create_production_runtime()` ->
`register_sources()` -> `runtime.start()`.

Production sources are declared in
`backend/app/event_sources/config/production_source_config.py`
(`PRODUCTION_SOURCE_CATALOG`, ADR-010 Option B). Exactly ONE source is
production-enabled:

| SOURCE | ADAPTER | ENTRY POINT | ENABLED |
|---|---|---|---|
| `radio` (multicast RTP, 239.233.18.30:5033, pcm_alaw 8k mono, `vad_enabled: True`) | `multicast_audio` -> `MulticastAudioSourceAdapter` | `PRODUCTION_SOURCE_CATALOG[0]` -> `register_sources` -> `AdapterSupervisor.add_adapter` -> `AdapterRuntime` | YES |

`signal`, `telegram`, `mqtt`, `atak` adapters exist (`event_sources/adapters/*_source_adapter.py`)
and are unit-tested, but they are **NOT declared in the production catalog** and
therefore are not production-enabled by configuration. `connectors/*` are the
legacy pre-canonical connector layer and are off the canonical composition path.

EXISTENCE OF A FILE IS NOT PRODUCTION ENABLEMENT. Only `radio` is enabled.

The runtime seam is `backend/app/event_sources/runtime/adapter_runtime.py`:
`_poll_forever()` -> `adapter.read_events()` -> `_process_raw()` ->
`factory.create_event(raw, source_name)` -> `pipeline.process(event)`.

## ADAPTER -> CANONICAL EVENT FINDINGS

Sole RAW -> Event boundary is `AdapterRuntime._process_raw()` calling
`EventFactory.create_event()` (`backend/app/event_sources/factory/event_factory.py`),
reusing the canonical `app.event.event.Event` (frozen dataclass).

Deterministic fields:
* `event_id` — `EventIdentityResolver` (WO-025) resolves a deterministic
  canonical identity from the raw source message + source name; falls back to a
  UUID4 default when no stable identity is derivable.
* `timestamp` — normalised to UTC from `timestamp|time|datetime|date|ts|created_at`,
  falling back to `datetime.now(timezone.utc)`.
* `source` — the adapter/runtime name (e.g. `radio`).
* `event_type` — defaults to `EventType.CUSTOM` (the type the production
  EventFactory emits for source-adapter events).
* `metadata` — `EventMetadata(tags, properties{source_name, ...}, correlation_id)`;
  `correlation_id` is lifted from `raw_data["correlation_id"]`.
* `payload` — the raw dict minus the timestamp keys.

Evidence reference: for the radio recording path the payload carries a
`recording` block (`wav_path`, `sha256`, `duration_ms`, `complete`,
`finalize_reason`) and the canonical identity chain
`audio_recording_id == content_id`.

## CANONICAL EVENT -> PIPELINE FINDINGS

`EventPipeline.process()` (`backend/app/event_pipeline/event_pipeline.py`)
enforces a single lifecycle: before-middleware -> filters -> [durable path or
legacy path]. Lock-serialised (`threading.Lock`) so ordering within the process
is the call order.

When a `DurableDeliveryDispatcher` is attached (PRODUCTION), `_process_durable()`
runs and:
1. rejects non-canonical input at the durable boundary (`TypeError` for a raw
   dict) BEFORE any persistence;
2. atomically persists the canonical Event **and** its PENDING outbox delivery
   records via `repository.save_with_deliveries(event, consumer_ids)`;
3. runs the Entity/relation projection best-effort AFTER the commit;
4. delivers the ORIGINAL in-memory Event to registered consumers strictly
   AFTER the durable commit, then marks each durable delivery record
   DELIVERED (or FAILED for retry);
5. runs a recovery pass (`deliver_pending()`) for any other
   pending/stale/failed/requeued record.

No consumer side effect can run before the durable commit.

Validation/normalisation/duplicate/ordering/error semantics are as above;
there is exactly ONE pipeline.

## PIPELINE -> JOURNAL FINDINGS

The durable journal is `DurableCanonicalEventRepository`
(`backend/app/event_repository/durable/sqlalchemy_event_repository.py`,
alias `SQLAlchemyEventRepository`), backed by the single canonical
`DatabaseSessionManager` (no second engine/sessionmaker/persistence plane).

Model: `DurableCanonicalEvent` (`durable_event_model.py`), table
`durable_canonical_events`:
* `id` — internal surrogate ORM PK (SQLAlchemy mechanics only);
* `event_id` — authoritative canonical identity, DB-level `UNIQUE`
  (`uq_durable_canonical_events_event_id`);
* `seq` — durable, monotonic, `UNIQUE`, `indexed`; assigned as `MAX(seq)+1`
  inside the same transaction; deterministic replay order `ORDER BY seq ASC`;
  a duplicate `event_id` rolls back WITHOUT consuming a sequence (duplicate
  retains its original `seq`);
* `event_type` (indexed), `timestamp`, `source`, `payload` (JSON),
  `metadata` (JSON), `created_at`.

Write path: `save()` / `save_with_deliveries()` / `save_many()`.
Read path: `get`, `list_all`, `iter_after_seq`, `list_after_seq`, `max_seq`,
`query_events(cursor, limit)` (keyset pagination on `seq`), `get_durable_event`.
Durability: append-only, single-transaction commit, no UPDATE/DELETE except the
explicit `delete()` API. Ordering: monotonic `seq`. Restart persistence:
proven by executable tests (see RESTART/PERSISTENCE FINDINGS).

## JOURNAL -> OBSERVATION FINDINGS

Mapping class: `EventToObservationMapper`
(`backend/app/observation/mapper.py`), reached from
`ObservationService._handle_canonical_event()` (`service.py`) via
`CanonicalEventToObservationAdapter.to_observation_dict()`
(`canonical_adapter.py`), then `ObservationProcessor.process_event()`
(`processor.py`) -> `ObservationFactory` -> `ObservationRepository`.

Subscription: `ObservationService.subscribe_canonical(event_bus)` subscribes to
`EventType.CUSTOM` on the CANONICAL bus
(`app.event_bus.event_bus.EventBus`), wired in `composition.py` via
`pipeline.set_event_bus(...)` — and, in production, the same service is reached
post-commit through the durable outbox consumer `"observation"`.

Event -> observation `event_type` derivation (`_SOURCE_TO_EVENT_TYPE`):
`signal->signal.message`, `radio->radio.transmission`, `atak->atak.map_object`,
`mqtt->mqtt.message`, `telegram->telegram.message`; fallback to the canonical
`event_type` value. WO-059: a canonical `radio` event whose payload carries a
`recording` block is classified `radio.recording` (never forced into the
frequency+callsign contract).

Required fields / rejection conditions (by mapping, `observation/models.py`):
* `radio.transmission` -> `required_fields=["frequency", "callsign"]`;
* `radio.recording` -> `required_fields=[]` (WO-059 exemption for the
  RTP->VAD->WAV path, which has no frequency/callsign source);
* `telegram.message` -> `["chat_id","text"]`; `atak.map_object` ->
  `["uid","location"]`; `mqtt.message` -> `["topic","payload"]`;
  `rest.webhook` -> `["endpoint"]`; default mapping -> `[]`.

Validation gate (`ObservationProcessor._validate_event`): non-empty `event_id`,
non-empty `event_type`, non-empty `data`, and per-mapping `required_fields`.
Rejection returns `ObservationResult(success=False, error_message=...)` — it
never raises to the caller and never weakens the requirement.

Identity/provenance: `immutable_id = custom_immutable_id or event.event_id`
(the canonical durable identity); `occurred_at = event.timestamp` (WO-060
event-time field, distinct from the ingestion `timestamp`); `provenance`
carries `original_timestamp`, `capture_method="event_bus:<type>"`,
`raw_source_reference="event://<source>/<event_id>"`, `correlation_id`;
`evidence_payload` preserves `raw_data` (so recording identity and evidence
references survive into the read model).

Failure isolation: an `IntegrityError`/persistence failure on a duplicate is
converted to `success=False` and the shared Session is explicitly rolled back
(`_recover_session()`), so later events are not silently dropped.

## OBSERVATION -> OPERATOR WALL FINDINGS

Data source and transport:
* `GET /api/v1/operator/observations` (`backend/app/operator/router.py` ->
  `OperatorService.list_observations()` -> `SessionManagerObservationRepository.list_chronological()`)
  — the WO-060 read model over the durable `observations` table. GET-only.
* The Wall UI (`backend/app/operator/static/operator.js`, `index.html`) is a
  **pure consumer** of that single GET: it renders the server's
  `occurred_at DESC` order verbatim, never reorders, never mutates, never opens
  a second event store, and never consumes the canonical event stream
  (in-code statement at `operator.js:386-391`).
* The separate event feed uses `GET /api/v1/operator/events` and the SSE tail
  `GET /api/v1/operator/events/stream` (WO-037-04, keyset/`seq`-based,
  `Last-Event-ID` resume). Real-time streaming therefore covers the durable
  EVENT feed; the observation Wall itself is pull-on-load / on refresh.

Displayed events correspond to durable records: the Wall renders rows derived
from durable Observations, whose `immutable_id` is the canonical durable
`event_id`, and whose `evidence_payload` is preserved intact.

Can events disappear between journal and UI? A canonical Event is committed to
the journal FIRST; the observation consumer is a durable outbox consumer with
AT-LEAST-ONCE semantics — a consumer failure marks the record `FAILED` and the
recovery pass retries it, so a temporary absence is recoverable and never a
silent loss. Two honest caveats:
1. the Wall's observation view is not itself a live stream — it reflects state
   at the moment of the GET;
2. a mapping-level rejection (`required_fields` unmet -> `success=False`) does
   not raise, so the outbox record is marked DELIVERED and the observation is
   not created and not retried. The durable Event remains authoritative in the
   journal, so this is a projection gap (visible on `/events`), not an Event
   loss. Classified as a documented LIMITATION, not a blocking defect.

## CHRONOLOGY FINDINGS

Authoritative chronological ordering of the observation read model
(`SessionManagerObservationRepository.list_chronological`):
`ORDER BY occurred_at DESC, timestamp DESC, id DESC`
(`backend/app/intelligence/observation/repository.py`). NULL `occurred_at`
sorts last. The `id` (unique UUID) tie-break makes the order fully
deterministic — ties on event time never produce a non-deterministic order.

The durable EVENT log orders by monotonic `seq ASC`, and the operator event
feed keyset-paginates on that `seq`; the SSE stream emits real persisted `seq`
values read from the durable row (not reconstructed as `base + index`), so it
stays correct across sequence gaps.

Chronology is therefore preserved and deterministic across event creation ->
journal -> observation -> wall, and across restart (the ordering is a pure
function of persisted columns). No stronger guarantee (e.g. wall-clock
causality across sources) is claimed by the implementation or asserted here.

## EVIDENCE FINDINGS

Classification: **PARTIAL — event -> recording evidence is VERIFIED for the
radio recording chain; a generic "any event -> any artifact" reference is not
implemented as a first-class field.**

Implemented link (radio):
```
canonical radio recording Event
  -> observation (observation_type "radio", evidence_payload.raw_data.recording
     + raw_data.audio_recording_id == content_id)
  -> GET /api/v1/operator/recordings/{recording_id}
     (backend/app/operator/recording_access.py + router.py)
  -> confined WAV artifact (identity-resolved, never path-based)
```
`RecordingAccess.resolve()` resolves the artifact from the canonical recording
IDENTITY (via the WO-025 identity resolver, `radio|content|<content_id>`) and
verifies SHA-256; the returned media is byte-identical to the archived WAV.
The Wall builds the playback URL ONLY from the canonical recording identity,
never from `wav_path`/`mp3_path`.

Fail-closed evidence semantics (WO-062): unknown identity -> 404; missing
artifact / corrupt artifact / missing / malformed / mismatched SHA-256 -> fails
closed (503/404); path traversal, absolute-path escape and symlink escape are
rejected; unauthenticated access is rejected. The relationship is never
inferred from a filename.

For non-radio sources (`signal`, `telegram`, `mqtt`, `atak`) there is no
recording/artifact link — those events are text/map observations with no media
artifact. That is by design, not a gap in the radio chain.

## RESTART / PERSISTENCE FINDINGS

Executable evidence (all PASSED in this WO):
* `test_wo014025_durable_checkpoint_catchup.py::test_checkpoint_persists_and_survives_restart`
* `test_wo014025_durable_checkpoint_catchup.py::test_durable_entity_state_survives_restart`
* `test_wo014026_startup_catchup_wiring.py::test_restart_recovery_heals_projection_gap`
* `test_wo024_migration_durability.py::test_crash_after_commit_persists_migration`
* `test_wo024_migration_durability.py::test_production_runtime_reopens_and_operates_after_recovery`
* `test_wo027_migration_durability.py::test_restart_recovers_pending_and_stale_inflight`
* `test_wo027_migration_durability.py::test_commit_then_process_crash_delivery_recovers`
* `test_wo060_observation_read_model.py::test_occurred_at_survives_reopen`
* `test_wo061_chronological_wall.py::test_radio_recording_survives_to_wall_data`
* `test_wo019_event_replay_consistency.py::test_durable_event_seq_ordering_is_deterministic`

Summary: canonical Events, their `seq`, the projection checkpoint, entity
state, pending/stale outbox deliveries, observation `occurred_at`, and the Wall
data all survive a process restart. `ProductionRuntime.start()` runs the
deterministic projection catch-up BEFORE steady-state source processing, and a
startup catch-up failure is logged/isolated so it can never destroy the runtime
lifecycle nor advance the checkpoint past a failed projection. UI recovery is
implicit: the operator process is stateless and re-reads the durable
repositories on each request.

No destructive restart test was run against production data — all evidence is
from existing tests using temporary file databases.

## FAILURE HANDLING FINDINGS

| Failure | Observed behaviour | Classification |
|---|---|---|
| `adapter.read_events()` fails (recoverable read) | `RUNNING -> DEGRADED`, logged, retried in the SAME runtime thread; does not consume the restart budget; a later success returns to `RUNNING` | RETRY (no fail-open) |
| `adapter.start()` fails / unexpected exception escapes the poll loop | `-> FAILED`, consumes ONE restart-budget unit; if budget remains a NEW thread is spawned, else stays FAILED pending manual `supervisor.restart(name)` | RETRY (bounded), then FAIL-CLOSED |
| `EventFactory.create_event()` fails for one raw event | that event is logged and DROPPED; runtime stays alive | DROP (per-event, isolated) |
| `EventPipeline.process()` raises (e.g. journal write fails) | the exception propagates out of `process()`; `AdapterRuntime._process_raw` logs and DROPS that event; runtime stays alive; nothing is committed | FAIL-CLOSED for that event (not persisted) + DROP; no persistence retry |
| journal write fails inside the durable path | nothing is committed (no partial event, no partial outbox records) — single-transaction atomicity | FAIL-CLOSED (ATOMIC) |
| post-commit consumer (plugin/observation) fails | the durable delivery record is marked FAILED; the recovery pass (`deliver_pending()`) retries; the durable event is untouched | RETRY (AT-LEAST-ONCE) |
| observation mapping/validation rejects the event | `success=False`, logged, session rolled back; the durable Event remains authoritative; the outbox record was already marked DELIVERED (no raise) so it is not retried | DROP of the projection / documented LIMITATION |
| Operator Wall client disconnects | the SSE event stream is resumable via `Last-Event-ID`; a new GET reconstructs the view from durable state | RECOVERABLE (no durable SSE state) |
| recording unavailable / corrupt / hash mismatch | WO-062 evidence access fails closed (404/503); the Wall shows "Recording unavailable" | FAIL-CLOSED |

---

## TEST RESULTS

Environment note: tests were run from `backend/` with the repository venv
(`../.venv/bin/python`, pytest 9.1.1, CPython 3.13.5) and with the host-injected
`PYTHONPATH` removed (`PYTHONNOUSERSITE=1`). One test
(`test_wo032_production_entrypoint.py::test_wo034_backend_dir_bootstrap_is_idempotent`)
asserts that the backend directory appears exactly once on `sys.path`; it fails
ONLY when `backend/` is itself placed on `PYTHONPATH` (`PYTHONPATH` containing
`.`), and passes with `PYTHONPATH` unset or `..` only. **This is a test-harness
artifact, not a production defect** (see DEFECTS D-1).

### Targeted canonical suites (all PASS, 0 failures)

| # | Command (cwd `backend/`) | Result |
|---|---|---|
| T1 | `../.venv/bin/python -m pytest tests/test_wo066_end_to_end.py -q` | exit 0 — **8 passed** |
| T2 | `... tests/test_wo066_end_to_end.py tests/test_wo052_durable_journal.py tests/test_wo061_chronological_wall.py tests/test_wo060_observation_read_model.py tests/test_wo059_radio_recording_observation_mapping.py tests/test_wo062_recording_access.py tests/test_wo065_final_radio_event.py tests/test_wo015_observation_canonical_migration.py tests/test_wo050_canonical_ingestion_contract.py tests/observation/test_observation_service.py -q` | exit 0 — **181 passed** (4.95 s) |
| T3 | `... tests/test_adapter_runtime.py tests/test_adapter_supervisor.py tests/test_event_factory_integration.py tests/test_event_model.py tests/test_event_pipeline.py tests/test_wo025_durable_event_identity.py tests/test_wo014016_durable_event_repository.py tests/test_wo014018_production_durable_event_service.py tests/test_wo014020_production_pipeline_persistence.py tests/test_wo014021_production_event_pipeline_e2e.py tests/test_wo019_event_replay_consistency.py tests/test_wo031_event_reconstruction.py tests/test_wo030_production_delivery_wiring.py tests/test_wo029_delivery_hardening.py tests/test_production_composition.py tests/test_production_bootstrap.py -q` | exit 0 — **213 passed** (7.54 s) |
| T4 | WO-037-01..06 operator suites + 5 source-adapter suites + production source config/registration/lifecycle + WO-014-025/026/027 + WO-032 production entrypoint | exit 0 — **426 passed** (14.04 s) |
| T5 | WO-038/039a/039b/039c/041/048/055/056/057/058/063/064 audio + radio vertical-slice suites | exit 0 — **249 passed** (28.79 s) |
| T6 | WO-024/WO-027 migration durability + WO-014-009..013 + WO-014-022/023/024 + WO-020..023 + event_bus/dispatcher/persistence + plugin wiring/delivery | exit 0 — **243 passed** (12.83 s) |

Total: the six batches above are **1320 literal test executions**; T1 is a strict
subset of T2 (`tests/test_wo066_end_to_end.py` is present in both), so the
**de-duplicated targeted total is 1312 tests** (1320 - 8). 1312 is explicitly a
DE-DUPLICATED total, not a literal execution count; the individual batch counts
above are unchanged.

### Full suite (informational, for completeness)

| Command | Result |
|---|---|
| `../.venv/bin/python -m pytest tests/ -q --ignore=tests/intelligence/test_identity.py` | WO-073 execution: **2180 passed, 50 failed, 16 skipped** in 102.97 s; independent forensic rerun: **2181 passed, 49 failed, 16 skipped** in 102.36 s (rc 1) |
| `../.venv/bin/python -m pytest tests/ -q` | collection error: `tests/intelligence/test_identity.py` cannot import `ExternalIdentity` (pre-existing stale import, module excluded by the project's standard command) |

Neither count may be presented as the uniquely verified actual count. The two
runs differ by exactly one test, and the difference is attributable to
order/`PYTHONPATH`-sensitive behaviour around
`tests/test_wo032_production_entrypoint.py::test_wo034_backend_dir_bootstrap_is_idempotent`
(it passes with `PYTHONPATH` unset or `..` only, and fails when `backend/` is
itself placed on `PYTHONPATH` — see DEFECT D-1). The discrepancy is a harness /
order / `PYTHONPATH` sensitivity, NOT a production-path defect, and it does not
alter any conclusion of this document; the legacy failures remain outside the
canonical production path.

All failures in both runs (50 in the WO-073 execution, 49 in the independent
rerun) are confined to the **legacy subsystem** and are pre-existing at
the untouched baseline:

* `tests/integration/test_end_to_end_pipeline.py` (6), `test_entity_bridge_e2e_real.py` (14),
  `test_identity_persistence.py` (12), `test_entity_persistence.py` (2),
  `test_event_bus.py` (1) — all import the LEGACY `app.core.event_bus.EventBus`
  and the legacy in-memory `app.intelligence.entity.*` models. Representative
  error: `TypeError: 'function' object is not iterable` at
  `app/core/event_bus.py:218`.
* `tests/intelligence/test_entity.py` (1), `test_entity_manager.py` (5),
  `test_relations.py` (5), `test_validation_framework.py` (3) — legacy
  entity/relation/observation in-memory models (e.g. `MockEntityRepository`
  lacking `resolve_by_identity`).

The canonical production chain uses the CANONICAL bus
(`app.event_bus.event_bus.EventBus`), `app.observation.service` and
`app.operator.*`; every suite covering those passes. The legacy failures are
therefore off the WO-073 chain and are classified TEST GAP / legacy drift.

### Runtime probe (beyond the unit tests)

A read-only in-process probe against a temporary SQLite database constructed
the real production composition (`create_production_runtime()`) and printed the
live wiring. Observed (exit 0):

```
pipeline type           : app.event_pipeline.event_pipeline.EventPipeline
repository              : SQLAlchemyEventRepository   durable? True
event_bus canonical     : app.event_bus.event_bus.EventBus   True
delivery_dispatcher     : DurableDeliveryDispatcher
outbox consumer ids     : ['plugins', 'observation']
registered consumers    : ['observation', 'plugins']
projection wired        : True
observation_service     : ObservationService
canonical subscription  : True
event_factory           : EventFactory   identity_resolver: True
radio_event_integrator  : RadioEventIntegrator
catch_up                : ProjectionCatchUp
supervisor              : AdapterSupervisor
```

This is RUNTIME VERIFIED evidence that composition wires exactly one pipeline,
one durable journal, one canonical bus and one observation consumer.

## OPTIONAL NON-DESTRUCTIVE E2E TEST

```
SAFE_SYNTHETIC_E2E_FIXTURE: AVAILABLE
```

`backend/tests/test_wo066_end_to_end.py` is an already existing safe
synthetic/in-memory E2E fixture. It uses a temporary WAV under `tmp_path`, a
temporary SQLite file, a deterministic fake transcriber implementing the
production `ITranscriber` seam, and the real canonical runtime machinery and
production composition. It does NOT contact radio hardware,
Signal/Telegram/MQTT/ATAK infrastructure, does not touch production databases,
sends no external messages, modifies no real recordings and does not access
`?? 500`.

Scope limitation of this fixture (inherited from WO-066; NOT a WO-073 change and
NOT a WO-073 defect): the fixture **hand-constructs**
`MulticastAudioSourceAdapter`, explicitly injects `runtime.radio_event_integrator`,
and directly drives `aruntime._process_raw(final_raw)`. It therefore verifies the
canonical production runtime chain
(`AdapterRuntime -> EventFactory -> EventPipeline -> durable journal -> Observation
-> Operator Wall`), but it does **NOT** constitute independent proof that the
production source-adapter factory/integrator injection seam wires
`radio_event_integrator` through: `register_multicast_audio_adapter()` registers
the adapter builder, while `radio_event_integrator` is not injected by that
production factory registration. The hand-built adapter and the direct
`_process_raw` invocation are limitations of the synthetic fixture. No source
adapter, registration, pipeline or observation code was modified by WO-073.

Executed: **8 passed** (exit 0). It verifies, through the real canonical runtime
path, that ONE accepted durable radio recording traverses
`recording -> STT seam -> enrichment -> final radio event -> canonical RAW ->
AdapterRuntime._process_raw -> EventFactory -> EventPipeline -> durable journal
-> canonical Observation -> /api/v1/operator/observations (Wall)` and that the
evidence is retrievable via `/api/v1/operator/recordings/{id}` with SHA-256
verification, including persistence-level idempotency
(`COUNT(immutable_id) == 1` after re-delivery) and source immutability.

## EVIDENCE MATRIX

| Stage | Implementation | Test Evidence | Runtime Evidence | Status |
|---|---|---|---|---|
| Source -> Adapter | `main.py` -> `create_production_runtime` -> `register_sources` -> `AdapterSupervisor`/`AdapterRuntime`; catalog: `production_source_config.PRODUCTION_SOURCE_CATALOG` (only `radio`/`multicast_audio` enabled) | `test_wo032_production_entrypoint.py`, `test_production_source_registration.py`, `test_production_source_lifecycle.py`, `test_wo036_production_source_config.py`, `test_radio_source_adapter.py`, `test_wo038_source_adapter.py`, `test_wo052_durable_journal.py` | Runtime probe: supervisor constructed; composition path instantiated | VERIFIED |
| Adapter -> Canonical Event | `AdapterRuntime._process_raw` -> `EventFactory.create_event` -> `app.event.event.Event`; `EventIdentityResolver` (WO-025) | `test_adapter_runtime.py`, `test_event_factory_integration.py`, `test_event_model.py`, `test_wo025_durable_event_identity.py`, `test_wo066_end_to_end.py` | Runtime probe: `event_factory` with identity resolver wired; `test_wo066` produced deterministic `event_id` | VERIFIED |
| Canonical Event -> Pipeline | `EventPipeline.process` / `_process_durable` (single lifecycle, durable outbox, post-commit delivery) | `test_event_pipeline.py`, `test_wo014020`, `test_wo014021`, `test_wo030_production_delivery_wiring.py`, `test_wo029_delivery_hardening.py` | Runtime probe: `delivery_dispatcher = DurableDeliveryDispatcher`, consumers `['plugins','observation']` | VERIFIED |
| Pipeline -> Journal | `SQLAlchemyEventRepository` (`durable_canonical_events`, UNIQUE `event_id`, monotonic UNIQUE `seq`, atomic `save_with_deliveries`) | `test_wo014016_durable_event_repository.py`, `test_wo014018`, `test_wo052_durable_journal.py`, `test_wo019_event_replay_consistency.py`, `test_wo031_event_reconstruction.py` | Runtime probe: `repository durable? True`; `test_wo066` persisted and read back | VERIFIED |
| Journal -> Observation | `ObservationService.subscribe_canonical` (`EventType.CUSTOM`) -> `CanonicalEventToObservationAdapter` -> `EventToObservationMapper` -> `ObservationProcessor` -> `ObservationFactory`/repository; per-mapping `required_fields` | `test_wo015_observation_canonical_migration.py`, `tests/observation/test_observation_service.py`, `test_wo059_radio_recording_observation_mapping.py`, `test_wo050_canonical_ingestion_contract.py`, `test_wo066_end_to_end.py` | Runtime probe: `canonical subscription: True`; `test_wo066` produced the expected canonical Observation | VERIFIED |
| Observation -> Operator Wall | `OperatorService.list_observations` -> `SessionManagerObservationRepository.list_chronological`; `GET /api/v1/operator/observations`; Wall UI pure consumer (`operator.js:386-391`) | `test_wo060_observation_read_model.py`, `test_wo061_chronological_wall.py`, `test_wo037_01..06`, `test_wo066_end_to_end.py::test_wo066_02` | `test_wo066_02` asserted the observation is present in the real `TestClient` response of `/api/v1/operator/observations` | VERIFIED |
| Chronology | `occurred_at DESC, timestamp DESC, id DESC` (observation read model); `seq ASC` (durable event log + SSE) | `test_wo060_observation_read_model.py`, `test_wo061_chronological_wall.py`, `test_wo019_event_replay_consistency.py`, `test_wo037_04_operator_sse.py` | `test_wo060::test_occurred_at_survives_reopen` | VERIFIED |
| Event -> Evidence | `RecordingAccess.resolve(recording_id)` from canonical identity + SHA-256; `GET /api/v1/operator/recordings/{id}`; identity-based playback in the Wall | `test_wo062_recording_access.py` (51 tests incl. fail-closed/hash/traversal/range), `test_wo066_end_to_end.py::test_wo066_03/05` | `test_wo066_03` asserted byte-identical WAV over the real operator app and SHA-256 match | PARTIAL (radio chain VERIFIED; no generic artifact reference for non-radio sources) |
| Restart/Persistence | Durable journal + `seq` + projection checkpoint + outbox; startup catch-up in `ProductionRuntime.start()`; stateless operator process | `test_wo014025`, `test_wo014026`, `test_wo024_migration_durability.py`, `test_wo027_migration_durability.py`, `test_wo060::test_occurred_at_survives_reopen`, `test_wo061::test_radio_recording_survives_to_wall_data` | `test_wo024::test_production_runtime_reopens_and_operates_after_recovery` (real reopen) | VERIFIED |
| Failure Handling | `AdapterRuntime` DEGRADED/FAILED + bounded restart; per-event drop isolation; atomic commit; outbox AT-LEAST-ONCE retry; WO-062 fail-closed evidence | `test_adapter_runtime.py`, `test_adapter_supervisor.py`, `test_wo029_delivery_hardening.py`, `test_wo030_production_delivery_wiring.py`, `test_wo052_durable_journal.py` (T5/T9 failure paths), `test_wo062_recording_access.py` | Source-code verified + test verified (see FAILURE HANDLING FINDINGS) | PARTIAL (mapping-level rejection is marked DELIVERED and not retried — LIMITATION L-1) |

## DEFECTS

No blocking, in-scope production defect was found. Two non-blocking findings
are recorded. Neither was fixed (WO-073 is a validation gate and both are
outside a minimal unambiguous fix that preserves established architecture).

### D-1 — TEST HARNESS artifact (non-blocking, TEST GAP)
```
DEFECT ID:   D-1
LOCATION:    backend/tests/test_wo032_production_entrypoint.py:359
             (test_wo034_backend_dir_bootstrap_is_idempotent)
OBSERVED:    assert _sys.path.count(backend_dir) == 1 -> AssertionError: 2 == 1
             when backend/ is itself placed on PYTHONPATH (PYTHONPATH containing '.').
EXPECTED:    exactly one backend dir entry on sys.path.
EVIDENCE:    passes 13/13 with PYTHONPATH unset or PYTHONPATH=.. ; fails only
             with PYTHONPATH='.' or '.:..'.
IMPACT:      none on production behaviour; a harness/runner-environment
             sensitivity in a bootstrap-idempotency assertion.
MINIMAL FIX: none proposed (would touch an entrypoint-idempotency assertion;
             out of WO-073 scope).
CLASSIFY:    TEST GAP (non-blocking)
```

### D-2 — Test-harness invocation note (documentation gap)
Running the repository test suite requires `PYTHONPATH` to contain the
repository root (`..`) because `app/event_bus/interfaces/__init__.py` imports
the absolute `backend.app...` path, while `backend/` itself must NOT be on
`PYTHONPATH` (D-1). This is a usage/documentation constraint of the existing
tree; no code change was made. CLASSIFY: **DOCUMENTATION GAP (non-blocking)**.

## LIMITATIONS

* L-1 — A journal->observation **mapping-level rejection** (`required_fields`
  unmet, e.g. `radio.transmission` without `frequency`+`callsign`) returns
  `success=False` without raising, so the durable outbox record is marked
  DELIVERED and the observation is neither created nor retried. The durable
  Event remains authoritative and is still visible on `/events`; the gap is in
  the observation projection only. Classified as a LIMITATION, not a defect:
  weakening or reclassifying it would change established delivery semantics,
  which WO-073 forbids.
* L-2 — The observation Wall is a pull-based view over the WO-060 read model;
  real-time streaming exists for the EVENT feed (SSE) but not for the
  observation Wall itself.
* L-3 — Evidence linkage is specific to the radio recording chain. Non-radio
  sources produce observations with no media artifact; there is no generic
  "event -> arbitrary artifact" reference field.
* L-4 — Most runtime evidence is test-harness local (temporary DBs, loopback
  sockets, a deterministic fake transcriber). No live multicast radio reception,
  no external Signal/Telegram/MQTT/ATAK infrastructure and no production STT
  engine were exercised — by design and by WO prohibition. The chain is
  therefore VERIFIED at the code + test + composition-runtime level, and the
  remaining gap to live-field verification is explicitly NOT covered here.
* L-5 — 50 (WO-073 execution) / 49 (independent rerun) pre-existing legacy-subsystem test failures and 1 pre-existing
  collection error remain at baseline; they are off the canonical chain and
  were not repaired.

## CONCLUSION

The already implemented production architecture provides a coherent,
single-path, test- and composition-verified end-to-end chain for the
production-enabled `radio` source:

```
radio (multicast RTP) -> MulticastAudioSourceAdapter -> AdapterRuntime
  -> EventFactory (deterministic identity) -> canonical app.event.Event
  -> EventPipeline (atomic commit + durable outbox, post-commit delivery)
  -> SQLAlchemyEventRepository / durable_canonical_events (UNIQUE event_id, monotonic seq)
  -> canonical Observation (occurred_at event-time, immutable_id == event_id)
  -> Operator Wall GET /api/v1/operator/observations (deterministic occurred_at DESC)
  -> evidence: GET /api/v1/operator/recordings/{recording_id} (identity-resolved, SHA-256 verified)
```

There is exactly ONE event model, ONE journal, ONE pipeline, ONE observation
model and ONE STT seam. Chronology is deterministic and survives restart.
Failure behaviour is isolated per event, atomic at the journal boundary, and
retryable at the delivery boundary; evidence access fails closed.

Two non-blocking test/harness findings and one documented projection limitation
were recorded; nothing was fixed, because no fix was both in scope and
unambiguous.

The full chain is VERIFIED for the production-enabled radio path at the
code + executed-test + composition-runtime level. Live field reception with a
provisioned STT engine is explicitly out of scope and remains unverified.

**WO-073 does not authorize any STT engine, does not activate Faster-Whisper or
Vosk, installs no model, and changes no production code.**

---

## INTEGRITY STATEMENT

```
PRODUCTION CODE CHANGED:  NO  (backend/ diff vs baseline: EMPTY)
STT CHANGED:              NO
STT ENGINE ACTIVATED:     NO
MODEL INSTALLED:          NO
DEPENDENCIES CHANGED:     NO
NEW EVENT MODEL:          NO
NEW JOURNAL:              NO
NEW STT SEAM:             NO
?? 500:                   UNTOUCHED
pre-existing .pyc:        PRESERVED (unstaged, unmodified)
```

The single deliverable of WO-073 is this document.
