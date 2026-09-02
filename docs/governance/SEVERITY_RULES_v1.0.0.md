# TACTICAL CORE — Ratified Baseline Severity Ruleset v1.0.0

## Document Identity

| Field | Value |
| --- | --- |
| PROJECT | TACTICAL CORE |
| RULESET_VERSION | SEVERITY-RULES-v1.0.0 |
| STATUS | RATIFIED_FOR_CONSUMPTION |
| GOVERNING_ADR | ADR-012 (Accepted) |

This document is a governance artifact. It is **NOT** implementation code.
It defines the ratified baseline operational severity classification rules and the
governance contract that governs them.

---

## 1. Severity Taxonomy

The operational severity taxonomy is defined by ADR-012.8 (Accepted) as:

```
INFO < WARNING < THREAT < CRITICAL
```

| Severity | Ordering | Semantic intent |
| --- | --- | --- |
| INFO | 1 | routine / negligible operational impact |
| WARNING | 2 | meaningful deviation or emerging operational concern |
| THREAT | 3 | direct or significant operational threat |
| CRITICAL | 4 | critical impact to mission, force safety, or system survivability |

These are architectural definitions. They are not source-specific mappings.

---

## 2. Approved Severity Semantics

The semantic intent of each level is as defined above (from ADR-012.8). The
baseline classifier assigns one of these four levels to an event based on the
ratified executable rules in section 3. No other level is admissible.

---

## 3. Ratified Executable Rules

The following rules are ratified for consumption. They are executable in the
sense that they are fully determined by the event facts named in their
conditions.

### CAND-002

```
RULE_ID = CAND-002
EVENT_TYPE = signal.failed
SOURCE = signal

CONDITION =
event_type == "signal.failed"
AND
source == "signal"

OUTPUT_SEVERITY = WARNING

STATUS = RATIFIED
```

### CAND-004

```
RULE_ID = CAND-004
EVENT_TYPE = observation.verified
SOURCE = *

CONDITION =
event_type == "observation.verified"

OUTPUT_SEVERITY = INFO

STATUS = RATIFIED_WITH_LIMITATION
```

**Mandatory limitation (must not be removed or weakened):**

> Payload content is not classified by the baseline classifier. A verified observation being INFO does not mean its content is non-threatening. Content-based threat/criticality analysis is outside the baseline event classification mechanism.

### CAND-005

```
RULE_ID = CAND-005
EVENT_TYPE = relation.severed
SOURCE = *

CONDITION =
event_type == "relation.severed"

OUTPUT_SEVERITY = INFO

STATUS = RATIFIED
```

### CAND-006

```
RULE_ID = CAND-006
EVENT_TYPE = system.startup
SOURCE = *

CONDITION =
event_type == "system.startup"

OUTPUT_SEVERITY = INFO

STATUS = RATIFIED
```

---

## 4. CAND-004 Limitation (Explicit)

The limitation on CAND-004 is authoritative and is restated here for emphasis:

**Mandatory limitation (must not be removed or weakened):**

> Payload content is not classified by the baseline classifier. A verified observation being INFO does not mean its content is non-threatening. Content-based threat/criticality analysis is outside the baseline event classification mechanism.

---

## 5. Non-Executable Rules

The following candidate rules were evaluated and are **NOT_EXECUTABLE**. They are
preserved here as record. They are not part of the ratified executable set.

### CAND-001

```
CAND-001
+
explicit conditional discriminator
-> severity
```

Status: **NOT_EXECUTABLE**

Reason: The current event model contains no deterministic fact establishing operational criticality. The event type name system.error MUST NOT itself be interpreted as CRITICAL.

### CAND-003

```
CAND-003
+
explicit conditional discriminator
-> severity
```

Status: **NOT_EXECUTABLE**

Reason: The current event model contains no deterministic discriminator establishing material operational correction. The event type name observation.retracted MUST NOT itself be interpreted as WARNING.

---

## 6. Unmapped Policy

```
UNMAPPED_POLICY = EXPLICIT_UNCLASSIFIED
```

When no approved rule matches an event, the baseline classification is:

```
UNCLASSIFIED
```

There MUST be no silent `UNCLASSIFIED -> INFO` conversion. An event is only
classified when an approved rule matches.

---

## 7. Rule Precedence

```
EVENT-SPECIFIC > SOURCE-SPECIFIC > GENERIC
```

When two rules of the same specificity match the same event:

```
NO SILENT RESOLUTION
```

Conflict at equal specificity is not automatically resolved by the baseline
classifier. Any resolution requires an explicit, separately approved decision.

---

## 8. Coverage Boundary

This ruleset does **NOT** claim universal event coverage.

Current ratified executable coverage consists of:

```
signal.failed + source=signal
observation.verified
relation.severed
system.startup
```

All other events remain:

```
UNCLASSIFIED
```

unless separately approved by a future rule.

---

## 9. Versioning

```
RULESET_VERSION_FORMAT = SEVERITY-RULES-vMAJOR.MINOR.PATCH
VERSION_STORAGE = Git-controlled
VERSION_OWNER = Domain Owner
VERSION_APPROVER = Architecture Governance
```

The ruleset version is reproducible from Git-controlled artifacts. No database
rule registry, external rule server, or cloud rules service is used.

---

## 10. Lifecycle

The lifecycle states are:

```
DRAFT
REVIEW
APPROVED
ACTIVE
DEPRECATED
RETIRED
```

Ownership:

```
LIFECYCLE_OWNER = Domain Owner
LIFECYCLE_APPROVER = Architecture Governance
```

The current ruleset status is `RATIFIED_FOR_CONSUMPTION`. Generating this
document does **not** mark the ruleset `ACTIVE` at runtime.

---

## 11. Change Control

```
RULE_CHANGE_REQUIRES_NEW_VERSION = YES
RULE_CHANGE_REQUIRES_DOMAIN_APPROVAL = YES
RULE_CHANGE_REQUIRES_ARCHITECTURE_REVIEW = YES
RULE_CHANGE_REQUIRES_REPLAY_REVALIDATION = YES
```

Any semantic change to an existing rule requires a new rule version, a new
evidence reference, and new approval. No silent in-place semantic replacement.

---

## 12. Replay Invariant

```
same authoritative event facts
+
same ruleset version
=
same baseline severity
```

Classification must not depend on:

```
operator state
current time
network state
randomness
external API
cloud service
AI nondeterminism
mutable assessment
```

---

## 13. Dimension Separation

```
PRIORITY != SEVERITY
URGENCY != SEVERITY
CONFIDENCE != SEVERITY
```

Priority, urgency, and confidence are independent dimensions. No automatic
conversion to severity is permitted without a separate authoritative domain
decision.

---

## 14. Normalization Status

```
NORMALIZATION_RULE_COUNT = 0
```

No source-specific normalization mapping is currently ratified. No such mapping
is invented here. Vendor values (e.g., `critical`, `red`, `urgent`, `90`,
`alarm`) are not automatically equivalent to operational severity.

---

## 15. Implementation Boundary

This document does **NOT** authorize modifications to:

```
EventPipeline
DurableDeliveryDispatcher
ReconstructionService
projection
checkpoint
outbox
retry
dead-letter
source adapters
CanonicalEvent
DurableCanonicalEvent
```

### Persisted / Not Implemented

```
RULESET_PERSISTED = YES

CLASSIFIER_IMPLEMENTED = YES

OPERATOR_SEVERITY_FILTER_IMPLEMENTED = YES

SCHEMA_CHANGED = NO

DATABASE_CHANGED = NO

WO03707_IMPLEMENTATION_AUTHORIZED = YES
```

---

## 16. Governance Notes

- This ruleset is a documentation/governance artifact.
- It is `RATIFIED_FOR_CONSUMPTION`, not `ACTIVE` at runtime.
- The classifier is implemented as a consumer-side, computed-on-demand,
  read-only mechanism (ADR-012). The machine-readable TOML is the single
  rule-content source; the Markdown is a generated representation.
- Any future rule change requires a new ruleset version, domain approval,
  architecture governance, replay revalidation, and newly generated Markdown,
  consistent with ADR-012 and ADR-013.
