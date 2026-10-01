# WO-080 — WhatsApp Ingress Implementation

**Status:** Verdict per final report (see §19 below / WO-080 §45 output).
**Repository:** `/opt/data/tactical_core_github`
**Branch:** `wo-080-whatsapp-ingress-implementation`
**Baseline (verified):** `0fabce389c5f23e95aa7a8546f490b320ce85949`

---

## 1. Baseline forensics

| Item | Value |
| --- | --- |
| `git rev-parse HEAD` (pre-implementation) | `0fabce389c5f23e95aa7a8546f490b320ce85949` |
| `git rev-parse origin/main` | `0fabce389c5f23e95aa7a8546f490b320ce85949` |
| `git ls-remote origin refs/heads/main` | `0fabce389c5f23e95aa7a8546f490b320ce85949` |
| Branch | `main` (WO-075 is the tip) |

The expected WO-075 baseline and the live remote `main` matched **exactly** — no
baseline substitution was required (WO-080 §2).

Pre-existing worktree state at baseline (`git status --porcelain=v1`):

```
 M backend/app/plugins/manager/__pycache__/plugin_manager.cpython-313.pyc
?? 500
?? docs/adr/ADR-015-WhatsApp-Ingress-Architecture.md
?? docs/work_orders/WO-078-WHATSAPP-INBOUND-HTTPS-ARCHITECTURE-GATE.md
?? docs/work_orders/WO-079-WHATSAPP-INGRESS-ARCHITECTURE-DECISION-GATE.md
```

## 2. WO-079 / ADR-015 Git status

| Artifact | Exists locally | Tracked | Present in HEAD | Present in origin/main |
| --- | --- | --- | --- | --- |
| `docs/work_orders/WO-079-...md` | YES | NO | NO | NO |
| `docs/adr/ADR-015-WhatsApp-Ingress-Architecture.md` | YES | NO | NO | NO |
| `docs/work_orders/WO-078-...md` | YES | NO | NO | NO |

`git ls-files --error-unmatch` fails and `git cat-file -e HEAD:<path>` /
`git cat-file -e origin/main:<path>` both report *"exists on disk, but not in
'HEAD'/'origin/main'"*. These documents are therefore treated as **external
architecture evidence** for this WO and are **NOT** committed (WO-080 §3, §40).

## 3. Implemented architecture

```
Meta WhatsApp Cloud API
      |  HTTPS GET (verify) / POST (webhook)
      v
WhatsApp Webhook Ingress process  (NEW; separate process + entrypoint)
      |  X-Hub-Signature-256 verified over the RAW body
      |  WhatsAppPayloadNormalizer (transport boundary; no Event construction)
      v
WhatsAppSourceAdapter   (leaf; SourceDefinition + AdapterFactory registration)
      v
AdapterRuntime.submit_raw()   (NEW synchronous seam; returns IngestResult)
      v
EventFactory.create_event()   (EXISTING, unmodified)
      v
EventPipeline.process()       (EXISTING, unmodified)
      v
DurableCanonicalEventRepository / save_with_deliveries   <- DURABILITY POINT
      |  (atomic canonical event + PENDING outbox records)
      v
DurableDeliveryDispatcher -> ObservationService -> Operator Wall
```

No second EventFactory, EventPipeline, journal, or observation path exists
(WO-080 §10). The ingress never constructs a canonical Event.

## 4. WhatsApp webhook

* GET verification challenge: `hub.mode == "subscribe"` AND
  constant-time `hub.verify_token` match → raw challenge returned; otherwise 403.
* POST: raw body read once; `X-Hub-Signature-256` verified; JSON decoded; the
  payload handed to the ingress service.  Oversized bodies → 413.
* The Verify Token and App Secret are never logged.

## 5. Signature / verification

* `app/whatsapp_ingress/signature.py` — HMAC-SHA256 over the **exact raw
  request body**, constant-time comparison (`hmac.compare_digest`), required
  `sha256=` prefix.
* Invalid / missing / malformed signature → **401**, and the payload never
  reaches the canonical path (verified by test: zero durable events).

## 6. Normalization

`app/event_sources/adapters/whatsapp_parser.py` (`WhatsAppPayloadNormalizer`)
walks `entry[].changes[].value.messages[]` and emits a flat raw dict per
message: `message_id`, `phone_number_id`, `sender`, `message_type`, `text`,
optional `display_phone_number`, optional `timestamp`, and for media categories a
**reference-only** `media` descriptor (`media_id`, `mime_type`, `sha256`,
`filename`, `caption`) — only fields Meta actually supplied.  Statuses-only
webhooks yield **no** raw events (nothing is fabricated).  Malformed structure
or a missing message `id` / `metadata.phone_number_id` → `WhatsAppParseError`
→ HTTP 400.

## 7. Deterministic identity

`_whatsapp_identity` policy added to
`app/event_sources/identity/event_identity.py`:

```
whatsapp|<phone_number_id>|<message_id>  ->  UUID5 (_EVENT_NAMESPACE)
```

No `chat_id` is assumed (WhatsApp webhook messages have none).  `event_id` stays
`String(36)` — **no schema change**.  Tests 1-3 (same/different
`phone_number_id`/`message_id`) and the no-UUID4-fallback check pass.

## 8. ACK / durability

`AdapterRuntime.submit_raw()` is the additive synchronous seam (WO-080 §21):
same factory/pipeline path, but it does **not** swallow failures and returns an
`IngestResult(status, event_id, durable, error)`.  A read-only durability probe
(`SQLAlchemyEventRepository.exists` on the SAME session manager / store) is used
to distinguish NEW from DUPLICATE and to **confirm** durability before success.
The ingress ACKs 200 only when `durable` is True for every message.  Durability
failure or unconfirmed durability → **503**.  No in-memory buffer is an ACK
boundary; **no new durable queue / store / table** was introduced.

## 9. EventFactory / EventPipeline

Both are the existing, unmodified classes, reached only through
`AdapterRuntime`.  `save_with_deliveries` (the existing atomic event+outbox
transaction) is the durability point.

## 10. Observation

Two additive changes: `_SOURCE_TO_EVENT_TYPE["whatsapp"] = "whatsapp.message"`
(the authoritative derivation, keyed on `Event.source`) and
`EVENT_TYPE_MAPPINGS["whatsapp.message"]` (`observation_type="other"`,
`required_fields=["message_id","phone_number_id"]` — no `chat_id`).  A single
kind covers text/image/audio/video/document; the category lives in the payload.

## 11. Media boundary

The webhook stores a **reference only** and never downloads media, never calls
the Meta media API, and never blocks ACK on media.  Media retrieval remains a
future WO (ADR-015 §11).

## 12. Tests

| Command | Exit | Pass | Fail | Skip |
| --- | --- | --- | --- | --- |
| `python -m pytest tests/test_wo080_whatsapp_ingress.py -q` | 0 | 24 | 0 | 0 |
| `python -m pytest <17 affected suites> -q` | 0 | 177 | 0 | 0 |
| `python -m pytest --ignore=tests/intelligence/test_identity.py -q` (full) | 1 | 2213 | 49 | 16 |

The 49 full-suite failures are the pre-existing baseline set (see §13).

## 13. Regression

A clean baseline clone (`0fabce389…`) run with an identical invocation gives
**48 failed / 2190 passed / 16 skipped**.  Comparing the failing sets:

* 48 failures are identical to the branch's.
* The single set difference
  (`tests/test_wo032_production_entrypoint.py::test_wo034_backend_dir_bootstrap_is_idempotent`)
  is **pre-existing and NOT caused by this WO**:
  * it reproduces in a two-file combo that imports **no WO-080 module** —
    `pytest tests/test_sdk_health.py tests/test_wo032_production_entrypoint.py`
    fails with `assert 2 == 1`, while the wo032 file alone passes;
  * the mechanism is: pre-existing `tests/test_sdk_*.py` unconditionally execute
    `sys.path.insert(0, "/opt/data/tactical_core_github/backend")` at import
    time, and pytest also inserts the repo rootdir — so the **real repo path**
    appears twice, breaking that test's `sys.path.count(...) == 1` assertion.
    In the baseline clone the hardcoded literal points at the *other* repo, so
    the clone cannot exhibit it;
  * `tests/test_sdk_health.py`, `tests/test_wo032_production_entrypoint.py` and
    `backend/main.py` are **byte-identical to baseline**
    (`git diff --stat <baseline> -- ...` is empty).
* `tests/intelligence/test_entity.py::TestEntityData::test_entity_data_to_dict`
  is **PYTHONHASHSEED-dependent** (a `set`-ordering assertion): it passes at
  `PYTHONHASHSEED=0/1` and fails at `2/3`, i.e. a pre-existing flake.

## 14. Change perimeter

Modified (5): `identity/event_identity.py`, `observation/canonical_adapter.py`,
`observation/models.py`, `runtime/adapter_runtime.py`,
`config/production_source_config.py`.

Created: the whatsapp adapter trio, the `whatsapp_ingress/` package
(`__init__`, `config`, `signature`, `service`, `composition`, `app`,
`entrypoint`), and `tests/test_wo080_whatsapp_ingress.py`.

Not touched: `backend/main.py`, the operator FastAPI app, any protected artifact.

## 15. Protected artifacts

`?? 500` — preserved untouched (never opened/read/stat'ed/hashed/copied/renamed/
staged/deleted/cleaned; observed only as a `git status --porcelain=v1` line).
`backend/app/plugins/manager/__pycache__/plugin_manager.cpython-313.pyc` —
preserved untouched (still ` M`, never staged/restored/regenerated/deleted).

## 16. Git commit

See the commit on `wo-080-whatsapp-ingress-implementation` (implementation files
+ this WO-080 documentation only).  `main` is neither modified nor pushed.
Architecture evidence (WO-078/079, ADR-015) is intentionally **not** committed.

## 17. Remote state

See the final report — either the pushed branch ref or the local commit SHA
(WO-080 §43).

## 18. Known limitations

* No deployment work: TLS, reverse proxy, DNS, firewall, host placement
  (ADR-015 §11) — out of scope.
* No live Meta validation; the Meta behaviour rows remain WO-078-carried
  external contract, not verified in-repo.
* Media retrieval, rate/concurrency bounding, and a WhatsApp production
  credential resolver remain future WOs.
* Duplicate delivery re-runs the WO-030 hot-path delivery to registered
  consumers; this is the existing at-least-once outbox behaviour and is
  gracefully idempotent at the observation layer (`UNIQUE(immutable_id)`), but
  it is visible in logs.

## 19. Reference

* ADR: `docs/adr/ADR-015-WhatsApp-Ingress-Architecture.md` (external evidence,
  not committed).
