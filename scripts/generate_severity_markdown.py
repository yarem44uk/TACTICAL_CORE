"""WO-037-07 — Deterministic Markdown generator for the severity ruleset.

Generates ``docs/governance/SEVERITY_RULES_v1.0.0.md`` from the authoritative
machine-readable ruleset ``docs/governance/SEVERITY_RULES_v1.0.0.toml``.

The generated Markdown is a mechanical, human-readable representation of the
TOML. It is NOT a second source of executable rules — the TOML artifact is the
single rule-content authority (ADR-013).

Determinism: the generator depends only on the TOML artifact content and this
template, so the same artifact always yields byte-identical output. This is
what makes the regenerate-and-compare CI drift check sound.

Usage:
    python scripts/generate_severity_markdown.py              # write the .md
    python scripts/generate_severity_markdown.py --check      # drift check only
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import tomllib

_REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TOML = _REPO_ROOT / "docs" / "governance" / "SEVERITY_RULES_v1.0.0.toml"
DEFAULT_MD = _REPO_ROOT / "docs" / "governance" / "SEVERITY_RULES_v1.0.0.md"

# Static governance prose sections, in document order. The rule-bearing
# sections (§3, §4, §5, §8) are generated from the TOML artifact and inserted
# in their numeric position by ``generate_markdown``.
_STATIC_SECTIONS = {
    "1": """## 1. Severity Taxonomy

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

These are architectural definitions. They are not source-specific mappings.""",
    "2": """## 2. Approved Severity Semantics

The semantic intent of each level is as defined above (from ADR-012.8). The
baseline classifier assigns one of these four levels to an event based on the
ratified executable rules in section 3. No other level is admissible.""",
    "6": """## 6. Unmapped Policy

```
UNMAPPED_POLICY = EXPLICIT_UNCLASSIFIED
```

When no approved rule matches an event, the baseline classification is:

```
UNCLASSIFIED
```

There MUST be no silent `UNCLASSIFIED -> INFO` conversion. An event is only
classified when an approved rule matches.""",
    "7": """## 7. Rule Precedence

```
EVENT-SPECIFIC > SOURCE-SPECIFIC > GENERIC
```

When two rules of the same specificity match the same event:

```
NO SILENT RESOLUTION
```

Conflict at equal specificity is not automatically resolved by the baseline
classifier. Any resolution requires an explicit, separately approved decision.""",
    "9": """## 9. Versioning

```
RULESET_VERSION_FORMAT = SEVERITY-RULES-vMAJOR.MINOR.PATCH
VERSION_STORAGE = Git-controlled
VERSION_OWNER = Domain Owner
VERSION_APPROVER = Architecture Governance
```

The ruleset version is reproducible from Git-controlled artifacts. No database
rule registry, external rule server, or cloud rules service is used.""",
    "10": """## 10. Lifecycle

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
document does **not** mark the ruleset `ACTIVE` at runtime.""",
    "11": """## 11. Change Control

```
RULE_CHANGE_REQUIRES_NEW_VERSION = YES
RULE_CHANGE_REQUIRES_DOMAIN_APPROVAL = YES
RULE_CHANGE_REQUIRES_ARCHITECTURE_REVIEW = YES
RULE_CHANGE_REQUIRES_REPLAY_REVALIDATION = YES
```

Any semantic change to an existing rule requires a new rule version, a new
evidence reference, and new approval. No silent in-place semantic replacement.""",
    "12": """## 12. Replay Invariant

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
```""",
    "13": """## 13. Dimension Separation

```
PRIORITY != SEVERITY
URGENCY != SEVERITY
CONFIDENCE != SEVERITY
```

Priority, urgency, and confidence are independent dimensions. No automatic
conversion to severity is permitted without a separate authoritative domain
decision.""",
    "14": """## 14. Normalization Status

```
NORMALIZATION_RULE_COUNT = 0
```

No source-specific normalization mapping is currently ratified. No such mapping
is invented here. Vendor values (e.g., `critical`, `red`, `urgent`, `90`,
`alarm`) are not automatically equivalent to operational severity.""",
    "15": """## 15. Implementation Boundary

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
```""",
    "16": """## 16. Governance Notes

- This ruleset is a documentation/governance artifact.
- It is `RATIFIED_FOR_CONSUMPTION`, not `ACTIVE` at runtime.
- The classifier is implemented as a consumer-side, computed-on-demand,
  read-only mechanism (ADR-012). The machine-readable TOML is the single
  rule-content source; the Markdown is a generated representation.
- Any future rule change requires a new ruleset version, domain approval,
  architecture governance, replay revalidation, and newly generated Markdown,
  consistent with ADR-012 and ADR-013.""",
}


def _render_rule(rule: dict) -> str:
    """Render one executable rule block from a ``[[rules]]`` record."""
    source = rule.get("source", "*")
    lines = [
        "```",
        f"RULE_ID = {rule['rule_id']}",
        f"EVENT_TYPE = {rule['event_type']}",
        f"SOURCE = {source}",
        "",
        "CONDITION =",
        f'event_type == "{rule["event_type"]}"',
    ]
    if rule.get("source") and rule["source"] != "*":
        lines.append("AND")
        lines.append(f'source == "{rule["source"]}"')
    lines += [
        "",
        f"OUTPUT_SEVERITY = {rule['severity']}",
        "",
        f"STATUS = {rule['status']}",
        "```",
    ]
    return "\n".join(lines)


def _render_limitation(rule: dict) -> str:
    """Render the mandatory CAND-004 limitation block."""
    limitation = rule.get("limitation", "")
    return (
        "**Mandatory limitation (must not be removed or weakened):**\n\n"
        "> " + limitation.replace("\n", "\n> ")
    )


def _render_non_executable(record: dict) -> str:
    """Render one non-executable candidate record block."""
    return (
        "```\n"
        f"{record['rule_id']}\n"
        "+\n"
        "explicit conditional discriminator\n"
        "-> severity\n"
        "```\n\n"
        f"Status: **{record['status']}**\n\n"
        f"Reason: {record['reason']}"
    )


def _render_coverage_boundary(rules: list[dict]) -> str:
    """Render the coverage boundary from the executable rules' event types."""
    lines = ["```"]
    for rule in rules:
        if rule.get("source") and rule["source"] != "*":
            lines.append(f"{rule['event_type']} + source={rule['source']}")
        else:
            lines.append(rule["event_type"])
    lines.append("```")
    return "\n".join(lines)


def _section3(rules: list[dict]) -> str:
    """Generate §3 — Ratified Executable Rules (from TOML)."""
    parts = [
        "## 3. Ratified Executable Rules",
        "",
        "The following rules are ratified for consumption. They are executable in the",
        "sense that they are fully determined by the event facts named in their",
        "conditions.",
        "",
    ]
    for rule in rules:
        parts.append(f"### {rule['rule_id']}")
        parts.append("")
        parts.append(_render_rule(rule))
        if rule.get("limitation"):
            parts.append("")
            parts.append(_render_limitation(rule))
        parts.append("")
    return "\n".join(parts).rstrip()


def _section4(rules: list[dict]) -> str:
    """Generate §4 — CAND-004 Limitation (Explicit), sourced from the TOML.

    The limitation text is derived exclusively from the authoritative
    ``limitation`` field of the CAND-004 record in the TOML artifact. There is
    no independently authored copy of the limitation prose in this generator —
    §3 and §4 both render the single TOML source via ``_render_limitation``.
    """
    cand004 = next((r for r in rules if r["rule_id"] == "CAND-004"), None)
    if cand004 is None or not cand004.get("limitation"):
        raise ValueError(
            "CAND-004 limitation missing from ruleset; §4 cannot render a single-source limitation"
        )
    return (
        "## 4. CAND-004 Limitation (Explicit)\n\n"
        "The limitation on CAND-004 is authoritative and is restated here for emphasis:\n\n"
        + _render_limitation(cand004)
    )


def _section5(non_executable: list[dict]) -> str:
    """Generate §5 — Non-Executable Rules (from TOML)."""
    parts = [
        "## 5. Non-Executable Rules",
        "",
        "The following candidate rules were evaluated and are **NOT_EXECUTABLE**. They are",
        "preserved here as record. They are not part of the ratified executable set.",
        "",
    ]
    for record in non_executable:
        parts.append(f"### {record['rule_id']}")
        parts.append("")
        parts.append(_render_non_executable(record))
        parts.append("")
    return "\n".join(parts).rstrip()


def _section8(rules: list[dict]) -> str:
    """Generate §8 — Coverage Boundary (from TOML)."""
    return (
        "## 8. Coverage Boundary\n\n"
        "This ruleset does **NOT** claim universal event coverage.\n\n"
        "Current ratified executable coverage consists of:\n\n"
        f"{_render_coverage_boundary(rules)}\n\n"
        "All other events remain:\n\n"
        "```\nUNCLASSIFIED\n```\n\n"
        "unless separately approved by a future rule."
    )


def generate_markdown(toml_path: Path = DEFAULT_TOML) -> str:
    """Generate the Markdown representation of the ruleset.

    Returns the full Markdown string with sections in numeric order.
    Rule-bearing sections (§3, §4, §5, §8) are derived from the TOML artifact;
    the remaining governance prose is static template text.
    """
    data = tomllib.loads(toml_path.read_text(encoding="utf-8"))
    meta = data["ruleset"]
    version = meta["version"]
    status = meta["status"]
    rules = data["rules"]
    non_executable = data.get("non_executable", [])

    # Deterministic ordering by rule_id.
    rules = sorted(rules, key=lambda r: r["rule_id"])
    non_executable = sorted(non_executable, key=lambda r: r["rule_id"])

    dynamic = {
        "3": _section3(rules),
        "4": _section4(rules),
        "5": _section5(non_executable),
        "8": _section8(rules),
    }

    out: list[str] = []
    out.append("# TACTICAL CORE — Ratified Baseline Severity Ruleset v1.0.0\n")
    out.append("## Document Identity\n")
    out.append("| Field | Value |")
    out.append("| --- | --- |")
    out.append("| PROJECT | TACTICAL CORE |")
    out.append(f"| RULESET_VERSION | {version} |")
    out.append(f"| STATUS | {status} |")
    out.append("| GOVERNING_ADR | ADR-012 (Accepted) |")
    out.append("")
    out.append("This document is a governance artifact. It is **NOT** implementation code.")
    out.append("It defines the ratified baseline operational severity classification rules and the")
    out.append("governance contract that governs them.")
    out.append("")

    # Assemble in numeric order: 1..16, pulling dynamic sections in position.
    for n in range(1, 17):
        key = str(n)
        out.append("---")
        out.append("")
        if key in dynamic:
            out.append(dynamic[key])
        else:
            out.append(_STATIC_SECTIONS[key])
        out.append("")

    return "\n".join(out).rstrip() + "\n"


def _write_default() -> None:
    DEFAULT_MD.write_text(generate_markdown(), encoding="utf-8")
    print(f"Generated: {DEFAULT_MD}")


def _check() -> int:
    generated = generate_markdown()
    if not DEFAULT_MD.exists():
        print(f"DRIFT: committed Markdown missing: {DEFAULT_MD}")
        return 1
    committed = DEFAULT_MD.read_text(encoding="utf-8")
    if generated == committed:
        print("DRIFT CHECK: PASS (regenerated Markdown matches committed artifact)")
        return 0
    print("DRIFT CHECK: FAIL (regenerated Markdown diverges from committed artifact)")
    import difflib

    diff = list(difflib.unified_diff(
        committed.splitlines(), generated.splitlines(),
        fromfile=str(DEFAULT_MD), tofile="<regenerated>", lineterm="",
    ))
    for line in diff[:80]:
        print(line)
    if len(diff) > 80:
        print(f"... ({len(diff) - 80} more diff lines)")
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate/validate the severity ruleset Markdown from the TOML artifact."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Drift-check only: regenerate to memory and byte-compare with the committed Markdown (no write).",
    )
    args = parser.parse_args(argv)
    if args.check:
        return _check()
    _write_default()
    return 0


if __name__ == "__main__":
    sys.exit(main())
