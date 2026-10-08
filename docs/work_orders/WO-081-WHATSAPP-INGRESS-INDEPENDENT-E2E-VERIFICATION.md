# WO-081 — WhatsApp Ingress Independent E2E Verification

**Status:** `ACCEPTED` (local, read-only verification only — production Meta E2E `NOT VERIFIED`)
**Reconstructed by:** WO-086 (documentation-only reconciliation)
**Repository:** `yarem44uk/TACTICAL_CORE`
**Branch (worktree):** `wo-080-whatsapp-ingress-implementation`
**Baseline (verified):** `1fb1482bd5b57a3a41543362152c61e8f17a8ea5`

> **Reconstruction note.** This file is historical documentation reconstructed from
> existing evidence only. Nothing here was redesigned, corrected, reinterpreted or
> upgraded. The source is the WO's own report as preserved in the local Hermes
> session store, plus the live Git facts it cites.

---

## Status

`ACCEPTED` — "локальна верифікація пройдена; усі production-only обмеження явно
зазначені" (local verification passed; all production-only limitations explicitly
disclosed).

The verdict explicitly covers **local verification only**; production Meta
end-to-end remains `NOT VERIFIED`.

## Purpose

Act as an independent forensic QA / production-readiness reviewer for the already
integrated WO-080 WhatsApp inbound webhook ingress. Read-only; no implementation,
no fixes, no repository mutation.

## Baseline

| Item | Value |
| --- | --- |
| Branch / worktree | `wo-080-whatsapp-ingress-implementation` |
| `HEAD` | `a3601693fcdf6aec67a32d5604db5c2c2ae2cd2f` |
| Local `main` | `1fb1482bd5b57a3a41543362152c61e8f17a8ea5` |
| `origin/main` | `1fb1482bd5b57a3a41543362152c61e8f17a8ea5` |
| `git ls-remote origin refs/heads/main` | `1fb1482bd5b57a3a41543362152c61e8f17a8ea5` |
| `merge-base --is-ancestor a3601693 origin/main` | exit 0 (PASS) |

No fetch was performed; no branch switching was performed. The worktree remained on
the WO-080 branch while the local `main` ref already pointed at the merge commit
`1fb1482` — recorded as a prior local ref update, **not** caused by this audit.

## Scope

Read-only independent verification of the integrated WO-080 state: prove the
merge actually landed on the remote, re-run the targeted tests, prove the local
worktree and protected artifacts are byte-identical before/after, and draw a hard
`VERIFIED-by-test` vs `VERIFIED-by-inspection` vs `NOT VERIFIED` boundary.

## Evidence

Recorded live Git facts (from the report):

- `git rev-parse main` / `origin/main` / `ls-remote` → `1fb1482bd5b57a3a41543362152c61e8f17a8ea5`
- `git merge-base --is-ancestor a3601693 origin/main` → `EXIT=0` (before and after tests)
- Merge perimeter: `git diff --name-only 0fabce38..1fb1482` → **17 files**;
  `backend/main.py` **absent**; none of the 5 audit/architecture files present in
  `main`'s tree (`git ls-tree -r main | grep -Ei 'audit_corrective|audit_idempotency|ADR-015|WO-078|WO-079'` → `GREP_EXIT=1`)
- WO-080 commit `a3601693` perimeter identical to the same 17-file set
- Both untracked audit tests present and unstaged

## Verification

Test commands and live results (from the report):

1. `cd /opt/data/tactical_core_github/backend && PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.:.. ../.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_wo080_whatsapp_ingress.py`
   → exit 0; **24 passed, 1 warning in 1.58s** (Python 3.13.5, pytest 9.1.1, rootdir `pytest.ini`)
2. Supplementary, same flags, over `tests/test_wo019_event_replay_consistency.py tests/test_wo030_production_delivery_wiring.py tests/test_wo060_observation_read_model.py`
   → exit 0; **36 passed, 1 warning in 2.27s**

Per-claim classification:

| Claim | Bucket | Basis |
| --- | --- | --- |
| Durable-before-ACK (200 iff `IngestResult.durable=True`; else 503) | VERIFIED (test) | tests 15, 15b |
| Deduplication (same `message_id` → one durable event, `duplicate=True`) | VERIFIED (test) | tests 10, 11; replay/outbox via `test_wo019` (13 passed) + `test_wo030` (11 passed) |
| Observation + Operator Wall reached | VERIFIED (test) | `test_wo080_13` (`ObservationRepository.get_by_immutable_id`); operator read-model `test_wo060` (12 passed) |
| Restart/recovery | VERIFIED **by simulation only** | test 16: fresh runtime over the same durable store |
| Event path HTTP→signature→parse→identity→EventFactory→pipeline→journal→Observation→Operator Wall | VERIFIED (inspection) | traced to file + class + function |
| Live Meta → production endpoint | **NOT VERIFIED** | no deployed ingress/TLS/DNS/public exposure |
| Real process/container restart | **NOT VERIFIED** | only in-process fresh-runtime simulation |

## Architecture / Implementation

Event path evidence (file → function), as recorded:

1. HTTP webhook GET/POST — `backend/app/whatsapp_ingress/app.py` → `create_whatsapp_ingress_app()` / `verify()` / `receive()`
2. Signature (constant-time HMAC-SHA256 over raw body) — `whatsapp_ingress/signature.py` → `verify_signature()` / `compute_signature()`
3. Parsing/normalization — `event_sources/adapters/whatsapp_parser.py` → `WhatsAppPayloadNormalizer.normalize_webhook()` / `_normalize_message()`
4. Deterministic identity + dedup — `event_sources/identity/event_identity.py` → `_whatsapp_identity()`, `EventIdentityResolver.resolve()` (UUID5 keyed `phone_number_id|message_id`)
5. Canonical construction — `event_sources/factory/event_factory.py` via `runtime.submit_raw` (`EventFactory.create_event`)
6. Durable seam — `event_sources/runtime/adapter_runtime.py` → `AdapterRuntime.submit_raw()` / `set_ingest_durability_probe()` / `IngestResult(durable)`
7. Durable journal — `event_repository/durable/sqlalchemy_event_repository.py` (`UNIQUE(event_id)`)
8. Observation — `observation/canonical_adapter.py` → `derive_event_type()`; `observation/models.py` → `EVENT_TYPE_MAPPINGS["whatsapp.message"]`
9. Operator Wall/feed — existing read-model; `test_wo080_13` + `test_wo060_observation_read_model.py`

## Findings

- `FILES_MODIFIED: NONE`; `COMMITS_OR_PUSHES: NONE`.
- Worktree `git status --porcelain=v1` byte-identical BEFORE/AFTER:

  ```
   M backend/app/plugins/manager/__pycache__/plugin_manager.cpython-313.pyc
  ?? 500
  ?? backend/tests/test_wo080_audit_idempotency.py
  ?? backend/tests/test_wo080_whatsapp_audit_corrective.py
  ?? docs/adr/ADR-015-WhatsApp-Ingress-Architecture.md
  ?? docs/work_orders/WO-078-WHATSAPP-INBOUND-HTTPS-ARCHITECTURE-GATE.md
  ?? docs/work_orders/WO-079-WHATSAPP-INGRESS-ARCHITECTURE-DECISION-GATE.md
  ```

- Protected artifacts preserved: `?? 500` observed **only** as porcelain text;
  `plugin_manager.cpython-313.pyc` kept the same pre-existing ` M` status (all runs
  used `PYTHONDONTWRITEBYTECODE=1` + `-p no:cacheprovider`); the 5 audit/architecture
  files stayed `??` and absent from `main`'s tree.
- Instruction-vs-worktree filename mismatch: the WO listed
  `backend/tests/test_wo080_audit_corrective.py`; the actual untracked file is
  `test_wo080_whatsapp_audit_corrective.py`. Both audit files preserved, neither opened.

## Limitations

- No live Meta → production E2E (real signature/delivery/ACK against Meta).
- Restart/recovery verified only by in-process simulation — no real
  process/container restart.
- Public exposure / TLS / firewall / DNS are outside the WO scope.
- Full backend suite deliberately not run.
- **Reconciliation note (WO-086 §5 vs evidence):** WO-086 §5 described WO-081 as
  "Telegram independent verification". The actual WO-081 prompt and report are
  titled **"WO-081 — WHATSAPP INGRESS INDEPENDENT E2E VERIFICATION"**. This document
  records the WhatsApp subject, as the evidence supports.

## Production Gaps

- Live Meta webhook, deployed ingress endpoint, TLS/DNS and public exposure are not
  established.

## Git / Repository State

| Item | Value |
| --- | --- |
| Files modified by the WO | NONE |
| Commits / pushes | NONE |
| `HEAD` movement | none (`a3601693` unchanged) |
| Refs movement | none |

## Final Verdict

`ACCEPTED` — integration of WO-080 into `main` confirmed, targeted tests green,
protected artifacts and local state preserved. The verdict covers **local
verification only**; production Meta E2E remains `NOT VERIFIED`.

## Evidence Provenance

- Report transcript preserved in the local Hermes session store (session
  `api-b759b2cbe81446cc`, recorded 03 Oct 2026).
- No repository copy of this WO existed before WO-086 (`git ls-tree -r HEAD docs/work_orders/`
  had no WO-081 entry).
