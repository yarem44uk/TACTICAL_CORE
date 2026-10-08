# WO-084 — Telegram Production Readiness / Deployment Gate

**Status:** `READY FOR DEPLOYMENT WO` (read-only gate; **not** an implementation and **not** a deployment)
**Reconstructed by:** WO-086 (documentation-only reconciliation)
**Repository:** `yarem44uk/TACTICAL_CORE`
**Baseline (main):** `688e0bbd1116afa70e780f493c44bfffb13317e8`

> **Reconstruction note.** Historical documentation reconstructed from existing evidence
> only. This WO's conclusion is preserved exactly: it is a **deployment-readiness gap
> report**, not a successful deployment record. No Telegram API call, no `setWebhook`,
> no live E2E. Source: the WO's own report as preserved in the local Hermes session store.

---

## Status

`READY FOR DEPLOYMENT WO`.

Note on status vocabulary: the WO's own instruction offered `ACCEPTED` /
`PARTIALLY VERIFIED` / `BLOCKED`, but the report's actual conclusion was
`READY FOR DEPLOYMENT WO` — justified because no **application-level** blocker exists, while
every infrastructure component remains unestablished. That exact conclusion is preserved
here and must not be upgraded to "deployed" or "accepted" in the deployment sense.

## Purpose

Read-only production-readiness / deployment gate: determine whether the already
accepted Telegram ingress implementation is production-ready **from an
infrastructure/deployment perspective**, without making any production-side change.
Not an implementation WO; not a live Telegram integration WO; not a DNS/firewall/TLS
change WO; not a webhook registration WO.

## Baseline

| Item | Value |
| --- | --- |
| `main` / `HEAD` / `origin/main` | `688e0bbd1116afa70e780f493c44bfffb13317e8` |
| WO-083 implementation | `71bd972ac14bdfc9a6ef79876f24229fbe071548` |
| WO-083 merge | `688e0bbd1116afa70e780f493c44bfffb13317e8` |
| WO-083 status at entry | Accepted |

Live Git safety gate: `branch=main`; `HEAD=688e0bbd…`; `main=688e0bbd…`;
`origin/main=688e0bbd…` — all identical to expected. PASS.

## Scope

Read-only inspection of the accepted Telegram ingress and the repository for any
deployment artefact. No application change; no infrastructure change; no Telegram API call.

## Evidence

Telegram deployment contract, confirmed from code (read-only inspection of 8 files under
`backend/app/telegram_ingress/`):

| Item | Value |
| --- | --- |
| Public URL | `UNKNOWN` — no public host, DNS name, IP or FQDN exists anywhere in the repository; must **not** be invented |
| Webhook path | `/telegram/webhook` (`config.DEFAULT_WEBHOOK_PATH`; also the FastAPI route default; overridable by `TELEGRAM_WEBHOOK_PATH`) |
| Application listen address | `127.0.0.1` (`config.DEFAULT_HOST`, loopback-only; overridable by `TELEGRAM_HOST`) |
| Application port | `8030` (`config.DEFAULT_PORT`; overridable by `TELEGRAM_PORT`) |
| TLS termination | Not in the application — `uvicorn.run(app, host, port)` serves plain HTTP; TLS must terminate upstream (`entrypoint.py` runs uvicorn with no `ssl_*` args). Consistent with ADR-015 §136 (TLS DEFERRED, reverse proxy) and WO-080 §211 (no TLS/reverse-proxy/DNS work) |
| Auth header | `X-Telegram-Bot-Api-Secret-Token` (`secret.SECRET_HEADER`) |
| Secret variable | `TELEGRAM_WEBHOOK_SECRET` (`config.SECRET_TOKEN_ENV`; required, fail-closed) |
| Allowed updates | `["message"]` (`normalizer.SUPPORTED_UPDATE_TYPE = "message"`; any other type → 400) |

PUBLIC URL SHAPE (a shape, not a claim of existence): `https://<public-host>/telegram/webhook`.
`<public-host>` is `UNKNOWN`.

## Verification

Production readiness matrix (area | status | evidence | required before production):

| Area | Status | Evidence | Required |
| --- | --- | --- | --- |
| Telegram ingress code | CONFIRMED | WO-083 accepted + read-only inspection of 8 files under `backend/app/telegram_ingress/` | No |
| Canonical event path | CONFIRMED | `composition.py` wires existing `create_production_runtime()` / `AdapterRuntime.submit_raw()`; no new pipeline | No |
| Durable-before-ACK | CONFIRMED | `service.py`: ACK 200 only when `result.durable` is True; 503 otherwise; `require_durable_delivery=True` (fail-closed) | No |
| Deduplication | CONFIRMED | identity from `chat_id`+`message_id` (`normalizer.py`); DUPLICATE status ACKs 200 with `duplicate=True` | No |
| Secret authentication | CONFIRMED | `secret.py` `hmac.compare_digest`; missing/empty/mismatch → 401 (`app.py`) | No |
| Public DNS | NOT FOUND IN REPOSITORY | find over repo: no DNS/zone records | Yes |
| Public HTTPS | NOT FOUND IN REPOSITORY | no proxy/TLS config; app serves HTTP on `127.0.0.1:8030` | Yes |
| TLS certificate | NOT FOUND IN REPOSITORY | ADR-015 §136 "DEFERRED — outside the repository" | Yes |
| Reverse proxy / edge | NOT FOUND IN REPOSITORY | no nginx/Caddy/Traefik/HAProxy/Apache config; WO-078/ADR-015 discuss FortiGate/reverse-proxy only conceptually ("NO REPOSITORY EVIDENCE" per WO-079 §291-294) | Yes if required |
| Firewall | NOT FOUND IN REPOSITORY | no firewall/NAT/port-forward config; WO-079 §496/§602 log firewall as NO REPOSITORY EVIDENCE | Yes |
| Application service deployment | NOT FOUND IN REPOSITORY | no Dockerfile, docker-compose, `*.service`, k8s manifest; entrypoint exists but no unit/container | Yes |
| Secret injection | PARTIALLY CONFIRMED | code reads `TELEGRAM_WEBHOOK_SECRET` from process env only; but `backend/.env.example` declares NO `TELEGRAM_*` / `WHATSAPP_*` variables | Yes |
| Telegram webhook registration | NOT EXECUTED | this WO (read-only) | Yes |
| Live Telegram E2E | NOT EXECUTED | this WO (read-only) | Yes |
| 413 automated test | KNOWN GAP | grep of `test_wo083_telegram_ingress.py`: no 413/`max_body` test (still absent) | Follow-up |
| Production monitoring | NOT FOUND IN REPOSITORY | no metrics/alerting/supervisor config; only in-app `/healthz` + loggers | Recommended/required |

Additional confirmed contract details (code evidence):

- Authentication: missing → 401; invalid → 401; valid → accepted; comparison is
  `hmac.compare_digest` (constant-time); the header value is never logged (only the generic
  message "invalid secret token"); **no HMAC body authentication** — Telegram does not sign
  the body; `secret.py` deliberately implements the static shared token only.
- Endpoints: `POST /telegram/webhook` (`include_in_schema=False`) + `GET /healthz`.
- Entrypoint: `python -m app.telegram_ingress.entrypoint` (or `backend.app.telegram_ingress.entrypoint`
  from root); a separate process, independent of `backend/main.py` and the operator app;
  reverse proxy expected (TLS belongs to external infrastructure).
- Failure/retry model (local verified): 200 durable (new or duplicate) → Telegram stops
  retrying; 400 authentic-but-unusable (bad JSON / non-object / unsupported update / missing
  `message_id` or `chat.id`) → nothing durable; 401 invalid secret; 503 durable not confirmed
  → Telegram retries. 2xx = delivered; 4xx = not retried; 5xx = retried. **LIVE TELEGRAM NOT VERIFIED.**
- No outbound calls: no `httpx`/`requests`/`urllib` import and no
  `getUpdates`/`getFile`/`sendMessage`/`api.telegram` reference in the package; media is
  reference-only (`file_id`/`file_unique_id`/`mime_type`/`file_size`) via the existing
  `TelegramPayloadNormalizer._normalize_media`. No bot token referenced anywhere (config
  only knows `TELEGRAM_WEBHOOK_SECRET`).
- Logging: 9 logger calls total, none emit the secret, the raw body, or the auth header;
  they log rejection reasons, oversized-body byte count, malformed JSON,
  durability-not-confirmed, and wiring/bind lines. `update_id` retained in the raw payload
  for observability/replay only (not identity).
- Health: `GET /healthz` returns `{"status":"ok","source":<runtime.health()>}` — application/
  process health only. It does **not** assert Telegram webhook reachability, DNS, TLS or the
  database's live writability. No readiness/dependency-probe endpoint exists.

## Findings

- No application-level blocker found. The accepted application side is complete,
  self-consistent, and evidenced. All missing items are external infrastructure/live-deployment
  actions, not fixes to the application.
- Non-blocking, evidence-based risks (follow-up only, **not** fixed here):
  1. **MEDIUM** — KNOWN PRE-EXISTING WO-083 FOLLOW-UP: no automated test covers the 413
     oversized-body branch (`grep` of `tests/test_wo083_telegram_ingress.py` → zero matches for
     413 / `max_body` / `oversized`). Still open.
  2. **LOW** — KNOWN PRE-EXISTING WO-083 FOLLOW-UP: `app.py` reads `await request.body()` fully,
     then compares `len(raw_body) > max_body_bytes`, so the whole body is buffered before the
     1 MiB ceiling is enforced. Still open.
  3. `backend/.env.example` does not document `TELEGRAM_WEBHOOK_SECRET` / `TELEGRAM_HOST` /
     `TELEGRAM_PORT` / `TELEGRAM_WEBHOOK_PATH` — secret injection is code-only (environment).
     Documentation gap, not a code defect.
  4. 503 retry relies on Telegram's own retry policy; there is no application-side retry/queue
     (correct per the fail-closed design), and no inbound replay buffer exists locally.

## Limitations

- Read-only gate: nothing was deployed, configured, or registered.
- All infrastructure findings are "NOT FOUND IN REPOSITORY" / "NOT EXECUTED" — absence of
  repository evidence, not evidence of absence in the real environment.

## Production Gaps

Required next WO (deployment WO — nothing executed here):

- **A. Infrastructure (must be authorized):** public DNS A/AAAA (or CNAME) for an
  operator-approved host (host `UNKNOWN`); TLS certificate obtain/renew + HTTPS on 443 (or
  Telegram-supported 80/88/8443); reverse proxy / edge terminating TLS and `proxy_pass` to
  `http://127.0.0.1:8030/telegram/webhook`, preserving the `X-Telegram-Bot-Api-Secret-Token`
  header and forwarding the raw body unmodified; firewall/NAT/FortiGate permitting inbound
  HTTPS to the edge only (no direct exposure of 8030); service deployment as a supervised
  service (systemd unit or container) executing
  `python -m app.telegram_ingress.entrypoint` with correct working dir/PYTHONPATH; environment
  injection of `TELEGRAM_WEBHOOK_SECRET` (high-entropy, Telegram-allowed charset),
  `TELEGRAM_HOST`, `TELEGRAM_PORT`, `TELEGRAM_WEBHOOK_PATH`, `DATABASE_URL`, plus a rotation
  strategy (values never printed); monitoring of `/healthz`, 401/503 rates and runtime health,
  plus a log retention/redaction policy.
- **B. Telegram API (authorized in the deployment WO, NOT executed here):** `setWebhook` with
  `url=https://<PUBLIC_HOST>/telegram/webhook`, `secret_token=<TELEGRAM_WEBHOOK_SECRET>`,
  `allowed_updates=["message"]` (host/secret not fabricated).
- **C. Live validation:** real message → 200 + one durable event on the Operator Wall;
  duplicate (same `chat_id`+`message_id`) → 200 `duplicate=true`, no second event; invalid
  secret → 401, zero durable; unsupported update (e.g. `edited_message`) → 400, zero durable;
  malformed JSON → 400; durability path (only if safely testable) → 503 and Telegram retry;
  Operator Wall observation with `source="telegram"`.
- **D. Rollback (conceptual, NOT executed):** `deleteWebhook` (or `setWebhook` to a drain
  URL); stop/disable the ingress service; revert edge/DNS/firewall to prior state; retain the
  DB (WO-083 is additive; `main` remains at `688e0bb` and can serve without the Telegram source).

## Git / Repository State

Worktree `git status --porcelain=v1` BEFORE = AFTER (unchanged, PASS):

```
 M backend/app/plugins/manager/__pycache__/plugin_manager.cpython-313.pyc
?? 500
?? backend/tests/test_wo080_audit_idempotency.py
?? backend/tests/test_wo080_whatsapp_audit_corrective.py
?? docs/adr/ADR-015-WhatsApp-Ingress-Architecture.md
?? docs/work_orders/WO-078-WHATSAPP-INBOUND-HTTPS-ARCHITECTURE-GATE.md
?? docs/work_orders/WO-079-WHATSAPP-INGRESS-ARCHITECTURE-DECISION-GATE.md
```

No new modified files, no new untracked files, no staged files, no commits, no pushes.
Protected artifacts untouched (observed via porcelain only). `HEAD` still `688e0bb`. No test
run was performed (a run would have created `.pytest_cache`, which is neither present nor
gitignored — deliberately avoided to keep the worktree pristine).

## Final Verdict

`READY FOR DEPLOYMENT WO`. The accepted Telegram ingress is complete and fully evidenced on
the application side. No application-level blocker exists. It is **not** full deployment
readiness: every infrastructure component (DNS, TLS, reverse proxy/edge, firewall, service
deployment, secret injection, webhook registration, live E2E, monitoring) is either
NOT FOUND IN REPOSITORY or NOT EXECUTED, and the WO-083 413 follow-up items remain open —
all of which are the authorized scope of the next deployment WO. Nothing was mutated; no
Telegram API call was made.

## Evidence Provenance

- Report transcript preserved in the local Hermes session store (session
  `api-3e17692fee11d986`, recorded 07 Oct 2026).
- Distilled counterpart: `skills/software-delivery/work-order-execution/references/read-only-deployment-readiness-gate.md`.
- No repository copy of this WO existed before WO-086.
