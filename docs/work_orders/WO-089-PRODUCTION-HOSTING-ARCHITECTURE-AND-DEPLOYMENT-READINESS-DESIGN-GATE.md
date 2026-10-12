# WO-089 — TACTICAL_CORE PRODUCTION HOSTING ARCHITECTURE & DEPLOYMENT READINESS DESIGN GATE

**Type:** READ-ONLY DISCOVERY + PROPOSED DESIGN (no implementation, no commit, no push)
**Repository:** `yarem44uk/TACTICAL_CORE` · local `/opt/data/tactical_core_github` · remote `git@github.com:yarem44uk/TACTICAL_CORE.git`
**Inspection window (UTC):** 2026-10-12T12:44:47Z → 2026-10-12T12:45:16Z

---

## 1. STATUS

`BLOCKED — PRODUCTION ACCESS NOT ESTABLISHED`

A complete, repository-grounded, provider-neutral hosting design and readiness checklist
were produced (sections 12–18). Production access, however, remains unestablished: the
inspected environment is a Hermes sandbox Docker container with no authorized route to
any TACTICAL_CORE production host. Therefore no provisioning WO may be authorized yet.
Nothing was deployed, no webhook was registered, no Telegram API call was made.

---

## 2. BASELINE

| Item | Observed | Evidence |
|---|---|---|
| UTC timestamp | `2026-10-12T12:44:47Z`, `2026-10-12T12:45:16Z` | `date -u` (rc=0) |
| hostname | `769d3b0303ca` (container id, no FQDN) | `hostname` |
| PID 1 | `s6-svscan` | `cat /proc/1/comm` |
| container marker | `/.dockerenv` present | `test -f /.dockerenv` |
| cwd | `/opt/data/tactical_core_github` | `pwd` |
| branch | `main` | `git branch --show-current` (rc=0) |
| HEAD | `10c030900207cbaa928d2ea06c753506a4f04ab4` | `git rev-parse HEAD` |
| origin/main (cached ref) | `10c030900207cbaa928d2ea06c753506a4f04ab4` | `git rev-parse refs/remotes/origin/main` |
| origin/main (live) | `10c030900207cbaa928d2ea06c753506a4f04ab4` | `git ls-remote origin refs/heads/main` (rc=0) |
| HEAD == expected baseline | YES | expected `10c0309…`, got `10c0309…` |
| HEAD == live origin/main | YES | both `10c0309…` |

`git status --porcelain=v1` (pre-existing, identical before and after this WO — nothing was
staged, restored, cleaned or modified):

```
 M backend/app/plugins/manager/__pycache__/plugin_manager.cpython-313.pyc
?? 500
?? backend/tests/test_wo080_audit_idempotency.py
?? backend/tests/test_wo080_whatsapp_audit_corrective.py
?? docs/adr/ADR-015-WhatsApp-Ingress-Architecture.md
?? docs/work_orders/WO-078-WHATSAPP-INBOUND-HTTPS-ARCHITECTURE-GATE.md
?? docs/work_orders/WO-079-WHATSAPP-INGRESS-ARCHITECTURE-DECISION-GATE.md
```

Notes recorded, not resolved:
* `ADR-015`, `WO-078`, `WO-079` exist **on disk but are UNTRACKED** (not in HEAD). Their
  content was readable and was used as context; they are **not** part of the published tree.
* `?? 500` is a protected worktree artifact. Observed by `status` only — never opened,
  hashed, stat-ed or staged.
* No `WO-086` file exists in HEAD. WO-086's deliverable is the reconciliation commit
  `10c0309 docs: reconcile WO-081 through WO-085 history` (top of `git log --oneline`).
* WO-084 / WO-085 exist at HEAD as documented (verified via `git ls-tree`/`git show`).

Documents verified present at HEAD (paths exact):
`docs/work_orders/WO-080-WHATSAPP-INGRESS-IMPLEMENTATION.md`,
`WO-081-WHATSAPP-INGRESS-INDEPENDENT-E2E-VERIFICATION.md`,
`WO-082-TELEGRAM-INGRESS-ARCHITECTURE-DECISION-GATE.md`,
`WO-083-TELEGRAM-INGRESS-IMPLEMENTATION.md`,
`WO-084-TELEGRAM-PRODUCTION-READINESS-DEPLOYMENT-GATE.md`,
`WO-085-TELEGRAM-PRODUCTION-INFRASTRUCTURE-PHASE-A-GATE.md`; `docs/PLATFORM_READINESS.md`;
`docs/adr/ADR-010-Production-Source-Configuration.md`, `ADR-011-Operator-Web-Realtime-Architecture.md`.

---

## 3. ENVIRONMENT IDENTITY

**Classification: `CONFIRMED_NON_PRODUCTION`** (positive evidence of a sandbox, not merely
`UNKNOWN`).

Evidence: hostname is a 12-hex container id; `/.dockerenv` present; PID 1 is `s6-svscan`;
Docker embedded DNS `127.0.0.11`; container IP `172.18.0.4` with gateway `172.17.0.1`;
no `python -m app.telegram_ingress.entrypoint`, no uvicorn, no systemd/supervisord; only
Hermes gateway services under `/run/service`; nothing listening on 8030/8020/80/443.

Nothing in this environment links it to an intended TACTICAL_CORE production deployment.
Per WO-085 (unchanged and re-confirmed here): `PUBLIC_FQDN: NOT_FOUND`, `HTTPS: NOT_FOUND`,
`EDGE/REVERSE_PROXY: NOT_FOUND`, gate verdict `NO-GO`.

---

## 4. PRODUCTION ACCESS PATH

`ABSENT` — no authorized production host, account, or access route is reachable.

* `~/.ssh/config` contains exactly one alias: `github.com` (deploy key). No production
  host, no bastion, no jump host. No hostname was guessed and no SSH attempt was made.
* Repository-wide sweep (`git ls-tree -r --name-only HEAD`, 790 files) finds **no**
  Dockerfile, docker-compose, systemd unit, nginx/Caddy/Traefik/HAProxy config, k8s/helm/
  terraform/ansible. Only `.github/workflows/severity-governance.yml` (a governance CI job).
* `ADR-010` states the verified fact: *"No deployment model exists (verified: no
  Docker/systemd/service/deploy files)"*.
* `backend/.env.example` is the only env template and declares **no** `TELEGRAM_*`,
  `WHATSAPP_*`, `WEBHOOK_*` or public-host variable (verified by `git grep -niE 'TELEGRAM|WEBHOOK_SECRET|X-Telegram' HEAD -- backend/.env.example` → **0 hits in that file**).

Per §5 of the WO, infrastructure probing stops here.

---

## 5. PREREQUISITE MATRIX

| # | Prerequisite | Verdict | Evidence / limitation |
|---|---|---|---|
| 1 | Identified production host/target | `ABSENT` | not in repo; WO-084 "Public URL UNKNOWN — must not be invented"; WO-085 `PUBLIC_FQDN NOT_FOUND` |
| 2 | Authorization + usable access path | `ABSENT` | only a GitHub deploy key in `~/.ssh/config` |
| 3 | Approved deployment mechanism | `ABSENT` | ADR-010 verified: no deployment model |
| 4 | Public webhook FQDN | `ABSENT` | `PUBLIC_FQDN NOT_FOUND` (WO-085 §63, §99) |
| 5 | DNS resolution for that FQDN | `NOT CHECKED` | no authorized FQDN exists to resolve |
| 6 | HTTPS/TLS endpoint + cert | `ABSENT` | `uvicorn.run(app, host, port)` — no `ssl_*` args (`entrypoint.py:78`); 443 not bound |
| 7 | Reverse proxy / ingress edge | `ABSENT` | no proxy config in tree; WO-084 "NOT FOUND IN REPOSITORY" |
| 8 | Route to ingress process | `ABSENT` | nothing listening on 8030 |
| 9 | Inbound firewall/NAT | `NOT CHECKED — OUTSIDE AUTHORIZATION` | no host/network access |
| 10 | Python/runtime + app deployment prereqs | `PARTIALLY PRESENT (local only)` | repo + `.venv` exist locally; not deployed anywhere |
| 11 | Supervised service definition | `ABSENT` | no systemd unit / supervisor / container spec |
| 12 | Port binding + process on intended host | `ABSENT` | default bind `127.0.0.1:8030` is an application default, not reachability |
| 13 | `TELEGRAM_WEBHOOK_SECRET` presence | `ABSENT` | env var unset in this process; name-only check, value never read/printed |
| 14 | Production database config/availability | `ABSENT` | `DATABASE_URL` unset in env; only `sqlite:///./storage/database/tactical_core.db` in `.env.example` |
| 15 | Durable event persistence prereqs | `ABSENT` at production scope | code path exists and is fail-closed; no deployed store |
| 16 | Log collection / monitoring | `ABSENT` | no exporter/agents/alerting; in-app `/healthz` + loggers only |
| 17 | Health check / restart policy | `ABSENT` | `/healthz` exists (`app.py`), no supervisor to consume it |
| 18 | Approved webhook-registration process | `ABSENT` | WO-085 Phase B not entered; no authorization |
| 19 | Approved live E2E procedure | `ABSENT` | WO-085 Phase B not entered |
| 20 | Oversized-request follow-up (1 MiB, no 413 test) | `PRESENT as a GAP` | `DEFAULT_MAX_BODY_BYTES = 1024*1024` + 413 branch in `app.py`; `git grep -n '413\|max_body\|oversize\|too large'` over `backend/tests/test_wo083_telegram_ingress.py` (902 lines, 47 tests) → **0 hits**. Still no automated 413 test. |
| 21 | Env-example/doc completeness for Telegram settings | `ABSENT` | `backend/.env.example` has no `TELEGRAM_*`; the ingress's real env contract lives only in module docstrings |

---

## 6. APPLICATION CONTRACT CROSS-CHECK (source read at HEAD; tests read, NOT executed)

Files read: `backend/app/telegram_ingress/{app,config,secret,service,composition,entrypoint,normalizer}.py`,
`backend/app/event_sources/runtime/adapter_runtime.py`,
`backend/app/event_pipeline/event_pipeline.py`,
`backend/app/event_repository/durable/{sqlalchemy_event_repository,durable_event_model}.py`,
`backend/app/database/{session,database,schema_migration,migration}.py`,
`backend/app/bootstrap.py`, `backend/app/composition.py`, `backend/main.py`,
`backend/tests/test_wo083_telegram_ingress.py`.

* **Route** — `POST /telegram/webhook` (`TELEGRAM_WEBHOOK_PATH`) + `GET /healthz`; FastAPI
  (`app.py`). No Flask anywhere; FastAPI+uvicorn is the accepted runtime pattern (ADR-011,
  ADR-015, WO-080).
* **Auth** — `X-Telegram-Bot-Api-Secret-Token` vs configured `secret_token`, constant-time
  `hmac.compare_digest`, empty/missing/mismatch ⇒ `401`. Deliberately **not** HMAC
  (Telegram does not sign the body) — `secret.py`. VERIFIED.
* **Fail-closed config** — missing `TELEGRAM_WEBHOOK_SECRET` or `DATABASE_URL` ⇒
  `TelegramIngressConfigError` before any resource is acquired (`config.py:from_env`). VERIFIED.
* **Payload validation / size** — non-dict or malformed JSON ⇒ `400`; `len(raw) > max_body_bytes`
  ⇒ `413 {"detail":"payload too large"}`; ceiling 1 MiB. VERIFIED in code; NOT verified by test.
* **Deduplication** — deterministic identity (`chat_id`+`message_id` → uuid5, fixed namespace);
  `IngestStatus.DUPLICATE` ⇒ HTTP 200 with `duplicate=true`; DB `UNIQUE(event_id)`. VERIFIED.
* **Durable ACK boundary** — `AdapterRuntime.submit_raw`: `durable=True` only when the
  configured durability probe confirms the `event_id` is durable; probe absent ⇒ never durable.
  `IngressService` maps `INVALID→400`, `FAILURE` or `not durable→503`, else `200`. VERIFIED.
* **Persistence failure surfaced** — `submit_raw` does **not** swallow; a pipeline exception
  ⇒ `IngestResult(FAILURE)` ⇒ 503 ⇒ Telegram retries. VERIFIED.
* **Tests** — `test_wo083_telegram_ingress.py`, 47 `def test_` (secret/401, malformed JSON,
  identity determinism, durable-before-ACK, 503 on unconfirmed durability, restart-no-duplicate,
  webhook→observation, operator read-model visibility, no legacy EventBus, no direct DB write).
  **NOT EXECUTED** — deliberately skipped (read-only gate; avoids worktree mutation / deps /
  external access). Represented as NOT CHECKED, never as passed.
* **Coverage gaps** — no 413/oversized-body test; dedup exercised largely indirectly; no test
  asserts multi-process SQLite behaviour.

---

## 7. EVIDENCE LOG (representative; all commands read-only)

| Command / path | Result | Classification |
|---|---|---|
| `date -u`, `hostname`, `cat /proc/1/comm`, `test -f /.dockerenv` | sandbox identity | VERIFIED |
| `git rev-parse HEAD`, `git ls-remote origin refs/heads/main` | `10c0309…` both | VERIFIED |
| `git status --porcelain=v1` | pre-existing 1 M + 6 ?? | VERIFIED |
| `git ls-tree -r --name-only HEAD` (790 files) | no Docker/systemd/proxy/alembic deploy files | VERIFIED |
| `git show HEAD:backend/app/telegram_ingress/app.py` | route, 413, 401, 400, ACK map | VERIFIED |
| `git show HEAD:backend/app/telegram_ingress/config.py` | required secret + DATABASE_URL, 1 MiB, port 8030 | VERIFIED |
| `git show HEAD:backend/app/database/session.py` | SQLite file ⇒ `QueuePool(pool_size=5, max_overflow=10)`, `check_same_thread=False`; no PRAGMA tuning | VERIFIED |
| `git grep -niE 'journal_mode\|busy_timeout\|WAL\|pragma' HEAD -- backend/app` | ONLY `PRAGMA table_info(observations)` in `schema_migration.py` — **no WAL, no busy_timeout** | VERIFIED (absence) |
| `git show HEAD:…/sqlalchemy_event_repository.py` | `_next_seq = MAX(seq)+1`; `save` swallows `IntegrityError` as idempotent duplicate | VERIFIED |
| `git show HEAD:…/schema_migration.py:415-445` | repo itself acknowledges transient SQLite `database is locked` contention | VERIFIED |
| `git show HEAD:backend/.env.example` | no `TELEGRAM_*`; `DATABASE_URL=sqlite:///./storage/database/tactical_core.db` | VERIFIED |
| `git grep -n '413\|max_body\|oversize\|too large' …/test_wo083_telegram_ingress.py` | 0 hits (902-line file, 47 tests) | VERIFIED (absence) |
| `git grep -n 'upgrade_schema\|initialize_database' HEAD` | ingress + `main.py` call `initialize_database(create_tables=True)` only | VERIFIED |
| DNS/TLS/firewall on any production host | not attempted | NOT CHECKED — OUTSIDE AUTHORIZATION |
| Test suite execution | not run | NOT CHECKED |
| Multi-process SQLite write safety | no repository evidence either way | UNKNOWN — REQUIRES VERIFICATION |

---

## 12. PROPOSED ARCHITECTURE — DESIGN ONLY (not implemented)

Constraint set inherited from evidence: a **public HTTPS edge**; an **isolated ingress
process** (`python -m app.telegram_ingress.entrypoint`, default `127.0.0.1:8030`); **one**
canonical durable store (`durable_canonical_events` + outbox) owned by exactly one
`DatabaseSessionManager` per process; **commit-before-ACK**; **no second event journal**;
no secrets in Git.

| # | Component | Purpose / required behaviour | Evidence base | Dependencies | Failure modes | Security | Decisions required |
|---|---|---|---|---|---|---|---|
| 1 | Public HTTPS endpoint | `https://<PUBLIC_HOST>/telegram/webhook` reachable by Telegram (443/80/88/8443) | WO-084 §66, WO-085 | public IP, DNS, edge | endpoint down ⇒ Telegram retries then disables webhook | expose ONLY the webhook path | hostname, DNS owner, exposure policy |
| 2 | TLS termination + edge | terminate TLS, `proxy_pass` to `127.0.0.1:8030`; never expose 8030 | WO-084 §61, ADR-015 §113/§136 (TLS DEFERRED) | cert, proxy software | cert expiry ⇒ total outage; misconfig ⇒ bypass of secret header? (no: secret still required) | HSTS, modern TLS, minimal surface | managed vs self-hosted edge; cert source |
| 3 | Isolated Telegram ingress process | FastAPI+uvicorn, separate process from `backend/main.py` and operator | `app.py`, `entrypoint.py`, ADR-011 §4 Option D, ADR-015 §2 | python runtime, DATABASE_URL, secret | crash ⇒ webhook 5xx ⇒ retries | loopback bind only; secret header verification | supervision model (unit vs container) |
| 4 | Secret injection | supply `TELEGRAM_WEBHOOK_SECRET` (+ `DATABASE_URL`) without Git | `config.py:from_env` (env-only, no vault by design) | host-side secret store | missing ⇒ fail-closed refusal to start | file perms 0600 / systemd credentials / platform secret store | mechanism + rotation cadence |
| 5 | Durable persistence + canonical pipeline | `submit_raw → EventFactory → EventPipeline → save_with_deliveries` | `service.py`, `adapter_runtime.py`, `event_pipeline.py:170` | DB reachable + writable | DB down ⇒ 503, no ACK (correct) | DB not publicly reachable | DB engine choice (see §13) |
| 6 | Event-journal / DB ownership | one owner per process; callers must not introduce a second engine | `session.py`, INVARIANT text in `schema_migration.py`, `sqlalchemy_entity_repository.py:11` | — | two engines + SQLite file ⇒ lock contention (see §13) | exclusive DB credentials | how many writers run concurrently |
| 7 | Health, logs, monitoring | `/healthz` (in-app) consumed by supervisor; structured logs shipped; alert on 5xx/persistence failure | `app.py` healthz; `adapter_runtime.py:253 health()` | log shipper, monitor | silent failures if unmonitored | redact secrets (already: no secret logging, masked repr) | monitoring stack, retention |
| 8 | Restart & recovery | supervised restart; deterministic projection catch-up on startup heals un-projected durables | `bootstrap.py:_run_startup_catch_up`, `projection/catch_up.py` | supervisor | crash loop ⇒ volume of Telegram retries | least-privilege service user | restart budget/backoff |
| 9 | Backup & restore | periodic consistent backup of the durable store + restore drill | none in repo (**ABSENT**) | storage tooling | data loss beyond RPO | encrypted backups, off-host | RPO/RTO, retention |
| 10 | Network segmentation | only 443 inbound; DB + 8030 host-local; egress limited | `entrypoint.py` default loopback; ADR-011/015 isolation principle | firewall/VPC | lateral movement if over-exposed | default-deny inbound | firewall policy owner |
| 11 | Deploy / rollback / upgrade | pin a commit, deploy, verify `/healthz`, rollback to pinned commit | no mechanism in repo (**ABSENT**) | CI or documented runbook | bad deploy ⇒ outage | signed/pinned artifacts | pipeline owner, rollback trigger |
| 12 | Operator access & emergency recovery | break-glass console, secret rotation, service stop/disable | none in repo (**ABSENT**) | out-of-band access | lockout | MFA / key-based, audited | access owner, on-call |

---

## 13. DATABASE AND DURABILITY GATE

| Property | Finding | Classification |
|---|---|---|
| Where durable data is written | table `durable_canonical_events` (`DurableCanonicalEvent`) and the delivery outbox, via `SQLAlchemyEventRepository.save` / `save_with_deliveries`, through the single `DatabaseSessionManager` engine | VERIFIED (source) |
| Transactions / commits | `DatabaseSessionManager.session(commit=True)` — commit on success, rollback + re-raise on failure, session always closed. `save_with_deliveries` writes event row + PENDING outbox rows **atomically** | VERIFIED |
| What counts as durable acceptance | the event row is committed **and** the read-only probe `SQLAlchemyEventRepository.exists(event_id)` returns True; `IngestResult.durable` is the single ACK authority | VERIFIED |
| Persistence failure surfaced to HTTP | yes — `submit_raw` catches nothing silently: pipeline exception ⇒ `FAILURE` ⇒ 503 | VERIFIED |
| Event identity / dedup across restart | deterministic uuid5 from `chat_id`+`message_id` (fixed namespace) + DB `UNIQUE(event_id)`; `test_wo083_22_restart_does_not_duplicate` asserts this | VERIFIED (code+tests read) |
| Concurrent writers expected/supported | **no repository evidence.** File SQLite uses `QueuePool(5,10)` + `check_same_thread=False`; **no WAL, no `busy_timeout`**; `seq = MAX(seq)+1` is a read-modify-write guarded only by `UNIQUE(seq)` ⇒ a cross-process race is possible; the repo's own `schema_migration._is_sqlite_locked` treats "database is locked" as a real transient condition | **UNKNOWN — REQUIRES VERIFICATION** |
| Schema migrations defined / applied | three mechanisms exist in code: Alembic (`migration.py`), the WO-021 revision registry (`schema_migration.upgrade_schema`), and `Base.metadata.create_all`. The **actual startup path** used by the ingress (and `main.py`) is `initialize_database(..., create_tables=True)` ⇒ `create_all` only. No `alembic.ini` / `versions/` directory is in the tree | VERIFIED (partially — runtime uses create_all, no revision tracking at startup) |
| Backups / restoration | no backup code, config or documented procedure anywhere in the tree | **ABSENT** |
| HTTP 200 ⇒ end-to-end visibility | Not asserted. 200 implies the **event row is durable**. Downstream observation/wall projection is **best-effort** (`EntityBridge` swallows failures) and is healed by startup catch-up; `test_wo083_27c/27d` cover webhook→observation and operator read-model — read, **not executed** | VERIFIED as a boundary statement |

**Minimum persistence/recovery requirements proposed** (design only, no code change here):
1. Resolve the multi-process SQLite question *before* provisioning: either (a) verify and
   enable `journal_mode=WAL` + `busy_timeout` **and** prove the writer set, or (b) adopt a
   server database (PostgreSQL) for any configuration with more than one writer process.
2. Exactly one long-lived writer process against the store, or an explicit writer-serialization
   mechanism; never two `DatabaseSessionManager` engines racing on one SQLite file unverified.
3. A revision-tracked schema application step at deploy time (`upgrade_schema`/Alembic), not
   ad-hoc `create_all` on a live production database.
4. Nightly consistent backup + a rehearsed restore into a scratch environment; documented RPO/RTO.
5. Disk-capacity and DB-growth monitoring; the store is append-only and unbounded today.

---

## 14. SECURITY AND OPERATIONS GATE

Already supported by existing code (VERIFIED): constant-time static-secret verification with
fail-closed behaviour; fail-closed startup on missing secret / missing `DATABASE_URL`;
1 MiB body ceiling + 413; JSON/shape validation → 400; commit-before-ACK → 503;
deterministic dedup + `UNIQUE(event_id)` and outbox `UNIQUE(event_id, consumer_id)`;
no secret logging; loopback default bind; read-only `/healthz`; fail-closed durable delivery.

Requires infrastructure or future implementation (ABSENT): public HTTPS + certificate
lifecycle; DNS; reverse proxy/edge; inbound firewall/NAT; secret store + rotation; supervised
service with restart policy; log collection, redaction and retention; process/persistence/
repeated-webhook-failure monitoring; disk-capacity monitoring; backup integrity + restore
testing; least-privilege service identity; database access restriction; software update and
rollback procedure; incident response and operator access path. No standard or SLA compliance
is claimed anywhere — none is evidenced.

---

## 15. PROVIDER-NEUTRAL OPTIONS

| Criterion | A. Managed VM + supervised processes | B. Containers on one host | C. Managed container/app platform |
|---|---|---|---|
| Operational complexity | low–medium (systemd + proxy + OS patching) | medium (images, registry, volumes, compose) | medium–high (platform abstractions, IAM, cold starts) |
| Persistent storage / DB suitability | good: local disk or attached volume; SQLite plausible **if** the §13 writer question is resolved; PostgreSQL easy | same as A, but the DB must live on a real volume, never in the container FS | poor for SQLite (ephemeral FS, scale-to-zero); effectively requires managed PostgreSQL |
| Network exposure | full control (only 443 published) | full control via port publishing | platform-managed ingress; private networking extra |
| Secret management | env file / systemd credentials (0600), rotation manual | compose secrets / env, rotation manual | native secret manager (best of the three) |
| Backups / restore | cron + offsite copy; simple, scriptable | volume snapshots + offsite | managed snapshots (good), but DB must be managed |
| Logs / monitoring | journald + shipper | docker logs + shipper | platform logs/metrics built in |
| Upgrade / rollback | `git`-pinned commit + restart; rollback by pinning previous commit | image tag rollback | image revision rollback |
| Relative cost category *(qualitative, not a quote)* | low | low–medium | medium–high |
| Compatibility risk with the current runtime | **main risk:** multi-process SQLite (see §13); otherwise high | same SQLite risk; net-new Dockerfile (none exists) | **highest:** SQLite + long-lived supervised process + `127.0.0.1` bind + startup catch-up fit poorly; would force a PostgreSQL migration that is not yet authorized |

**Recommended default (provisional): Option A** — one managed virtual server, systemd-supervised
ingress process on `127.0.0.1:8030`, a TLS-terminating reverse proxy publishing only 443, the
canonical durable store on a dedicated local volume.
**Assumptions:** internet-facing (or behind an existing organizational edge); a single host;
low-to-moderate volume; Telegram as the first production ingress; the operator accepts manual
OS patching. **Condition:** Option A is only defensible once the SQLite multi-process/writer
question in §13 is resolved and the store is either verified-safe in WAL mode with one writer,
or replaced by PostgreSQL (which the code supports — `String(36)` UUIDs, `QueuePool`,
documented "PostgreSQL-ready" in `docs/PLATFORM_READINESS.md`). If that cannot be established,
the evidence is insufficient for a firm recommendation and the decision must return to the
Architect.

---

## 16. OPERATOR DECISIONS (genuinely unresolved)

1. Internet-facing, or behind an existing organizational edge (e.g. an existing FortiGate/firewall)?
2. Does a domain already exist for the public host, or must one be obtained — and who owns DNS?
3. Hosting ownership and administrative responsibility (who patches, who is on call)?
4. Geographic / data-residency constraints on where the durable store may live?
5. Acceptable operational complexity and a qualitative cost ceiling.
6. Required recovery objectives (RPO/RTO) and the acceptable data-loss window.
7. Is Telegram the first production ingress, or part of a larger initial deployment?
8. Production persistence: SQLite (with a proven single-writer/WAL discipline) or PostgreSQL
   (recommended if §13 cannot be satisfied)?

No passwords, bot tokens or private keys are requested.

---

## 17. DEPLOYMENT READINESS CHECKLIST (future gate — all items currently OPEN)

1. Approved architecture (this document reviewed and ratified by the Architect).
2. Authorized hosting owner and named deployment target.
3. Approved provider/account and cost.
4. Public hostname allocated; DNS ownership and records defined.
5. TLS + ingress-edge design approved (cert source, renewal, only-443 exposure).
6. Network/firewall policy approved (default-deny inbound; 8030 and the DB never public).
7. Runtime/package reproducibility (pinned interpreter + `backend/requirements.txt`; no `alembic.ini`/`versions` today).
8. Process supervision + health checks (`/healthz` consumed by a supervisor with restart policy).
9. Secret injection + rotation (`TELEGRAM_WEBHOOK_SECRET`, `DATABASE_URL`; never in Git).
10. Database ownership + migration (single writer OR PostgreSQL; revision-tracked schema step at deploy).
11. Backup + **rehearsed restore** with documented RPO/RTO; disk-growth monitoring.
12. Log collection with redaction + retention; monitoring for process health, persistence failure and repeated webhook failure.
13. Oversized-request follow-up closed: an automated 413 test for the documented 1 MiB limit (gap 20 in §5).
14. `backend/.env.example` (or equivalent) documents the Telegram-specific settings (gap 21 in §5).
15. Approved webhook-registration procedure (still NOT authorized).
16. Approved live end-to-end test procedure, with rollback and webhook deletion steps.
17. Deploy/rollback/upgrade runbook with a pinned commit and a rollback trigger.

**Gate condition before any provisioning WO may be authorized:** items 1–6, 9, 10 and 11 must
be explicitly decided by the operator, and the §13 writer/serialization question must be closed
with evidence — otherwise provisioning would encode an unverified assumption into production.

---

## 18. BLOCKERS

1. No authorized production host, credential, or access route exists from this environment.
2. No approved deployment mechanism exists in the repository (ADR-010, verified).
3. `UNKNOWN — REQUIRES VERIFICATION`: multi-process SQLite write safety (no WAL/busy_timeout,
   `MAX(seq)+1` race, repo's own lock-contention acknowledgement).
4. All of DNS/TLS/edge/supervision/production DB/monitoring/secret-injection are unestablished
   (WO-084/WO-085, re-confirmed).
5. Repository gaps that a production deployment would expose: no backup/restore, no revision-tracked
   runtime migration, no supervised service definition, no 413 test, no Telegram env template.

---

## 19. RECOMMENDED NEXT ACTION

Single smallest safe next step: **the operator answers decisions 1–3 and 8 of §16** — i.e.
states (a) whether the ingress will be internet-facing or behind an existing edge, (b) whether a
domain exists and who owns DNS, (c) who owns the host, and (d) SQLite or PostgreSQL. Those four
facts collapse the design space and close the only structurally-ambiguous item (§13). No
credentials are needed for that answer. A provisioning WO must not be authorized until §17
gates 1–6, 9, 10 and 11 are decided.

---

## 20. FILES CHANGED

**NONE in the repository.** No repository file was created, edited, renamed or deleted. The
worktree porcelain is byte-identical to the pre-run snapshot, including the protected `?? 500`
and the pre-existing modified `.pyc` (neither opened, hashed, stat-ed, staged nor restored).
The only file written this WO is this report, outside the repository, at
`/opt/data/output/WO-089-PRODUCTION-HOSTING-ARCHITECTURE-AND-DEPLOYMENT-READINESS-DESIGN-GATE.md`.

## 21. GIT OPERATIONS

**NONE.** No commit, push, pull, fetch, merge, rebase, cherry-pick, reset, checkout, clean,
stash or branch creation occurred. `HEAD` remains `10c030900207cbaa928d2ea06c753506a4f04ab4`
and live `origin/main` remains `10c030900207cbaa928d2ea06c753506a4f04ab4` — unchanged.
No test suite was executed; no unexecuted test is represented as passed.

**STOP.** No provisioning, no deployment, no Telegram API call, no webhook registration, no
infrastructure change, and WO-090 was not started.
