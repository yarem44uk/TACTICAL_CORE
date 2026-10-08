# WO-083 — Telegram Ingress Implementation

**Status:** `ACCEPTED` (local implementation verified) — then independently audited: `ACCEPTED` (read-only)
**Reconstructed by:** WO-086 (documentation-only reconciliation)
**Repository:** `yarem44uk/TACTICAL_CORE`
**Branch:** `wo-083-telegram-ingress-implementation`
**Baseline:** `1fb1482bd5b57a3a41543362152c61e8f17a8ea5`

> **Reconstruction note.** Historical documentation reconstructed from existing evidence
> only. WO-083 is already represented by real Git commits; the SHAs below were
> independently re-confirmed live against the repository during WO-086. No new
> implementation commit was created. Source: live Git + the implementation and
> independent-audit reports preserved in the local Hermes session store.

---

## Status

Implementation report: `ACCEPTED` — claim limited to *"WO-083 local implementation
verified"*. Independent read-only audit: `ACCEPTED`.

Both verdicts explicitly cover **local verification only**; live Telegram production
E2E remains `NOT VERIFIED`.

## Purpose

Implement exactly the bounded Telegram Ingress slice defined by the WO-082
architecture gate (OPTION A — reuse the canonical ingress architecture), without
broadening scope and without silently modifying shared canonical components.

## Baseline

| Item | Value |
| --- | --- |
| Baseline (WO-080 integration point / WO-082 gate baseline) | `1fb1482bd5b57a3a41543362152c61e8f17a8ea5` |
| Branch | `wo-083-telegram-ingress-implementation` (created from `1fb1482`, **not** `main`) |
| Implementation commit | `71bd972ac14bdfc9a6ef79876f24229fbe071548` |
| Commit subject | `WO-083 implement canonical Telegram ingress` |
| Merge commit | `688e0bbd1116afa70e780f493c44bfffb13317e8` |
| Merge subject | `Merge WO-083 Telegram ingress` |
| Merge parents | `1fb1482bd5b57a3a41543362152c61e8f17a8ea5` , `71bd972ac14bdfc9a6ef79876f24229fbe071548` |

Live re-confirmation during WO-086:

- `git cat-file -t 71bd972…` → `commit`
- `git log -1 --format='%H %P %s' 688e0bb…` → `688e0bbd… 1fb1482… 71bd972… Merge WO-083 Telegram ingress`
- `git ls-remote origin refs/heads/main` → `688e0bbd1116afa70e780f493c44bfffb13317e8`

The remote branch `refs/heads/wo-083-telegram-ingress-implementation` is **absent** on
origin (`git ls-remote` empty) — consistent with the implementation report stating the
branch was committed locally and **not pushed**.

## Scope

Bounded first vertical slice: `message` update type only; text and reference-only media
descriptors; duplicate delivery idempotency. Per the WO-082 gate this explicitly excluded
`edited_message` / `edited_channel_post` (identity gap), `channel_post`, `callback_query` /
`inline_query` / `business_*` / `poll` / `message_reaction`, and any media-byte download.

## Evidence

Changed files — `git diff --name-status 1fb1482… 71bd972…` (live, WO-086):

```
M   backend/app/event_sources/config/production_source_config.py
A   backend/app/telegram_ingress/__init__.py
A   backend/app/telegram_ingress/app.py
A   backend/app/telegram_ingress/composition.py
A   backend/app/telegram_ingress/config.py
A   backend/app/telegram_ingress/entrypoint.py
A   backend/app/telegram_ingress/normalizer.py
A   backend/app/telegram_ingress/secret.py
A   backend/app/telegram_ingress/service.py
A   backend/tests/test_wo083_telegram_ingress.py
```

`git diff --shortstat` → **10 files changed, 1906 insertions(+)**, 0 deletions. Single
commit. The only pre-existing tracked file touched is
`production_source_config.py`, additively (`+38`, `build_telegram_source_definition()`
only; the catalog is unchanged). `backend/main.py` diff is **empty**.

## Verification

Implementation report (recorded live results):

- `cd backend && PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.:.. ../.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_wo083_telegram_ingress.py`
  → **47 passed, 1 warning in 4.78s** (RC 0). Warning = pre-existing `StarletteDeprecationWarning` from `fastapi.testclient`.
- Regression over unchanged areas (`test_wo080_whatsapp_ingress.py`,
  `test_wo036_production_source_config.py`, `test_telegram_source_adapter.py`,
  `test_telegram_source_adapter_registration.py`, `test_adapter_runtime.py`,
  `test_wo025_durable_event_identity.py`, `tests/observation`) → 154 passed, 0 failed, RC 0.
- A temporary ad-hoc verification script (created under `/tmp` with an
  `hermes-verify-wo083-` prefix, run against the real canonical composition and a real
  isolated SQLite durable store, then deleted) reported 20/20 PASS, RC 0.

Independent audit (recorded live results):

- Target suite: exit 0 — **47 passed, 1 warning in 4.84s** (Python 3.13.5, pytest 9.1.1).
  The auditor noted it could **not** reproduce the report's "20/20" figure as-is; the live
  target-suite result is 47 collected / 47 passed.
- Neighbour suite (`test_wo080_whatsapp_ingress.py`, `test_wo036_production_source_config.py`,
  `test_telegram_source_adapter.py`, `test_telegram_source_adapter_registration.py`,
  `test_adapter_runtime.py`, `test_wo025_durable_event_identity.py`,
  `test_wo060_observation_read_model.py`) → exit 0 — **125 passed, 1 warning in 3.94s**.
- Full suite: NOT RUN (intentionally).

Verified properties (auditor's PASS list): canonical Telegram path
`receive()` → `verify_secret_token()` → `handle_update()` → `normalize_update()` →
`AdapterRuntime.submit_raw()` → `IEventFactory.create_event()` → `IEventPipeline.process()`
→ `SQLAlchemyEventRepository` → Observation → operator read-model; authentication
(missing/invalid/whitespace-only → 401, zero durable); constant-time comparison
(`hmac.compare_digest`, monkeypatched spy asserts it is the comparison path); no HMAC for
the Telegram body; update normalization (`chat_id` + `message_id` as `str`); supported type
`message` only; identity via the existing `_telegram_identity` policy and existing
`_EVENT_NAMESPACE`; independent UUID5 recomputation:
`chat_id=-100200300, message_id=42 → d7e85908-4bd3-5455-9397-c43c2bdf5d99` (MATCH);
durable-before-ACK; duplicate idempotency (durable-uniqueness based, not a process-local
cache); restart idempotency (**simulation**); retry semantics (503 path); media
reference-only (largest photo preferred; no bytes/`getFile`/`file_path`/base64); Observation
+ Operator Wall (`GET /api/v1/operator/observations?source=telegram` includes the event's
`immutable_id`); no `app.core.event_bus` import in the ingress; no direct DB write or direct
Observation creation; source catalog unchanged (`["radio","signal"]`, `telegram` absent);
shared-component perimeter (empty diff for `backend/main.py`, `observation/canonical_adapter.py`,
`event_sources/runtime/adapter_runtime.py`, `event_sources/identity/event_identity.py`,
`app/whatsapp_ingress/app.py`, `app/connectors/telegram/connector.py`).

## Architecture / Implementation

```
Telegram JSON Update
  → app.py:receive()                         (FastAPI async route)
  → secret.verify_secret_token()             (constant-time; 401 on failure)
  → service.TelegramIngressService.handle_update()   (200 / 400 / 503)
  → normalizer.TelegramUpdateNormalizer.normalize_update()   (Update envelope → raw)
  → AdapterRuntime.submit_raw()              (durability probe = SQLAlchemyEventRepository.exists)
  → EventFactory.create_event() → EventPipeline.process()    (EXISTING, unmodified)
  → SQLAlchemyEventRepository                (durable; UNIQUE(event_id))
  → Observation (CanonicalEventToObservationAdapter) → operator read-model
```

Contract (as implemented): `POST /telegram/webhook` (+ `GET /healthz`); auth header
`X-Telegram-Bot-Api-Secret-Token`; required env `TELEGRAM_WEBHOOK_SECRET` (fail-closed) and
`DATABASE_URL` (fail-closed); defaults `TELEGRAM_HOST=127.0.0.1`, `TELEGRAM_PORT=8030`,
`TELEGRAM_WEBHOOK_PATH=/telegram/webhook`, max body 1 MiB; separate uvicorn process
(`python -m app.telegram_ingress.entrypoint`), independent of `backend/main.py`.

Deliberate deviations, recorded not hidden:

- **Framework.** WO-083 §10 stated "the project uses Flask". There is **zero** Flask in the
  repository; the accepted WhatsApp ingress and the operator API use FastAPI, and
  `fastapi`/`uvicorn` are declared runtime deps in `backend/requirements.txt`. Per §10's own
  escalation clause, FastAPI was used. No new dependency was added. The auditor agreed:
  no unauthorized framework expansion.
- **Unsupported updates.** An authenticated non-`message` Update returns HTTP 400 with a
  deterministic non-secret error and creates zero durable events (never silently
  acknowledged, never turned into an incorrect canonical event).
- **Sender optionality.** `TelegramPayloadNormalizer` requires `sender_id`, but identity is
  `chat_id` + `message_id` only, so the Update normalizer treats `from` as optional
  (channel-sent messages carry no `from`); identity remains strictly required.
- **`text` always emitted** (`""` when neither text nor caption) so the pre-existing
  `telegram.message` observation mapping (required fields `["chat_id","text"]`, unmodified)
  validates for media-only messages.

## Findings

Independent audit findings (verbatim severity):

- **MEDIUM ×1** — `app/telegram_ingress/app.py`: the request-size ceiling
  (`DEFAULT_MAX_BODY_BYTES` = 1 MiB; 413 branch) has **no automated test**; nothing asserts
  413 or "oversized ⇒ zero durable events". Implemented in source, unverified by test.
- **LOW ×3** — (a) the size check runs *after* `await request.body()`, so the full body is
  buffered before the ceiling is enforced, and the 413 check precedes the 401 secret check
  (ordering only; no secret disclosure); (b) `backend/.pytest_cache` present (git-ignored,
  pre-existing); (c) instruction-vs-worktree filename mismatch for the protected WO-080
  audit file (`test_wo080_audit_corrective.py` named in the WO; actual
  `test_wo080_whatsapp_audit_corrective.py`).
- No CRITICAL findings. No HIGH findings. No secret exposure found (secret absent from
  success/rejection/health responses; `config.__repr__` masks it; secret never logged).
- Architecture findings: none blocking — single canonical architecture, thin transport
  boundary over the existing `submit_raw` seam.

Implementation-side notes: no `uuid4` anywhere in the package; no HTTP/TG client library
(`requests`/`httpx`/`urllib.request`/`telebot`/`aiogram`/`aiohttp`) appears in any ingress
source file; `app.core.event_bus` reachable only transitively through the pre-existing
canonical `app/observation/service.py` (a pre-existing property of the shared composition,
not a WO-083 dependency).

## Limitations

- Live Telegram production E2E `NOT VERIFIED`.
- Restart idempotency verified by in-process runtime reconstruction over a real durable
  SQLite store — **not** a real container/process restart.
- 413 branch and the "oversized ⇒ zero durable" guarantee are untested (MEDIUM, open).
- Full backend suite deliberately not run.
- WO-086 §11 note: the WO-083 documentation file is historical documentation only; the
  implementation SHAs above are the real commits and were not re-created.

## Production Gaps

Public DNS + HTTPS host; TLS 1.2+ termination and certificate chain; Telegram-permitted
ports only (443/80/88/8443, or a local Bot API server); firewall allow for Telegram subnets
`149.154.160.0/20` and `91.108.4.0/22`; a real bot token provisioned into the ingress
environment; `setWebhook` registration with `allowed_updates=["message"]` and the
`secret_token`; live acceptance testing against the real Bot API. No live Telegram API call
was made; no bot was created; no webhook was set; no credential was used.

## Git / Repository State

- Implementation commit `71bd972ac14bdfc9a6ef79876f24229fbe071548` (10 files, +1906/-0) on
  branch `wo-083-telegram-ingress-implementation`.
- Merge commit `688e0bbd1116afa70e780f493c44bfffb13317e8` (`Merge WO-083 Telegram ingress`)
  is the current tip of `main` and of `origin/main`.
- Worktree preserved: `git status --porcelain=v1` identical before/after both the
  implementation and the audit —

  ```
   M backend/app/plugins/manager/__pycache__/plugin_manager.cpython-313.pyc
  ?? 500
  ?? backend/tests/test_wo080_audit_idempotency.py
  ?? backend/tests/test_wo080_whatsapp_audit_corrective.py
  ?? docs/adr/ADR-015-WhatsApp-Ingress-Architecture.md
  ?? docs/work_orders/WO-078-WHATSAPP-INBOUND-HTTPS-ARCHITECTURE-GATE.md
  ?? docs/work_orders/WO-079-WHATSAPP-INGRESS-ARCHITECTURE-DECISION-GATE.md
  ```

  (audit recorded the porcelain sha256 as `c380c4a91cc5e50095e94d447fda8f4d10135c33058d89f19acfd0f52f7a236f`,
  byte-identical before/after). `?? 500` observed only as porcelain text; the `.pyc` never
  opened/hashed/staged/restored/regenerated; staging was explicit per-path (never `git add -A`).
- Push: not performed by WO-083 (recorded as available on request).

## Final Verdict

`ACCEPTED` (implementation) and `ACCEPTED` (independent read-only audit). Scope statement:
covers local, read-only verification only. Every applicable local acceptance criterion was
independently reproduced from live commands. Live Telegram production E2E remains
`NOT VERIFIED` and is explicitly disclosed.

## Evidence Provenance

- Live Git facts re-confirmed during WO-086 (see Baseline / Evidence).
- Implementation report: local Hermes session store, session `api-3c0c2982e2309b85`
  (recorded 06 Oct 2026).
- Independent audit report: local Hermes session store, session `api-a748cdf5d8aa0eb8`
  (recorded 07 Oct 2026).
- Distilled counterpart: `skills/software-development/forensic-repo-audit/references/wo083-telegram-ingress-independent-audit.md`.
- No repository copy of this WO existed before WO-086.
