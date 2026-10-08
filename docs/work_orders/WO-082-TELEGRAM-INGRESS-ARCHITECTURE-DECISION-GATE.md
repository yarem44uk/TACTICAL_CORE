# WO-082 — Telegram Ingress Architecture / Decision Gate

**Status:** `ACCEPTED`
**Reconstructed by:** WO-086 (documentation-only reconciliation)
**Repository:** `yarem44uk/TACTICAL_CORE`
**Branch (worktree):** `wo-080-whatsapp-ingress-implementation`
**Baseline:** `1fb1482bd5b57a3a41543362152c61e8f17a8ea5`

> **Reconstruction note.** Historical documentation reconstructed from existing evidence
> only. No redesign, no reinterpretation, no status upgrade. Source: the WO's own report
> as preserved in the local Hermes session store, plus the WO-082 references distilled
> into the local skills tree.

---

## Status

`ACCEPTED`.

## Purpose

Independent Chief Systems Architect / Architecture Reviewer gate: determine whether
TACTICAL_CORE is architecturally ready for a Telegram ingress implementation and
define the exact, safe implementation boundary for WO-083. Read-only — no code, no
implementation files, no commits, no repository mutation.

## Baseline

| Item | Value |
| --- | --- |
| Branch / worktree | `wo-080-whatsapp-ingress-implementation` |
| `HEAD` | `a3601693fcdf6aec67a32d5604db5c2c2ae2cd2f` |
| Local `main` | `1fb1482bd5b57a3a41543362152c61e8f17a8ea5` |
| `origin/main` | `1fb1482bd5b57a3a41543362152c61e8f17a8ea5` |
| `git ls-remote origin refs/heads/main` | `1fb1482bd5b57a3a41543362152c61e8f17a8ea5` (live, no fetch) |
| `merge-base --is-ancestor a3601693 origin/main` | RC 0 |

GATE A = PASS. Worktree before/after identical (byte-for-byte); `HEAD`/refs unchanged.

## Scope

Architecture discovery and decision gate only. Inventoried the existing canonical
ingress architecture and the Telegram protocol facts; decided the first vertical
slice; fixed identity, authentication, ACK/durability, media and failure/retry
decisions; defined the WO-083 implementation perimeter and acceptance criteria.

## Evidence

Existing architecture inventory (real files, read-only):

- WhatsApp ingress `backend/app/whatsapp_ingress/{app,composition,service,signature,config,entrypoint}.py` — a **separate process** (not `main.py`, not the operator). Pipeline: HTTP → verify HMAC-SHA256 over raw body → JSON → `WhatsAppIngressService.handle_webhook` → `AdapterRuntime.submit_raw` → durable → ACK (commit-before-ACK). The ready template for Telegram.
- Signal seam: `adapters/signal_transport.py` (injected leaf transport) + `register_signal_adapter(factory, transport=...)` (WO-075); `signal` is in `PRODUCTION_SOURCE_CATALOG`.
- `EventFactory` (`event_sources/factory/event_factory.py`, with `identity_resolver`); adapters do not set `event_type` → canonical `EventType.CUSTOM`.
- `EventPipeline` (`app/event_pipeline/event_pipeline.py`); production path `_process_durable`.
- `AdapterRuntime` (`event_sources/runtime/adapter_runtime.py`): `submit_raw()` + `IngestResult` + `IngestStatus` (NEW/DUPLICATE/INVALID/FAILURE) + `set_ingest_durability_probe()` — a **generic** mechanism, not WhatsApp-specific.
- Durable journal `event_repository/durable/sqlalchemy_event_repository.py` — `save_with_deliveries()` atomic (event + outbox), idempotent, `UNIQUE(event_id)`.
- Observation `observation/canonical_adapter.py` (`derive_event_type` by `Event.source`) + `observation/models.py` (`EVENT_TYPE_MAPPINGS`).
- Operator Wall: read-model, separate read-only process (ADR-011).
- Identity `event_sources/identity/event_identity.py`: `_IDENTITY_POLICIES` already contains `telegram` → `_telegram_identity = _native(chat_id, message_id)` → `uuid5(_EVENT_NAMESPACE, "chat_id|message_id")`; namespace = `uuid5(NAMESPACE_URL, "https://tacticalcore.dev/event")`.
- Deduplication: deterministic `event_id` (UUID5, `String(36)`) + `UNIQUE(event_id)` → idempotent no-op save.
- Source registration: `PRODUCTION_SOURCE_CATALOG = [radio, signal]` (does **not** contain `telegram`). `build_production_adapter_factory()` registers 6 types (atak, mqtt, signal, radio, telegram, multicast_audio) → `telegram` **resolvable but not declared**. Legacy `connectors/telegram/{connector,service}.py` import `app.core.event_bus` (legacy bus) → outside the canonical chain.

Telegram protocol facts, taken from official `core.telegram.org` at the time of the WO
(confirmed via curl; cited by page reference in the report):

- `getUpdates` and webhooks are mutually exclusive.
- `setWebhook` sends an HTTPS POST with a JSON-serialized `Update`; a non-2xx response makes Telegram **repeat** the request.
- `secret_token` → header `X-Telegram-Bot-Api-Secret-Token`; 1–256 chars, `[A-Za-z0-9_-]` only — a **static shared secret**, **not** an HMAC body signature.
- Webhooks require TLS 1.2+, IPv4-only, ports 443/80/88/8443.
- `allowed_updates` narrows the received update types; `max_connections` 1–100 (default 40).
- Media: `file_id` is persistent; download is a separate `getFile` call (20 MB limit); the webhook body carries no bytes.

## Verification

Gate results as recorded: GATE A (baseline integrity) = PASS; worktree before/after
identical; `HEAD`/refs unmoved; filtered status (excluding pre-existing entries)
→ `NONE_ELSE`; no fetch/checkout/reset/stash/clean performed; `?? 500` observed only
as porcelain text.

## Architecture / Implementation

**Architecture decision: OPTION A — REUSE THE EXISTING CANONICAL INGRESS ARCHITECTURE.**

Evidence for the default: the `submit_raw()` / `IngestResult` / durability-probe seam
already exists in the core `AdapterRuntime`; the `telegram` identity policy is already
registered; the `telegram` observation mapping already exists; adapter registration via
`register_type` already exists. There is no architectural incompatibility blocking
implementation. The single real gap (`edited_message` identity collision) is a
first-slice **limitation**, not a blocker.

**Identity decision.** Canonical external identity for `message` = `message_id` scoped
by `chat_id`; `EVENT_ID = uuid5(namespace, "chat_id|message_id")` (36 chars → `String(36)`,
schema unchanged). Duplicate delivery of the same `Update` → same `event_id` →
`UNIQUE(event_id)` → idempotent no-op, HTTP 200 (`duplicate:true`) — behaviour 1:1 with
WO-080. Missing `message_id`/`chat_id` → normalization error → HTTP 400, nothing
persisted; random UUID4 ingestion identity is **forbidden**. `update_id` is kept only
as an observability/replay field, never as identity. An extra gap was noted: the existing
`telegram_parser.normalize()` accepts a **message object**, not the `Update` envelope, and
does not read `update_id` — WO-083 needs an envelope normalizer (new code, not a core change).

**Authentication decision.** Header `X-Telegram-Bot-Api-Secret-Token`; constant-time
comparison (`secrets.compare_digest` / `hmac.compare_digest`) of the raw header value
against the configured secret; reject missing/empty/invalid (fail-closed) → HTTP 401.
Secret lives in the ingress-process environment, **never** in
`SourceDefinition.config` / the catalog (`credentials_ref` only); exact env name
(e.g. `TELEGRAM_WEBHOOK_SECRET`) DEFERRED. **HMAC is not to be introduced** — Telegram
does not sign the body. Malformed JSON → 400; oversize → 413; replay/duplicate → dedup.

**ACK / durability decision.** Atomic commit via
`SQLAlchemyEventRepository.save_with_deliveries()` through `EventPipeline._process_durable`
(event + outbox together). HTTP 200 only after `IngestResult.durable == True`; 400 for
authenticated-but-unusable payload (nothing durable); 503 when durability is unconfirmed.
Non-2xx → Telegram retries; therefore 5xx is the expected retry mechanism. The existing
`AdapterRuntime.submit_raw()` + `IngestResult.durable` seam can be reused directly — no
`AdapterRuntime` change needed; the durability probe is set via
`set_ingest_durability_probe(SQLAlchemyEventRepository(sm).exists)`.

**Media decision.** The canonical event initially contains only a reference-only
descriptor (`media_type`, `file_id`, `file_unique_id`, `mime_type`, `file_size`,
`file_name`) + `caption` as text + `has_media`. No bytes, no in-request download.
Later download (`getFile` → `file_path` → `https://api.telegram.org/file/bot<token>/<file_path>`)
is a separate post-commit async WO. No download was performed during WO-082.

**First vertical slice.** `SUPPORTED_IN_WO-083`: Update envelope → single `message`;
text messages; media messages as reference-only descriptors; duplicate delivery →
idempotent 200 `duplicate:true`. `OUT_OF_SCOPE_FOR_WO-083`: `edited_message` /
`edited_channel_post` (**architecture gap** — the `chat_id|message_id` identity collides
an edit with its original), `channel_post`, `callback_query` / `inline_query` /
`business_*` / `poll` / `message_reaction`, and any media-byte download. Non-covered
types are handled by *not receiving* them via `allowed_updates: ["message"]` (rule:
"do not silently drop").

**WO-083 implementation perimeter.** MUST ADD/MODIFY: a new
`backend/app/telegram_ingress/` package (`app.py`, `service.py`, `config.py`,
`entrypoint.py`, `composition.py`); an Update-envelope normalizer near `telegram_parser`;
an additive `build_telegram_source_definition()` in `production_source_config.py`
(**not** appended to `PRODUCTION_SOURCE_CATALOG`); only if proven by test, additive
extension of `_telegram_identity` / `EVENT_TYPE_MAPPINGS["telegram.message"]`; tests
`backend/tests/test_wo083_telegram_ingress.py` modelled on `test_wo080_whatsapp_ingress.py`.
MUST NOT MODIFY: `backend/main.py`, `EventFactory` / `EventPipeline` / `AdapterRuntime`,
the WhatsApp ingress, the radio implementation, protected artifacts (`?? 500`,
`plugin_manager.cpython-313.pyc`), unrelated adapters, `connectors/telegram/*`,
`PRODUCTION_SOURCE_CATALOG`.

**WO-083 acceptance criteria (as specified, 17 testable items).** Includes: missing/invalid
secret → 401 with zero durable events; constant-time comparison unit test; one text
`message` → 200 and exactly 1 durable event with `event_id = uuid5(chat_id|message_id)`;
identity matrix; duplicate Update → 200 `duplicate:true` and exactly 1 durable event;
malformed JSON → 400 / oversize → 413 / missing identity → 400 (all with 0 durable);
200 reachable only when `durable=True` (forced probe→False ⇒ 503); canonical path via
`EventFactory`/`EventPipeline`; durable via real `SQLAlchemyEventRepository` (not a mock);
Observation visible via the operator read-model; restart dedup; no `app.core.event_bus`
import; no direct DB/Observation bypass; no secret/bot-token in logs or responses; no
other source changed; worktree preserved; target suite green with
`PYTHONDONTWRITEBYTECODE=1 -p no:cacheprovider`.

## Findings

- Legacy/bypass risk: `connectors/telegram/connector.py` and `service.py` import
  `app.core.event_bus` (legacy bus) → outside the canonical chain. WO-083 does not use
  them. No second `EventPipeline`/`EventFactory` exists; no Telegram HTTP ingress exists
  at baseline (`git ls-tree main` → only `whatsapp_ingress`). `event_sources/*` adapters
  do not write to the DB or create `Observation` directly.
- Two recorded architecture gaps (excluded from the first slice, not designed around):
  `edited_message` identity collision; `channel_post` chat-identity gap. Media bytes
  → out of scope (separate WO).
- The WO text's premise "the project uses Flask" is incorrect; resolved on repository
  evidence in WO-083.

## Limitations

- Local/static gate only; no live Telegram API call was made.
- The full set of unresolved production concerns is enumerated below.

## Production Gaps

`DNS` + public HTTPS host; TLS 1.2+ termination, SNI, full certificate chain; Telegram
webhook ports only (443/80/88/8443, or a local Bot API server); a real bot token + webhook
secret provisioned into the ingress environment; `setWebhook` on a live account with
`allowed_updates=["message"]`; firewall allow for Telegram source subnets
`149.154.160.0/20` and `91.108.4.0/22`; live acceptance testing. No live Telegram API call
was made; no bot was created; no webhook was set; no credential was used.

## Git / Repository State

Worktree after = worktree before (byte-for-byte, same order). `HEAD=a3601693`,
`main=origin/main=1fb1482`. No fetch/checkout/reset/stash/clean. `?? 500` observed only
as porcelain text. No write, no commit, no push, no ref change.

## Final Verdict

`ACCEPTED`. Telegram can reuse the canonical TACTICAL_CORE path (OPTION A); identity/dedup
defined (`chat_id|message_id` → uuid5, missing material → 400); ACK/durability defined
(200 only after durable via `submit_raw`/`IngestResult.durable`); security boundary defined
(static secret header, constant-time, **no HMAC**); first slice bounded (`message` only,
`allowed_updates=["message"]`); WO-083 perimeter explicit; no critical architectural blocker
(two recorded gaps excluded from the first slice rather than designed around); repository
and worktree untouched.

## Evidence Provenance

- Report transcript preserved in the local Hermes session store (session
  `api-a0aee9f76e2943b1`, recorded 06 Oct 2026).
- Distilled counterpart: `skills/software-development/forensic-repo-audit/references/ingress-architecture-decision-gate.md`.
- No repository copy of this WO existed before WO-086.
