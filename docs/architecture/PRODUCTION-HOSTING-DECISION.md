# PRODUCTION HOSTING DECISION — TACTICAL_CORE

**Document type:** Architecture decision record (documentation only)
**Status:** `CONDITIONALLY APPROVED — NOT FINAL`
**Production deployment status:** `BLOCKED — PRODUCTION ACCESS NOT ESTABLISHED`
**Prepared by:** WO-091 (documentation publication gate, DOCUMENTATION ONLY)
**Baseline:** `10c030900207cbaa928d2ea06c753506a4f04ab4` (`main`)
**Evidence base:** WO-089 design gate and WO-090 independent audit (see references below)

---

## 1. Decision status

`CONDITIONALLY APPROVED — NOT FINAL`.

The provisional architecture below is approved only as a provisional default. It is **not**
ratified architecture and carries no production authorization. It may not be treated as
final until its named conditions (section 3) are closed with evidence and independently
verified. This document does not authorize a production-readiness declaration.

## 2. Provisional preferred topology (design only — not implemented)

Managed VM hosting a **supervised ingress process bound to loopback**, fronted by a
**TLS-terminating reverse proxy** publishing only the public TLS port, with the durable
store on **dedicated durable persistent storage** (a local volume, never a container's
ephemeral filesystem).

This provisional preference is recorded by WO-090 as Option A, approved conditionally as a
provisional default only. No host, provider, domain, credential, cost or account is named
here; none is evidenced in the repository. Nothing in this section has been provisioned,
built, deployed or tested.

## 3. Open conditions precedent to any ratification or deployment

1. **Production access is not established.** No production server exists, no domain, no DNS,
   no TLS certificate, no secret store, no monitoring, no backup/restore procedure and no
   approved provisioning path has been established.
2. **SQLite multi-writer safety remains unproven.** No evidence demonstrates safe concurrent
   writers against one SQLite file; multi-process writing is unsupported by any evidence and
   untested.
3. **`MAX(seq)+1` collision-handling defect.** The durable write path allocates sequence
   numbers via `MAX(seq)+1` under `UNIQUE(seq)`, and a sequence collision is treated as if it
   were a duplicate event. This requires remediation **and** independent verification. No
   remediation has occurred.
4. **Observation/Wall recovery after a failed projection.** A durable event whose downstream
   projection is rejected can be marked delivered and therefore never retried, leaving it
   invisible on the operator wall with no catch-up path. This requires remediation **and**
   independent verification. No remediation has occurred.
5. **Versioned and controlled database migration procedure.** A revision-tracked,
   deterministic migration step for an existing production database is required before
   deployment. Today the runtime path uses unversioned schema creation; this gap must be
   closed by a controlled migration procedure before any deployment.
6. **Oversized webhook body handling.** Body-size limiting is enforced only after the full
   body has been buffered, and the rejection branch has no test coverage. This requires a
   **bounded-read design and test coverage**. No such design or test exists.
7. **Database engine decision.** SQLite may be retained **only if** a single-writer topology
   and its concurrency and recovery behaviour are demonstrated. PostgreSQL remains an
   alternative for a multi-process topology, subject to an **explicit decision**. No engine
   decision is made by this document.
8. **No authorization to provision or register.** No production provisioning is authorized by
   these documents, and no Telegram webhook registration is authorized by these documents.

## 4. What this document and its evidence base explicitly do NOT claim

- No remediation of any defect listed above has occurred.
- No code, configuration, test, runtime or infrastructure change is associated with this
  decision.
- No test execution, deployment, provisioning or external API call is represented as
  performed.
- No production-readiness is declared.

## 5. References (repository-relative)

- `docs/work_orders/WO-089-PRODUCTION-HOSTING-ARCHITECTURE-AND-DEPLOYMENT-READINESS-DESIGN-GATE.md`
  — production hosting architecture and deployment readiness design gate (design only; its own
  verdict: `BLOCKED — PRODUCTION ACCESS NOT ESTABLISHED`).
- `docs/work_orders/WO-090-INDEPENDENT-AUDIT-REPORT.md`
  — independent audit of WO-089 (overall verdict: `ACCEPTED WITH CONDITIONS`; includes the
  publication provenance header recording that the report body was recovered from an
  identified conversation record and reproduced unaltered).

Both documents are published verbatim (WO-090 with a clearly separated provenance header
placed outside its report body). Neither document is summarized, rewritten or superseded
here; where this decision document states a condition, the authoritative wording remains the
one in those two reports.

---

**STOP.** Documentation prepared only. No staging, no commit, no push, no pull request, no
provisioning, no deployment, no webhook registration, no infrastructure action.
