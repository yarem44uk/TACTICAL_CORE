# ADR-013 — Severity Ruleset Single-Source Architecture

**Date:** 2026-09-02
**Status:** Accepted
**Deciders:** Chief Systems Architect

---

## Context

ADR-012 (Accepted) establishes the operational classification model: a deterministic, read-only, derived, replayable, computed-on-demand **baseline classification** as a distinct concept from the immutable canonical event and from mutable operator assessment. AD-012.10 makes the **Baseline Classifier** the sole semantic owner of baseline severity.

Following the WO-037-06 runtime/governance ruleset binding audit, the current state is:

```text
RUNTIME_RULE_SOURCE      = backend/app/operator/severity.py
GOVERNANCE_RULE_SOURCE   = docs/governance/SEVERITY_RULES_v1.0.0.md
RUNTIME_CONSUMES_GOVERNANCE_FILE = NO
RUNTIME_RULES_HARDCODED  = YES
VERSION_CONTENT_BINDING  = NONE
CURRENT_RULE_SEMANTIC_MATCH = YES
GOVERNANCE_DRIFT_RISK    = HIGH
```

The runtime implementation contains the four ratified executable rules directly in Python. The governance artifact independently defines the same rules. The two currently match. The problem is **not** current semantic mismatch; the problem is that the architecture permits future silent divergence. The rule set is duplicated across two representations that share no binding, no version linkage, and no content-integrity relationship. Nothing mechanically prevents one representation from being edited without the other, and nothing detects the resulting divergence at build or runtime.

## Problem Statement

1. The same severity semantics are expressed in two places that share no authoritative relationship.
2. Markdown is human-readable prose, not an executable input; it cannot be safely consumed by runtime logic without a parser, and it is not a stable semantic contract.
3. There is no binding between a ruleset version and its content, so a version label alone carries no guarantee of content identity.
4. There is no integrity check to detect unauthorized or accidental modification of the authoritative ruleset.
5. There is no automated gate that fails when governance and runtime semantics diverge.
6. There is no defined behavior for a malformed or non-loadable ruleset; the current design could silently fall back to stale hardcoded rules.
7. Released rulesets are not protected against content mutation under an unchanged semantic version.

The architecture must make the ruleset a **single semantic source of truth** so that the governance representation, the runtime behavior, and the version identity all derive from one authoritative artifact.

## Decision

- **ARCHITECTURE_DECISION = APPROVED FOR FOLLOW-UP DESIGN**
- **IMPLEMENTATION_AUTHORIZED = NO**
- **ADOPT_SINGLE_SEMANTIC_SOURCE = YES** — adopt a Git-controlled machine-readable severity ruleset as the single semantic source of truth.
- **AUTHORITATIVE_SOURCE = Git-controlled machine-readable severity ruleset artifact.**
- **RUNTIME_CONSUMPTION_SOURCE = the same Git-controlled machine-readable severity ruleset artifact.**
- **HUMAN_DOCUMENT_ROLE = human-readable governance representation; not an independent semantic authority.**
- **DERIVATION_MECHANISM = the human-readable Markdown is mechanically generated from the authoritative machine-readable ruleset.**
- **VERSION_BINDING = ruleset semantic version + content-integrity binding.**
- **CONTENT_INTEGRITY = SHA-256 or equivalent cryptographic content binding.**
- **DRIFT_DETECTION = mandatory automated validation / CI failure on semantic divergence.**
- **MALFORMED_RULE_BEHAVIOR = FAIL CLOSED; classifier initialization must fail; no fallback to hardcoded rules.**
- **RELEASE_IMMUTABILITY = YES; released ruleset content cannot change under the same semantic version.**

Important identity rule: **ruleset version alone is NOT sufficient identity.** Identical version labels carrying different contents would otherwise permit silent semantic replacement. Identity is the combination of the semantic version and the content-integrity binding; a content change under the same version label is a release-integrity violation.

## Authoritative Source

The authoritative source is a **Git-controlled machine-readable severity ruleset artifact**. It lives in the repository, is versioned by Git, and is the artifact from which runtime classification and the governance representation are both generated. It is the single authoritative source of approved **rule content**.

Single semantic source of truth is explicitly **not** the same as a single physical file. Markdown may coexist with the machine-readable artifact, but it MUST NOT be an independent semantic authority. The human-readable document is a representation of the authoritative ruleset, not a second source of truth.

### AD-012.10 Reconciliation — Rule Content vs Semantic Ownership

This ADR does NOT replace AD-012.10 and MUST NOT be read as making the machine-readable ruleset the semantic owner of classification. The two authorities are distinct and complementary:

- **MACHINE-READABLE RULESET = single authoritative source of approved RULE CONTENT.** It is the authoritative definition of what the rules are: the conditions, mappings, and values the classifier applies.
- **BASELINE CLASSIFIER = sole semantic owner of baseline severity classification.** AD-012.10 is unchanged. The classifier owns the meaning of the classification — how the rules are applied to events to produce a baseline severity result.

The intended model:

```text
             ┌─────────────────────────────┐
             │ MACHINE-READABLE RULESET    │
             │ authoritative rule CONTENT  │
             └──────────────┬──────────────┘
                            │
                            ▼
             ┌─────────────────────────────┐
             │ BASELINE CLASSIFIER         │
             │ sole semantic owner         │
             │ of classification           │
             └──────────────┬──────────────┘
                            │
                            ▼
                       Severity result
```

The ruleset supplies the approved rule content; the classifier remains the sole semantic owner of the baseline severity classification. The ruleset does not replace the classifier's semantic ownership, and the classifier does not independently author rule content.

## Runtime Consumption

The runtime classifier consumes the **same Git-controlled machine-readable ruleset artifact** that is authoritative. At classification time the artifact is loaded and evaluated. The runtime does not contain a second copy of the rules as authoritative input.

Consumption preserves the existing baseline-classification properties from AD-012.9:

- deterministic
- read-only
- derived
- replayable
- computed on demand

## Human-Readable Governance Representation

The human-readable governance document (`docs/governance/SEVERITY_RULES_v1.0.0.md` in current terms) is a **generated representation** of the authoritative machine-readable ruleset. It is mechanically generated from the authoritative ruleset. It exists for review, communication, and audit by humans. It is NOT an independent semantic authority.

The architectural rule is:

```text
machine-readable ruleset
        ↓
Markdown generation
```

Consequently:

- Markdown is **not independently authored as semantic rule data**.
- Manual semantic changes to the Markdown are **not authoritative**.
- Generated-Markdown divergence from the authoritative ruleset is **an error**.
- **CI MUST fail** when the generated Markdown does not correspond to the authoritative machine-readable ruleset.

The generation mechanism is not defined in this ADR; the subsequent Work Order defines the concrete generation tooling.

## Version and Content Binding

- Each ruleset release carries a **semantic version**.
- Each ruleset release carries a **content-integrity binding** (SHA-256 or equivalent) over the authoritative artifact.
- The runtime records and verifies the binding of the ruleset it consumes.
- **Ruleset version alone is NOT sufficient identity** — identity is the pair (semantic version, content-integrity binding).

Content integrity / hash binding establishes **artifact identity and integrity**; it does not by itself establish semantic correctness or domain approval. Semantic correctness remains governed by the approved ruleset and the architecture governance process. No new approval roles are introduced by this ADR.

## Drift Detection

Drift detection is **mandatory automated validation**. The build/CI pipeline MUST validate that:

- the machine-readable ruleset is well-formed and loadable;
- the runtime consumption source resolves to the authoritative artifact;
- the human-readable governance representation matches the authoritative artifact (generated);
- the content-integrity binding matches the artifact content.

**Semantic divergence MUST cause CI failure.** Drift between governance and runtime semantics is a build failure, not a warning. This is the mechanism that makes divergence structurally impossible to ship silently.

## Malformed Ruleset Behavior

**FAIL CLOSED.** If the ruleset cannot be loaded and validated, **classifier initialization MUST fail**. There MUST be **no fallback to hardcoded rules**. Silent fallback to stale or embedded rules is explicitly prohibited, because it would reintroduce a second semantic authority and defeat the single-source guarantee. A malformed ruleset is an operational error that must be surfaced and fixed, not masked.

Classifier initialization fails closed for **at least** the following conditions:

- missing ruleset;
- malformed ruleset;
- schema-invalid ruleset;
- invalid ruleset version;
- duplicate/conflicting rules;
- unknown fields where prohibited;
- unsupported rule semantics;
- content-integrity/hash failure.

All such conditions MUST result in **classifier initialization failure**. There MUST be:

- **NO fallback to hardcoded Python rules**;
- **NO silent partial loading**;
- **NO silent rule omission**;
- **NO permissive recovery**.

This ADR does not define exact exception classes or implementation code; the subsequent Work Order defines the concrete failure handling within this boundary.

## Release Immutability

**RELEASE_IMMUTABILITY = YES.** Released ruleset content cannot change under the same semantic version. Once a semantic version is released, its content is fixed. Any change to the ruleset requires a new semantic version and a new content-integrity binding. Modifying the content of an already-released ruleset under the same version label is a release-integrity violation and is detected by the content-integrity binding.

## Alternatives Considered

### OPTION A — Markdown as Runtime Source

**Rejected.** Treating governance prose as executable input creates fragility, parser coupling, format dependence, and unnecessary operational risk. Markdown is not a stable machine contract; changes in formatting would change runtime behavior. Prose is a representation, not an authoritative executable source.

### OPTION B — Machine-Readable Ruleset as Single Semantic Source

**Adopted.** A Git-controlled machine-readable ruleset is authoritative; the runtime consumes it; the human-readable document is mechanically generated from it. This is the recommended and adopted architecture.

### OPTION C — Generated Runtime Artifact

**Documented as viable but not adopted.** A generated runtime artifact (a compiled or code-generated representation produced from the ruleset at build time) is a valid approach, but is unnecessarily more complex than required for the present architecture. It may be considered later if implementation constraints demonstrate a need. It is not the architecture chosen now.

### OPTION D — Hardcoded Python + Drift Test

**Rejected as the final architecture.** Keeping the rules hardcoded in Python and adding a test that checks for drift leaves two semantic representations that remain independent authorities. Drift remains structurally possible outside the validation path, because the validation test is not the source of truth — the two copies are. The single-source guarantee is only achieved when the runtime consumes the authoritative artifact directly, not when it holds an independent copy that a test happens to check.

## Consequences

Positive:

- The governance representation and runtime behavior share one authoritative semantic source.
- Semantic divergence is structurally detectable and causes CI failure.
- Rule changes are versioned and content-bound, preventing silent semantic replacement.
- Malformed or tampered rulesets fail closed rather than falling back to stale rules.
- The ruleset is immutable per release, providing a stable contract for replay and audit.
- No new durable state, no schema change, no external service, no cloud dependency — offline operation and determinism are preserved.

Negative / open:

- Requires a concrete machine-readable format and a runtime loader, both to be defined by a separate Work Order.
- Requires CI validation infrastructure for drift detection and content integrity.
- Requires migration of the current hardcoded runtime rules to consume the authoritative artifact.
- The human-readable governance document becomes a derived artifact; its editing workflow must change so that changes originate in the authoritative source.

## Security Considerations

The ruleset must not bypass existing controls: authentication, authorization, read-only guarantees, and operator-process isolation.

The content-integrity binding protects against unauthorized or accidental modification of the authoritative ruleset. The FAIL-CLOSED behavior ensures a tampered or malformed ruleset cannot silently produce an incorrect classification. Ruleset loading and integrity verification are part of classifier initialization and must be subject to the same isolation guarantees as the rest of the classifier.

The machine-readable ruleset is **declarative data, never executable code**. The runtime loader MUST use a safe data parser and MUST NOT permit arbitrary object deserialization, custom executable tags, embedded code, or equivalent code-execution mechanisms. This ADR does not prescribe a specific parser library; the subsequent Work Order may select the concrete safe parser.

## Operational / Offline Considerations

This architecture preserves:

- offline runtime;
- no cloud dependency;
- no external rules service;
- no external IdP;
- no telemetry;
- consumer-side ownership.

The authoritative ruleset is a Git-controlled artifact, so it is available offline at runtime without any network dependency. The ruleset is loaded and verified locally; no remote fetch is required for classification.

## Replay / Determinism Considerations

Baseline classification remains deterministic and replayable (AD-012.9). Because the runtime consumes a fixed, immutable, content-bound ruleset, replaying classification over the same authoritative events with the same released ruleset version yields the same result. The content-integrity binding guarantees that the ruleset used in a replay is byte-identical to the released version, which is what makes deterministic replay meaningful across time and environments.

## Explicit Non-Goals

This ADR decides architecture only. It does NOT implement anything. The following are explicitly NOT within scope:

- No definition of the exact YAML/JSON schema for the machine-readable ruleset (a subsequent Work Order defines the concrete format and runtime loader).
- No inventing of field names beyond what is necessary to define the architectural boundary.
- No change to `backend/`, `tests/`, or `docs/governance/SEVERITY_RULES_v1.0.0.md`.
- No implementation of the runtime loader.
- No CI implementation.
- No migration of the current hardcoded runtime rules.

The architecture MUST NOT become a mechanism for introducing:

- CAND-001;
- CAND-003;
- new tactical mappings;
- content classification;
- AI classification;
- priority → severity;
- urgency → severity;
- confidence → severity.

## Implementation Boundary

- **ARCHITECTURE_DECISION = APPROVED FOR FOLLOW-UP DESIGN**
- **IMPLEMENTATION_AUTHORIZED = NO**

This ADR does NOT authorize implementation. A separate Work Order is required after this ADR is independently reviewed and approved. The follow-up Work Order must define and implement the concrete machine-readable ruleset format and runtime loader, within the boundary established here.

## Required Follow-Up Work

A subsequent Work Order must define:

1. The concrete machine-readable ruleset format (schema) and its location in the repository.
2. The runtime loader and its consumption path.
3. The content-integrity (SHA-256 or equivalent) binding mechanism.
4. The CI drift-detection and integrity validation gates.
5. The migration of the current hardcoded runtime rules to consume the authoritative artifact.
6. The relationship and synchronization workflow between the authoritative ruleset and the human-readable governance representation.
7. The release/immutability process for ruleset versions.

All follow-up work must preserve the runtime boundary: no durable severity state, no Event schema change, no DurableCanonicalEvent change, no database migration, no external rules service, offline operation, deterministic evaluation, read-only classification, consumer-side ownership.
