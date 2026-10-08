# WO-085 — Telegram Production Infrastructure / Live E2E (Phase-A Gate)

**Status:** `BLOCKED — INFRASTRUCTURE NOT READY` (Phase-A gate: **NO-GO**; Phase B not entered)
**Reconstructed by:** WO-086 (documentation-only reconciliation)
**Repository:** `yarem44uk/TACTICAL_CORE`
**Baseline (main):** `688e0bbd1116afa70e780f493c44bfffb13317e8`

> **Reconstruction note.** Historical documentation reconstructed from existing evidence
> only. The status `BLOCKED — INFRASTRUCTURE NOT READY` is preserved exactly as reported.
> No Telegram Bot API call, no `setWebhook`, no live E2E — none of these happened and none
> may be inferred. Source: the WO's own Phase-A gate report as preserved in the local
> Hermes session store.

---

## Status

`BLOCKED — INFRASTRUCTURE NOT READY`. Phase-A verdict: **GO / NO-GO: NO-GO**.

Phase B (Telegram API registration + live E2E) was **not entered**. Telegram Bot API was
not called; `setWebhook` was not executed; live E2E was not executed.

## Purpose

Two-phase attempt to move the accepted Telegram ingress from "APPLICATION READY" toward
"PRODUCTION DEPLOYED + LIVE TELEGRAM E2E VERIFIED". Phase A = infrastructure discovery and
deployment-readiness gate; Phase B = Telegram API registration and live E2E. Distinct
requirement: do **not** enter Phase B automatically, and do not force deployment to obtain
a passing verdict.

## Baseline

| Item | Value |
| --- | --- |
| Branch | `main` |
| `HEAD` | `688e0bbd1116afa70e780f493c44bfffb13317e8` |
| `refs/heads/main` | `688e0bbd1116afa70e780f493c44bfffb13317e8` |
| `origin/main` | `688e0bbd1116afa70e780f493c44bfffb13317e8` |

All three identical → baseline PASS.

## Scope

Phase A only: host inventory, service/runtime discovery, application contract
re-confirmation, public DNS, TLS, edge/reverse proxy, firewall/NAT, secret injection,
database and monitoring — then a mandatory stop gate.

## Evidence

Host context (live, read-only) — **the WO was executed inside a Docker container (the Hermes
agent sandbox), not the real TACTICAL_CORE production host**:

- `hostname` = `3357795a1223` (container id); `hostname -f` = same (no FQDN)
- `eth0` = `172.18.0.4/16`; default route via `172.18.0.1`
- resolver = `127.0.0.11` (Docker embedded DNS); search domain `silly.billy`
- listeners: `0.0.0.0:8642` (Hermes gateway) and `127.0.0.11:46539` (Docker DNS) only
- port `8030` (`0x1F5E`): NOT bound — free
- no `iproute2`/`ss`/`netstat`/`lsof` tools; verified via `/proc/net/tcp` + `/proc/net/fib_trie`

Phase-A gate result:

```
PUBLIC_FQDN:          NOT_FOUND
PUBLIC_IP:            NOT_FOUND   (only container-internal 172.18.0.4)
HTTPS:                NOT_FOUND
TLS:                  NOT_READY
EDGE:                 NOT_PRESENT
REVERSE_PROXY:        NOT_PRESENT
FIREWALL_NAT:         UNKNOWN
APPLICATION_SERVICE:  NOT_PRESENT
APPLICATION_BIND:     NOT_PRESENT (code default would be 127.0.0.1; nothing bound)
APPLICATION_PORT:     8030 (WO-083 code default; not listening)
LOCAL_HEALTH:         NOT_TESTED (nothing bound on 8030)
PUBLIC_HEALTH:        NOT_FOUND
DATABASE:             NOT_CONFIGURED
SECRET_INJECTION:     NO
MONITORING:           NOT_PRESENT

TELEGRAM_API_CALLED:  NO
SETWEBHOOK_EXECUTED:  NO
LIVE_E2E_EXECUTED:    NO

GO / NO-GO:           NO-GO
```

Supporting findings (live, read-only):

- No edge/proxy at all — `/etc/nginx`, `/etc/caddy`, `/etc/traefik`, `/etc/haproxy`,
  `/etc/apache2` do not exist; no such binaries on PATH.
- No service manager — `systemctl` not found (`/etc/systemd/system` holds only an empty
  `timers.target.wants` dir). The container is s6-supervised and runs only the Hermes
  gateway. The `docker` CLI exists but the daemon is unreachable
  ("Cannot connect to the Docker daemon"); `podman` not found.
- No secrets and no injection path — `TELEGRAM_WEBHOOK_SECRET`, `TELEGRAM_HOST`,
  `TELEGRAM_PORT`, `TELEGRAM_WEBHOOK_PATH`, `DATABASE_URL`, `TELEGRAM_BOT_TOKEN` all absent
  from the process environment. `/opt/data/.env` holds a single non-Telegram variable
  (masked). `backend/.env.example` declares only `DATABASE_URL`/`DATABASE_ECHO`.
- No public DNS — repo-wide search for real FQDNs/IPs returns only test/placeholder URLs and
  the `tacticalcore.dev` UUID namespace. `PUBLIC_FQDN = NOT_FOUND` (not invented).
- No deployment artifacts in the repo — no Dockerfile, docker-compose, systemd unit (the many
  `*.service` hits are Python `service.py` modules), no k8s/Podman files, no proxy config.
  Only CI workflow `.github/workflows/severity-governance.yml`. Matches ADR-010 §146/§349 and
  WO-080 §211, which record that no deployment model exists.
- Monitoring absent — no Prometheus/Grafana/Sentry/Datadog config or scrape target;
  `docs/PLATFORM_READINESS.md` itself lists "Prometheus export — not implemented". Only
  in-app local loggers + `/healthz`.

Application-side contract re-confirmed from code (unchanged since WO-083):
`POST /telegram/webhook`, `GET /healthz`; `DEFAULT_HOST=127.0.0.1`, `DEFAULT_PORT=8030`,
`DEFAULT_WEBHOOK_PATH=/telegram/webhook`, `DEFAULT_MAX_BODY_BYTES=1 MiB`; auth header
`X-Telegram-Bot-Api-Secret-Token` compared with `hmac.compare_digest`, fail-closed; required
env `TELEGRAM_WEBHOOK_SECRET` (fail-closed) + `DATABASE_URL` (fail-closed); separate uvicorn
process via `python -m app.telegram_ingress.entrypoint`; `build_telegram_source_definition()`
exists with `adapter_type="telegram"`, declared but **not** wired into
`PRODUCTION_SOURCE_CATALOG` (correct per WO-083 design). WO-083 commits present: `71bd972`
and its merge `688e0bb`.

## Verification

Per the WO's GO criteria, because `PUBLIC_FQDN`, `HTTPS`, `TLS`, `EDGE`/`REVERSE_PROXY`,
`APPLICATION_SERVICE`, `SECRET_INJECTION` and `DATABASE` are all
`NOT_FOUND`/`NOT_READY`/`NOT_CONFIGURED`, the gate is **NO-GO**. Phase B was not entered.
No `/healthz` probe was possible (nothing bound on 8030).

Phase B items — all not executed:

```
SETWEBHOOK:          NOT EXECUTED
WEBHOOK_STATE:       NOT QUERIED
REAL_MESSAGE:        NOT EXECUTED
DURABLE_EVENT:       NOT VERIFIED
OPERATOR_WALL:       NOT VERIFIED
DUPLICATE:           NOT EXECUTED
INVALID_SECRET:      NOT EXECUTED
MALFORMED_JSON:      NOT EXECUTED
UNSUPPORTED_UPDATE:  NOT EXECUTED
DURABILITY_FAILURE:  NOT EXECUTED
RESTART_RECOVERY:    NOT EXECUTED
```

## Findings

Blockers (all infrastructure-side; none application-level):

1. No public hostname/DNS — `PUBLIC_FQDN` NOT_FOUND.
2. No public HTTPS / no TLS — TLS NOT_READY, no certificate, no `:443`.
3. No edge/reverse proxy — nginx/Caddy/Traefik/HAProxy/Apache absent; the route
   `PUBLIC /telegram/webhook → 127.0.0.1:8030` does not exist.
4. No firewall/NAT posture — UNKNOWN; 8030 exposure not governed.
5. No service deployment — no systemd/container supervision for the ingress process.
6. No secret injection — `TELEGRAM_WEBHOOK_SECRET` (and `DATABASE_URL`) not provisioned.
7. No production database reachable/configured.
8. No monitoring.
9. The host is the Hermes sandbox container, not the production TACTICAL_CORE host.

## Limitations

- The discovery host is **not** the production host — the entire gate is a
  negative/absence report from the sandbox.
- No Telegram API interaction of any kind was performed.
- Rollback is documented conceptually only; nothing was deployed, so nothing was rolled back.

## Production Gaps

- All WO-084 "NOT FOUND IN REPOSITORY" items remain unfulfilled in the real environment.
- WO-083 follow-ups still open: no automated test for the 413 oversized-body branch; the body
  is fully buffered before the 1 MiB check.
- `backend/.env.example` still documents no `TELEGRAM_*` variables (documentation gap).

Required next WO (deployment infrastructure — nothing executed here):

- **A.** Establish in the real environment: public DNS A/AAAA record for an operator-approved
  host; TLS at an edge; a reverse proxy terminating TLS and proxying the raw body + preserving
  `X-Telegram-Bot-Api-Secret-Token` to `http://127.0.0.1:8030/telegram/webhook`; firewall/NAT
  allowing only edge→8030 (8030 not Internet-exposed); a supervised service (systemd unit or
  container) running `python -m app.telegram_ingress.entrypoint` with correct cwd/PYTHONPATH;
  provisioned `TELEGRAM_WEBHOOK_SECRET` + `DATABASE_URL` (+ optional HOST/PORT/WEBHOOK_PATH);
  `/healthz` monitoring.
- **B.** Only then `setWebhook(url=https://<ACTUAL_PUBLIC_FQDN>/telegram/webhook,
  secret_token=<TELEGRAM_WEBHOOK_SECRET>, allowed_updates=["message"])` — FQDN and secret to be
  supplied by the deployment environment, never invented.
- **C.** Live E2E: real message → 200 + one durable event (`source=telegram`,
  `event_type=telegram.message`) on the Operator Wall; duplicate → 200 duplicate, one event;
  invalid secret → 401, zero durable; malformed JSON → 400; unsupported update → 400.
- **D.** Rollback (conceptual, not executed): `deleteWebhook`; stop/disable the ingress
  service; disable the edge route; restore firewall/edge; keep the DB intact (WO-083 is
  additive; `main` remains `688e0bb`).

## Git / Repository State

```
WORKTREE:        M backend/app/plugins/manager/__pycache__/plugin_manager.cpython-313.pyc;
                 ?? 500;
                 ?? backend/tests/test_wo080_audit_idempotency.py;
                 ?? backend/tests/test_wo080_whatsapp_audit_corrective.py;
                 ?? docs/adr/ADR-015-WhatsApp-Ingress-Architecture.md;
                 ?? docs/work_orders/WO-078-WHATSAPP-INBOUND-HTTPS-ARCHITECTURE-GATE.md;
                 ?? docs/work_orders/WO-079-WHATSAPP-INGRESS-ARCHITECTURE-DECISION-GATE.md
SOURCE_CHANGES:  NONE
COMMITS:         NONE
PUSH:            NONE
WORKTREE UNCHANGED vs WO-084 baseline: PASS
```

## Final Verdict

`BLOCKED — INFRASTRUCTURE NOT READY`. Per the WO's non-negotiable rule, because
infrastructure was not actually ready, the correct result is a blocked gate. No deployment was
forced, no Telegram API was contacted, and the worktree is unchanged.

## Evidence Provenance

- Report transcript preserved in the local Hermes session store (session
  `api-5d1301bcb5d06222`, recorded 07 Oct 2026).
- No repository copy of this WO existed before WO-086.
