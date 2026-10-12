# WO-090 — INDEPENDENT AUDIT REPORT

## PUBLICATION PROVENANCE HEADER (added by WO-091; NOT part of the audited report body)

This report was RECOVERED FROM AN IDENTIFIED CONVERSATION RECORD. It was NOT separately
supplied as a standalone file by the operator.

- Source record: Hermes session-state database `/opt/data/state.db`, table `messages`,
  row `id = 33915`, `session_id = api-549b1ef148ee9152`, `role = assistant`.
- Source report body length: 29992 characters / 30775 bytes (UTF-8).
- Source-message SHA-256 (provenance metadata only — NOT a newly computed hash of the
  published file, and NOT to be read as a hash of the file below):
  `174956eb79b0e565b5feeaa5c34a1a2a5391bd1fd3614027f69a0f90a60407a9`

Integrity statements:

- The recorded source-message SHA-256 above WAS independently re-verified during WO-091 by
  hashing the exact source bytes read from `messages.id = 33915` (UTF-8); the recomputed
  digest matched the recorded value exactly.
- The report body was NOT rewritten, summarized, paraphrased, reordered or technically
  altered during publication. It is reproduced below byte-for-byte.
- The audited report's findings, verdict (`ACCEPTED WITH CONDITIONS`), severities and wording
  are preserved intact. All publication metadata is confined to this header and to the
  BEGIN/END marker lines, which lie outside the report body.
- Verbatim extraction proof: the report body begins at byte offset 1735 of this file (the
  byte immediately after the BEGIN marker line and its newline) and is exactly 30775 bytes
  long, so `sha256(file[1735:32510])` == `174956eb79b0e565b5feeaa5c34a1a2a5391bd1fd3614027f69a0f90a60407a9`.

---- BEGIN UNALTERED SOURCE REPORT BODY (byte offset 1735, 30775 bytes) ----
WO-090 INDEPENDENT AUDIT REPORT

OVERALL VERDICT
ACCEPTED WITH CONDITIONS

The report is materially accurate and evidence-grounded. Every material technical claim in WO-089 was independently reproduced from live repository state at the verified baseline. Two statements are imprecise (attribution of the observation/wall failure path to `EntityBridge`+startup catch-up; the container gateway address), and two gaps are under-stated (body-limit enforcement order; silent conflation of seq-collision with duplicate-event in the durable write path). None of these invalidates the report's conclusion. WO-089's own verdict — BLOCKED, PRODUCTION ACCESS NOT ESTABLISHED — stands, and its architecture recommendation may be approved only conditionally.

AUDIT TARGET NOTE (favourable deviation): the WO-089 report text WAS available and was audited in full, not merely the prompt summary. It is NOT in the repository; it lives outside it at /opt/data/output/WO-089-PRODUCTION-HOSTING-ARCHITECTURE-AND-DEPLOYMENT-READINESS-DESIGN-GATE.md (372 lines). Found by exhaustive glob over /opt/data/**; no copy under /opt/data/uploads/. Repository evidence: `git ls-tree -r --name-only HEAD | grep -E 'WO-08[6-9]|WO-09'` → NONE_FOUND.

────────────────────────────
BASELINE AND PROVENANCE

Repository identity: toplevel /opt/data/tactical_core_github, inside-work-tree true, git-dir .git.
Remote: origin git@github.com:yarem44uk/TACTICAL_CORE.git (fetch+push).

Raw:
  pwd → /opt/data/tactical_core_github
  git branch --show-current → main
  git rev-parse HEAD → 10c030900207cbaa928d2ea06c753506a4f04ab4
  git ls-remote origin refs/heads/main → 10c030900207cbaa928d2ea06c753506a4f04ab4  refs/heads/main
  git rev-list --count origin/main..HEAD → 0
  git rev-list --count HEAD..origin/main → 0
  git log -1 → 10c0309… "docs: reconcile WO-081 through WO-085 history" (Tactical Core Engineer, Thu Oct 8 15:05:05 2026 +0000)

EXPECTED BASELINE 10c0309… := PRESENT. HEAD == origin/main == expected baseline. WO-089 was assessed against the intended revision; no baseline drift.

Working tree (porcelain=v1), BEFORE and AFTER this audit — byte-identical:
   M backend/app/plugins/manager/__pycache__/plugin_manager.cpython-313.pyc
  ?? 500
  ?? backend/tests/test_wo080_audit_idempotency.py
  ?? backend/tests/test_wo080_whatsapp_audit_corrective.py
  ?? docs/adr/ADR-015-WhatsApp-Ingress-Architecture.md
  ?? docs/work_orders/WO-078-WHATSAPP-INBOUND-HTTPS-ARCHITECTURE-GATE.md
  ?? docs/work_orders/WO-079-WHATSAPP-INGRESS-ARCHITECTURE-DECISION-GATE.md
  sha256(porcelain) before == after == c380c4a91cc5e50095e94d447fda8f4d10135c33058d89f19acfd0f52f7a236f

Preservation: PASS. Deltas I caused = NONE. The ` M …cpython-313.pyc` is the known pre-existing tracked-pyc delta (already ` M` at first observation, unchanged). `?? 500` was observed ONLY as porcelain text — never opened, hashed, stat-ed, staged, copied or moved. No staging: `git diff --cached --stat` empty. HEAD/refs unmoved (`git ls-remote origin` shows refs/heads/main still 10c0309…; no new branch). `git diff --stat` shows only the pre-existing pyc.

Evidence classification legend used below: VERIFIED (read from source/git this session) / PARTIALLY VERIFIED / NOT VERIFIED / CONTRADICTED / BLOCKED; and RUNTIME-ONLY items are marked NOT VERIFIED — TEST EXECUTION PROHIBITED.

────────────────────────────
FINDINGS TABLE

| ID | WO-089 claim | Evidence inspected | Verdict | Severity | Consequence |
| F1 | Production access/deployment infrastructure do not exist | git ls-tree 790 files: no Dockerfile/compose/systemd/nginx/Caddy/Traefik/HAProxy/k8s/helm/terraform/ansible; only .github/workflows/severity-governance.yml; ~/.ssh/config has exactly 1 Host alias (github.com); ADR-010:146 "No deployment model exists" | VERIFIED | HIGH | No authorized provisioning path exists; provisioning WO cannot be authorized |
| F2 | Telegram ingress is FastAPI/uvicorn with POST /telegram/webhook + GET /healthz | telegram_ingress/app.py:47 (TestClient/fastapi), :86 @app.post(webhook_path), :132 @app.get("/healthz"); entrypoint.py:59,78 uvicorn.run(app, host, port) | VERIFIED | INFO | none |
| F3 | Webhook secret validation is fail-closed | secret.py:30 SECRET_HEADER=*** :51-58 empty/missing→False, hmac.compare_digest; app.py:100-106 → 401; config.py:85-91 missing secret ⇒ TelegramIngressConfigError before start | VERIFIED | INFO | none |
| F4 | Body limit 1 MiB with an HTTP 413 path | config.py:45 DEFAULT_MAX_BODY_BYTES=1024*1024; app.py:89-97 len(raw_body)>max ⇒ JSONResponse 413 | VERIFIED | LOW | Claim true as stated; see F4b |
| F4b | (completeness of F4) ordering/verification of the 413 path | app.py:89 `raw_body = await request.body()` runs BEFORE the size test at :91; the size check also precedes the secret check at :100. No test asserts 413: `git grep -n -E '413' -- backend/tests` → 0 files | PARTIALLY VERIFIED | MEDIUM | Oversized bodies are fully buffered before rejection (no memory/bandwidth bound) and the 413 branch is unimplemented-by-test; WO-089 flags the missing test, not the ordering |
| F5 | Dedup is deterministic on chat_id+message_id via UUID5 + durable unique event id | normalizer.py:123-138 emits str(chat_id)/str(message_id); event_identity.py:81-84 `_native(raw,"chat_id","message_id")`, :36 fixed namespace, :191 uuid5; durable_event_model.py:78-83 unique+index; sqlalchemy_event_repository.py:130-136 idempotent conflict-safe save | VERIFIED | INFO | none |
| F6 | HTTP 200 depends on the durable canonical event being committed then found by exists(event_id) | adapter_runtime.py:453-498 (probe before :456, commit via pipeline :459, probe after :485, NEW/DUPLICATE :492-498); composition.py:112-115 probe = SQLAlchemyEventRepository(get_session_manager()).exists; repository :271-279 exists() = real committed-row read | VERIFIED | INFO | none |
| F7 | Event and outbox records are intended to be persisted atomically | sqlalchemy_event_repository.py:138-201 save_with_deliveries — event row + PENDING DurableDeliveryRecord(s) added in ONE `session(commit=True)`; pipeline set_delivery_dispatcher/set_outbox_consumer_ids (composition.py:748-749); _process_durable event_pipeline.py:164-176 | VERIFIED | INFO | Atomicity claim holds |
| F7b | (latent defect in the same area) IntegrityError handling | sqlalchemy_event_repository.py:130-136 and :168-178 catch IntegrityError and treat it as "duplicate event_id"; seq is MAX(seq)+1 (:102-112) with UNIQUE(seq) (durable_event_model.py:70-75). A seq UNIQUE collision on a concurrent writer is therefore indistinguishable from a duplicate event | NOT VERIFIED (runtime) / defect identified by inspection | MEDIUM | Fail-closed ACK is preserved (exists() False ⇒ 503), but on the save_with_deliveries path the rollback is followed by _reconcile_deliveries (:176-177) which creates PENDING outbox rows for an event that was never persisted → orphan records retried then DEAD_LETTER; the collision is never logged |
| F8 | SQLite config lacks explicit WAL and busy_timeout | session.py:156-185 (file SQLite ⇒ QueuePool(pool_size=5,max_overflow=10,pool_pre_ping=True), connect_args={"check_same_thread": False}); grep for journal_mode/busy_timeout/WAL/pragma across backend app → only PRAGMA table_info(observations) at schema_migration.py:311; no `event.listen`/on_connect hook anywhere | VERIFIED | HIGH | No journal-mode/busy-timeout tuning exists; single-writer assumption is untested |
| F9 | Sequence allocation uses MAX(seq)+1 with cross-process concurrency risk | sqlalchemy_event_repository.py:102-112 `_next_seq` = select(max(seq)); durable_event_model.py:63-75 documents "duplicates roll back WITHOUT consuming a sequence"; schema_migration.py:424-449 `_is_sqlite_locked` explicitly treats "database is locked"/"busy" as a real transient condition | VERIFIED | HIGH | Read-modify-write race is real and unproven-safe; blocks architecture approval |
| F10 | Database migration mechanisms may be inconsistent | THREE mechanisms: (a) Alembic MigrationManager migration.py:19-20 imports alembic.command, :486 run_migrations — but NO alembic.ini and NO versions/ in tree (`git ls-tree | grep -ci alembic` → 0); (b) WO-021 revision registry schema_migration.py:329 MIGRATIONS, :612 upgrade_schema; (c) entity_repository/migration.py:7-14 raw sqlite3 executescript. Actual startup: initialize_database(database_url, create_tables=True) → DatabaseManager.initialize → create_tables → Base.metadata.create_all (database.py:116). upgrade_schema is called ONLY from tests | VERIFIED | MEDIUM | Inconsistent as stated; runtime uses unversioned create_all |
| F11 | Durable acceptance does not prove downstream Observation/Wall visibility | event_pipeline.py:189-236 hot path invokes registered consumers INLINE post-commit and returns True regardless of consumer success (:213-223 failure recorded, not fatal); consumers registered composition.py:736-737 ("plugins","observation"), _deliver_observation = event_bus.publish | VERIFIED | HIGH | 200 ⇒ canonical event durable only; the report's boundary statement is correct |
| F11b | (mechanism clause of the same row) "best-effort (EntityBridge swallows failures) and is healed by startup catch-up" | EntityBridge is the ENTITY projection seam (composition.py:467-469, pipeline.set_projection :241); startup catch-up = bootstrap.py:152,156-185 → ProjectionCatchUp, DEFAULT_PROJECTION="entity" (catch_up.py:40) — it heals the ENTITY projection via the checkpoint, NOT the observation read model; observation failures never raise (observation/service.py:415-439 logs and recovers; processor.py:226-231 returns False on mapping rejection) → the outbox record is marked DELIVERED | PARTIALLY VERIFIED | MEDIUM | Imprecise attribution; consequence: a durable event whose observation mapping is rejected is silently DELIVERED and never retried/never visible on the operator wall (no observation catch-up exists) |
| F12 | Migration/schema init: no versioned migration at runtime | same evidence as F10; test_wo021_schema_migration.py is the only upgrade_schema caller; no revision step in entrypoint.py/main.py startup path | VERIFIED | MEDIUM | Upgrading an existing production DB is not deterministic/documented at runtime |
| F13 | Backup and restore readiness | No backup/restore code or procedure in tree; only DatabaseManager.vacuum() database.py:255-269; grep vacuum/.backup/pg_dump over backend/app+scripts → none | VERIFIED (ABSENT) | MEDIUM | RPO/RTO undefined; append-only store unbounded |
| F14 | Tests: none run; readiness blocked | test_wo083_telegram_ingress.py = 902 lines, 47 `def test_`; behaviours covered: 401 (01,02,03b), compare_digest spy (04), 400 paths (05,07,07b,08,09), identity determinism (10-14b), durable-before-ACK (15,16), 503 (17,18), duplicate→1 event (19/20/21), restart-no-duplicate (22), canonical-path reuse (23-26), webhook→observation + operator read model (27c,27d), media reference-only (28-29), no legacy EventBus / no direct DB write (30-34), catalog unchanged (35-37) | VERIFIED (as a coverage statement); NOT EXECUTED — READ ONLY | MEDIUM | No 413 test, no multi-process SQLite test, no migration-upgrade test |
| F15 | Managed-VM (Option A) recommended provisionally, TLS-terminating, subject to SQLite writer safety | entrypoint.py:54-82 (uvicorn, loopback default 127.0.0.1:8030, no ssl_* args); session.py single-owner DatabaseSessionManager; PLATFORM_READINESS.md:23,104 "PostgreSQL-ready" | VERIFIED as written (provisional + explicitly conditioned) | MEDIUM | Architecture decision is legitimately NOT final; conditions are correctly named in the report |
| F16 | Environment is a confirmed non-production sandbox | hostname 769d3b0303ca; /proc/1/comm s6-svscan; /.dockerenv present; /proc/net/tcp shows nothing on 8030/8020/80/443 (only 0.0.0.0:8642=0x21C2, 127.0.0.11:46039=0xB3D7 Docker DNS, 172.18.0.4 ephemeral sockets) | VERIFIED | INFO | none |
| F16b | WO-089 §3 "container IP 172.18.0.4 with gateway 172.17.0.1" | /proc/net/tcp confirms 040012AC = 172.18.0.4; /proc/net/route default route gateway 010012AC = 172.18.0.1 (little-endian) | PARTIALLY VERIFIED | LOW | Gateway misstated (172.17.0.1 is the Docker default-bridge address, not this netns's gateway); no effect on any conclusion |
| F17 | WO-089 §5 item 13 / §4: production DB and secret not configured | .env.example has no TELEGRAM_*/WEBHOOK/X-Telegram (grep exit 1) and DATABASE_URL=sqlite:///./storage/database/tactical_core.db; nothing listening on 8030 | VERIFIED | INFO | none |
| F18 | Citation precision §7/§13: schema_migration.py:415-445 "acknowledges lock contention" | the actual lock-contention acknowledgement is schema_migration.py:424-449 (_is_sqlite_locked docstring :428-431); 415-417 is the migration-state dict | PARTIALLY VERIFIED | LOW | Line range off by ~9 lines; the cited fact is correct |
| F19 | WO-089 report exists as a repository artifact | Not in HEAD (docs/work_orders ends at WO-085); it exists only outside the repo in /opt/data/output/ | VERIFIED (as recorded by the report itself, §20) | INFO | The report is not part of the audited tree — correctly disclosed by WO-089 |

Summary: 15 VERIFIED, 5 PARTIALLY VERIFIED, 0 CONTRADICTED, 0 BLOCKED. No claim in WO-089 was found to be false.

────────────────────────────
DETAILED TECHNICAL FINDINGS

B. Telegram ingress and ACK semantics
Entrypoint/framework: `create_telegram_ingress_app()` (app.py:57-137), FastAPI (app.py:47), started by `uvicorn.run(app, host=config.host, port=config.port)` (entrypoint.py:78) — `python -m app.telegram_ingress.entrypoint`, default 127.0.0.1:8030 (config.py:37-38). Route definitions verified: `@app.post(webhook_path, include_in_schema=False)` (app.py:86) where webhook_path defaults to "/telegram/webhook" (app.py:61, config.py:39) — parameterized by TELEGRAM_WEBHOOK_PATH (config.py:34,109-111) — and `@app.get("/healthz")` (app.py:132-135).
Secret: header constant `SECRET_HEADER="X-Tele...oken"` (secret.py:30); source = env `TELEGRAM_WEBHOOK_SECRET` (config.py:31); comparison `hmac.compare_digest(expected_secret, presented.strip())` (secret.py:58) guarded by `if not expected_secret or not presented_header: return False` (secret.py:51-56). Missing/empty/mismatch ⇒ HTTP 401 (app.py:101-106). Fail-closed at startup if the secret or DATABASE_URL is absent (config.py:85-98).
Body size: enforced AFTER full body consumption — `raw_body = await request.body()` (app.py:89) precedes `if len(raw_body) > max_body_bytes` (app.py:91). The 413 return (app.py:95-97) is therefore guaranteed for the buffered body but does not bound memory/bandwidth, and it fires before the secret check (so an unauthenticated caller can force the full read). The branch has ZERO test coverage (no "413" token anywhere under backend/tests).
Invalid/unsupported input: malformed JSON ⇒ 400 (app.py:108-114); non-object JSON ⇒ 400 (app.py:116-120); missing/unsupported update type, missing message_id, missing chat.id ⇒ TelegramUpdateError ⇒ 400 with zero durable events (normalizer.py:105-130, service.py:98-102). Duplicates: pre-probe records already_present (adapter_runtime.py:456) and the final status is DUPLICATE (adapter_runtime.py:492-498) ⇒ 200 with `duplicate: true` (service.py:133-137, app.py:123-127); no second durable row (`UNIQUE(event_id)`, durable_event_model.py:78-83).
Persistence failure: never swallowed — factory error ⇒ INVALID (adapter_runtime.py:445-451); pipeline exception ⇒ FAILURE (adapter_runtime.py:458-466); probe false/null ⇒ FAILURE "durable persistence not confirmed" (adapter_runtime.py:480-490). Service maps: INVALID⇒400, FAILURE or not durable⇒503, else 200 (service.py:109-137).
Sequential order before 200: normalize → `submit_raw` → `EventFactory.create_event` → `EventPipeline.process` (atomic commit + inline post-commit consumers) → probe `exists(event_id)` → 200. Therefore 200 guarantees canonical-event durability ONLY, plus an inline best-effort attempt at downstream delivery (see F11/F11b).
Restart/recovery per source: (i) transactional outbox with stale-IN_FLIGHT reclaim, bounded backoff, DEAD_LETTER (delivery_dispatcher.py:18-33, :106-178); (ii) startup projection catch-up, idempotent via durable checkpoint, stops at the first failed event (bootstrap.py:152-185, catch_up.py:7-23) — this heals the ENTITY projection only; (iii) the ingress itself holds no queue: the telegram source leaf returns no events and the path is synchronous (composition.py:30-37), so missed webhooks rely entirely on Telegram's own retry; (iv) no observation catch-up exists.

C. Event identity / persistence / outbox
Identity: `chat_id`+`message_id`, both stringified by the normalizer, joined by `_native` with per-component JSON canonicalization and a fixed UUID5 namespace (event_identity.py:36,39-63,81-84,191). Stable and deterministic; no UUID4/invented fallback (normalizer.py:40-43). DB-level `unique=True, index=True` on both `event_id` and `seq` (durable_event_model.py:70-83) plus `UniqueConstraint("event_id")` (:117-119). Event+outbox atomicity: single session, single commit (sqlalchemy_event_repository.py:165-201). Rollback on failure: `DatabaseSessionManager.session()` commits on success, rolls back and re-raises on exception (session.py:257-278). `exists(event_id)` is a meaningful durable read: a separate session reading the committed row (sqlalchemy_event_repository.py:271-279). Idempotency verdict: FULLY SUPPORTED for duplicate canonical events at the durable-row level; AT-LEAST-ONCE (not exactly-once) for consumer side effects, by explicit design (delivery_dispatcher.py:8-16); multiple processes could still duplicate WORK (consumer invocation) although not durable event rows — and the unhandled seq race is the concrete risk (F7b/F9).

D. SQLite concurrency and durability
QueuePool for file SQLite: session.py:175-185. check_same_thread=False: session.py:160-162 (and again explicitly at :184; note the :162 `connect_args` nested inside `connect_args` is dead code — pre-existing, harmless). WAL: ABSENT. busy_timeout: ABSENT. `MAX(seq)+1`: sqlalchemy_event_repository.py:102-112. Uniqueness/race: UNIQUE(event_id) idempotent path is deliberate; UNIQUE(seq) is the only guard on the read-modify-write and its violation is mis-classified as a duplicate (F7b). "database is locked" handling: present ONLY in the schema-migration path (`_is_sqlite_locked`, schema_migration.py:424-449, bounded retry), NOT in the canonical write path — there, an OperationalError propagates out of `pipeline.process` and is converted to FAILURE⇒503 with no in-process retry (partial mitigation via fail-closed ACK + external Telegram retry). Design assumption: one long-lived writer process with one DatabaseSessionManager engine; multiple independent writer processes are NOT supported by any evidence and NOT tested.
RUNTIME-ONLY items marked NOT VERIFIED — TEST EXECUTION PROHIBITED: actual multi-process lock contention, WAL-behaviour under load, and whether the seq race can be triggered in practice were not executed.
Verdict on the managed-VM recommendation: SUPPORTED ONLY WITH EXPLICIT CONDITIONS — exactly as WO-089 states. Conditions: (1) close the writer question with evidence — either enable and prove `journal_mode=WAL` + `busy_timeout` under a proven single-writer set, or move to a server database; (2) never run two DatabaseSessionManager writers against one SQLite file; (3) make the durable write path distinguish/retry a seq collision instead of treating it as a duplicate. Trade-off, stated without prescriptiveness: a controlled single-writer SQLite deployment on a managed VM is coherent and low-cost and matches the code (single owner, loopback bind, local volume); PostgreSQL is not dependency-justified by the code today, but becomes the honest choice for any multi-process topology (multiple ingress workers, more adapters, HA) — the repository is already shaped for it (String(36) UUID identity, QueuePool, PLATFORM_READINESS.md:23,104).

E. Migration and schema initialization
Actual invocation: the ingress calls `initialize_database(database_url=config.database_url, create_tables=True)` (telegram_ingress/app.py:154; identical in whatsapp_ingress/app.py:162 and main.py:243) ⇒ `DatabaseManager.initialize(create_tables=True)` ⇒ `create_tables()` ⇒ `Base.metadata.create_all(bind=self.engine)` (database.py:97-116). Alembic config/revisions in tracked files: NONE (no alembic.ini, no versions/, no script.py.mako; `git ls-tree -r --name-only HEAD | grep -ci alembic` → 0) although alembic IS a declared dependency (requirements.txt) and is installed in .venv (site-packages/alembic) because migration.py imports alembic.command at import time. Custom registry: schema_migration.py MIGRATIONS/upgrade_schema exists but is invoked only from tests. Competing mechanisms: three (Alembic-based MigrationManager, WO-021 revision registry, raw sqlite3 executescript in entity_repository/migration.py) plus create_all bootstrap. Fresh-DB startup: supported (create_all). Deterministic upgrade of an existing production DB: NOT supported by the inspected startup path and NOT documented. Migration failure vs webhook acceptance: the ingress configures the DB at build time and fails closed before serving; there is no runtime migration step that could fail per-request. Verdict: "a migration mechanism exists in the repository" ≠ "the deployed service reliably runs versioned migrations" — the latter is FALSE today.

F. Downstream delivery and operator-visible state — the precise meaning of HTTP 200
200 means: request accepted AND canonical event durably committed AND its outbox delivery records committed AND `exists(event_id)` true. It does NOT mean: downstream consumer delivery completed (invocation is synchronous and inline, but failure is recorded to the outbox, not propagated), Observation persisted (mapping rejection returns success=False without raising, service.py:415-439 + processor.py:226-231), or operator Wall visibility achieved. Failure mode that leaves a durable event not visible: observation-mapping rejection (or any observation-side persistence failure that the service absorbs) ⇒ outbox record marked DELIVERED by the dispatcher `else` branch (event_pipeline.py:221-223) ⇒ never retried ⇒ absent from the operator read model, with no catch-up path to heal it. This is a genuine, non-fabricated gap consistent with (and slightly stronger than) WO-089's boundary statement.

G. Deployment architecture comparison (three models WO-089 considered)
Compatibility with the current ingress entrypoint: A (managed VM + systemd/supervisor + TLS proxy) — highest, the code already assumes exactly this shape (loopback bind + separate process + local store); B (containers on one host) — high, but requires a net-new Dockerfile (none exists) and a real volume for the store, never container FS; C (managed container/app platform) — lowest: ephemeral/scale-to-zero FS is incompatible with the current durable SQLite store, and would force an unauthorized PostgreSQL migration. Persistent local SQLite provided safely: A and B plausible; C poor. Single-writer vs multi-process: identical, unresolved constraint for all three (F8/F9). Secret injection: A = 0600 env/systemd credentials; B = compose/platform secrets; C = native secret manager (best). TLS/public isolation: A/B full control (publish only 443); C platform-managed. Backup/restore: A/B scriptable with off-host copy; C managed snapshots but only if the DB is managed. Migrations: NO model is ready today — all three inherit F10 (no revision-tracked deploy-time step). Health/supervision: `/healthz` exists (app.py:132) but no supervisor exists in any model (F1). Monitoring: absent in all three; application loggers only. Operational complexity: A low–medium, B medium, C medium–high. No vendor, cost, domain, host or account has been invented here, and none is evidenced in the repository.

H. Tests and evidence quality
Relevant file: backend/tests/test_wo083_telegram_ingress.py — 902 lines, 47 `def test_` (counted from the file: `grep -c 'def test_'` → 47). Behaviours represented: secret/401 matrix (01,02,03,03b,04,04b), 400 paths (05,07,07b,08,09), deterministic identity + no UUID4 fallback (10–14b), durable-before-ACK (15,16), 503 on failure/unconfirmed (17,18), duplicate ⇒ one durable event (19/20/21), restart-no-duplicate (22), canonical-path component reuse (23–26), webhook→observation and operator read-model visibility (27c,27d), media reference-only (28,28b,29), architectural guards (30–34: no legacy EventBus, no direct DB/observation write, no secret leakage), additive-scope guards (35–38). Coverage gaps relevant to production safety: NO 413/oversized-body test (0 hits for "413" under backend/tests; "max_body_bytes" appears only in production source); NO multi-process SQLite contention test; NO `database is locked` recovery test for the canonical write path; NO migration-upgrade-from-existing-DB test at the ingress/main entrypoint; NO test for the observation-mapping-rejection ⇒ invisible-observation path. Every test in this report is READ ONLY — NOT EXECUTED. No test is claimed to pass merely because a test function exists.

────────────────────────────
ARCHITECTURE DECISION

Option A (managed VM, systemd-supervised ingress on 127.0.0.1:8030, TLS-terminating reverse proxy publishing only 443, durable store on a dedicated local volume) is APPROVED CONDITIONALLY, as a provisional default only. It may not be treated as ratified architecture until its own named conditions are closed, specifically: the §13 writer/serialization question resolved with evidence (WAL+busy_timeout with a proven single writer, or a server database); exactly one long-lived writer against the store; a revision-tracked schema step at deploy time instead of create_all on a live DB; backup + rehearsed restore with documented RPO/RTO; and the oversized-request follow-up closed. Options B and C are not disqualified but carry strictly more preconditions (B: net-new image + real volume; C: forced DB migration currently unauthorized). The architecture decision is NOT FINAL — the report says so, and the evidence supports that it must remain open.

────────────────────────────
BLOCKERS BEFORE PROVISIONING

1. No authorized production host, credential, or access route exists from this environment (F1).
2. No approved deployment mechanism exists in the repository (ADR-010:146; F1).
3. Multi-process SQLite write safety is UNPROVEN, and inspection reveals a concrete latent defect (seq UNIQUE collision mis-classified as a duplicate; orphan outbox rows on that path; no lock handling in the canonical write path) (F7b, F8, F9).
4. DNS/TLS/edge/supervision/production DB/monitoring/secret-injection are all unestablished and re-confirmed NO-GO (WO-085).
5. Repository gaps a deployment would expose: no backup/restore, no revision-tracked runtime migration, no supervised service definition, no 413 test, no Telegram env template.
6. Two WO-089 statements must be corrected before any operator relies on them for operability planning: the observation/wall failure attribution (F11b) and the container gateway detail (F16b) — plus the under-stated items F4b and F7b.

────────────────────────────
TESTS NOT EXECUTED

backend/tests/test_wo083_telegram_ingress.py (47 tests) — READ ONLY, NOT EXECUTED.
backend/tests/test_wo080_whatsapp_ingress.py — READ ONLY, NOT EXECUTED (keyword scan only).
backend/tests/test_wo021_schema_migration.py, test_wo022/023/024/027_*migration* — READ ONLY, NOT EXECUTED.
Repository-wide grep evidence for the 413 gap and the multi-process gap — READ ONLY, NOT EXECUTED.
No migration was applied, no database was created or written, no service or container was started, no webhook was registered, no Telegram/Meta API was contacted.

────────────────────────────
FILES READ (repository, at HEAD 10c0309, via git show/grep/ls-tree — read-only)

backend/app/telegram_ingress/{app,config,secret,service,normalizer,composition,entrypoint}.py
backend/app/event_sources/runtime/adapter_runtime.py
backend/app/event_sources/identity/event_identity.py
backend/app/event_pipeline/event_pipeline.py
backend/app/event_repository/durable/{sqlalchemy_event_repository,durable_event_model}.py
backend/app/event_delivery/delivery_dispatcher.py
backend/app/database/{session,database,schema_migration,migration}.py
backend/app/entity_repository/migration.py
backend/app/{composition,bootstrap}.py, backend/main.py
backend/app/observation/{service,processor}.py, backend/app/event_bus/event_bus.py
backend/app/projection/catch_up.py
backend/tests/test_wo083_telegram_ingress.py, backend/tests/test_wo080_whatsapp_ingress.py
backend/requirements.txt, backend/.env.example
docs/work_orders/WO-084-…, docs/work_orders/WO-085-…
docs/adr/ADR-010-Production-Source-Configuration.md, docs/PLATFORM_READINESS.md

Non-repository, non-mutating reads: /opt/data/output/WO-089-PRODUCTION-HOSTING-ARCHITECTURE-AND-DEPLOYMENT-READINESS-DESIGN-GATE.md; ~/.ssh/config; hostname; /proc/1/comm; /.dockerenv; /proc/net/tcp; /proc/net/route.

────────────────────────────
FILES CHANGED: NONE
Repository worktree porcelain byte-identical before and after (sha256 c380c4a9…), including the protected `?? 500` (observed only as porcelain text) and the pre-existing modified tracked `.pyc`. Nothing staged (`git diff --cached --stat` empty). No file created in the repository; this audit report is produced as chat output only.

────────────────────────────
INFRASTRUCTURE ACTIONS: NONE
No provisioning, no service/container launch or restart, no container build, no OS change, no DNS/TLS/webhook/Telegram operation, no production probe. All local inspection was file-read only.

────────────────────────────
COMMIT/PUSH: NONE
HEAD, local main, and live origin/main all remain 10c030900207cbaa928d2ea06c753506a4f04ab4 (`git ls-remote origin` re-checked at the end). No branch created, no staging, no commit, no push, no fetch/pull/checkout/reset/clean/stash.

STOP — awaiting explicit operator authorization for any subsequent work order.
---- END UNALTERED SOURCE REPORT BODY ----
