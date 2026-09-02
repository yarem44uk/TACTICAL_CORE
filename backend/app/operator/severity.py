"""WO-037-07 — Baseline operational severity classifier (ruleset-driven).

Implements the ratified SEVERITY-RULES-v1.0.0 ruleset (governed by ADR-012,
Accepted; single-source architecture per ADR-013) as a deterministic,
read-only, consumer-side, computed-on-demand classifier.

The authoritative rule content lives in the Git-controlled machine-readable
ruleset (``docs/governance/SEVERITY_RULES_v1.0.0.toml``). This module loads
and validates that artifact exactly once per process at import time (classifier
initialization) and exposes it as an immutable tuple. There is NO independent
copy of the ratified rules in Python.

Architecture contract (ADR-012 / ADR-013 / WO-037-07):
  * deterministic — same event facts + same ruleset version => same severity;
  * read-only — never mutates the event, the schema, the database or the
    pipeline;
  * derived — the severity is computed on demand, never durably persisted;
  * replayable / offline — depends on no operator state, wall-clock time,
    network, external API, cloud service, or AI nondeterminism;
  * single-source — the machine-readable TOML ruleset is the sole executable
    rule-content source; Markdown is a generated, non-authoritative
    representation;
  * fail-closed — if the ruleset is missing, malformed, schema-invalid,
    version-mismatched, or fails content-integrity, classifier initialization
    fails and no severity is available. No hardcoded-Python fallback, no silent
    partial loading, no permissive recovery;
  * consumer-side — the operator process (a CONSUMER of the durable engine)
    derives the classification, never the durable engine itself.

Scope:
  * Only the four ratified executable rules are loaded (CAND-002, CAND-004,
    CAND-005, CAND-006).
  * CAND-001 and CAND-003 are NOT_EXECUTABLE and appear only as non-executable
    records in the ruleset; they are never materialized as executable rules.
  * Unmapped events classify as UNCLASSIFIED. UNCLASSIFIED != INFO; there is
    no silent UNCLASSIFIED -> INFO conversion.
  * CAND-004 limitation: the classifier never inspects payload content. A
    verified observation being INFO does not mean its content is harmless.

Precedence (SEVERITY-RULES-v1.0.0 §7): EVENT-SPECIFIC > SOURCE-SPECIFIC >
GENERIC. Two rules of equal specificity matching the same event raise
:class:`SeverityConflictError` — NO SILENT RESOLUTION. Classification
semantics remain the sole responsibility of the Baseline Classifier; the
loader performs structural validation only and never resolves precedence.
"""

from __future__ import annotations

import hashlib
import hmac
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional, Sequence, Tuple

import tomllib

from app.event.event import Event

# Ruleset identity is bound to the loaded artifact (ADR-013). The values below
# are populated from the validated ruleset at import time; they are NOT
# independently hardcoded as semantic authority.
RULESET_VERSION: str
RULESET_STATUS: str

# Loaded immutable rule representation (sole executable rule-content source).
RULES: Tuple["BaselineRule", ...]

# Non-executable candidate rule ids, loaded from the ruleset [[non_executable]]
# records (record-only; never materialized as executable rules).
NON_EXECUTABLE_RULE_IDS: Tuple[str, ...]


class Severity(str, Enum):
    """Operational baseline severity taxonomy (ADR-012.8)."""

    INFO = "INFO"
    WARNING = "WARNING"
    THREAT = "THREAT"
    CRITICAL = "CRITICAL"
    UNCLASSIFIED = "UNCLASSIFIED"

    def __str__(self) -> str:
        return self.value


class SeverityConflictError(RuntimeError):
    """Raised when two rules of equal specificity match the same event.

    Per SEVERITY-RULES-v1.0.0 §7 there is NO SILENT RESOLUTION: the baseline
    classifier must not silently choose the higher severity or the first match.
    """


class RulesetLoadError(RuntimeError):
    """Raised when the authoritative ruleset cannot be loaded or validated.

    Any instance of this error means classifier initialization has failed and
    NO severity classification is available (fail-closed). It is an internal
    initialization error, never a normal operator-request error.
    """


@dataclass(frozen=True)
class BaselineRule:
    """One ratified baseline classification rule.

    ``event_type`` of ``None`` is a wildcard (matches any event type), used to
    express the GENERIC precedence tier in the resolution logic. The four
    ratified rules always carry a concrete event_type.

    ``source`` of ``None`` means the rule applies regardless of source
    (generic / source-agnostic). In the machine-readable ruleset this is
    expressed as ``source = "*"``; the loader maps ``"*"`` to ``None``.
    """

    rule_id: str
    event_type: Optional[str]
    source: Optional[str]
    severity: Severity


# ---------------------------------------------------------------------------
# Authoritative artifact paths (package-relative, CWD-independent).
# ---------------------------------------------------------------------------
_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_GOVERNANCE_DIR = _REPOSITORY_ROOT / "docs" / "governance"
RULESET_PATH = _GOVERNANCE_DIR / "SEVERITY_RULES_v1.0.0.toml"
SIDECAR_PATH = _GOVERNANCE_DIR / "SEVERITY_RULES_v1.0.0.toml.sha256"

# ---------------------------------------------------------------------------
# Ruleset schema / validation constants.
# ---------------------------------------------------------------------------
_VALID_SEVERITIES = frozenset({"INFO", "WARNING", "THREAT", "CRITICAL"})
_VALID_RULE_STATUSES = frozenset({"RATIFIED", "RATIFIED_WITH_LIMITATION"})
_VERSION_RE = re.compile(
    r"^SEVERITY-RULES-v(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)$"
)
_FILENAME_VERSION_RE = re.compile(
    r"^SEVERITY_RULES_v(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)$"
)

_ALLOWED_RULE_FIELDS = frozenset(
    {"rule_id", "event_type", "source", "severity", "status", "limitation"}
)
_REQUIRED_RULE_FIELDS = frozenset(
    {"rule_id", "event_type", "source", "severity", "status"}
)
_ALLOWED_NON_EXEC_FIELDS = frozenset({"rule_id", "status", "reason"})
_REQUIRED_NON_EXEC_FIELDS = frozenset({"rule_id", "status", "reason"})


def _resolve_ruleset_path(path: Optional[Path]) -> Path:
    """Return the ruleset path, defaulting to the authoritative artifact."""
    return Path(path) if path is not None else RULESET_PATH


def _validate_version_binding(
    version: str, ruleset_path: Path
) -> None:
    """Validate the ruleset version format and its filename consistency.

    The version declared in ``[ruleset].version`` MUST match the version
    embedded in the artifact filename (``SEVERITY_RULES_v<v>``). Any mismatch
    is a fail-closed invalid-ruleset-version failure.
    """
    m = _VERSION_RE.match(version)
    if not m:
        raise RulesetLoadError(
            f"invalid ruleset version format: {version!r} "
            f"(expected SEVERITY-RULES-v<MAJOR>.<MINOR>.<PATCH>)"
        )
    fm = _FILENAME_VERSION_RE.match(ruleset_path.stem)
    if not fm:
        raise RulesetLoadError(
            f"ruleset filename does not match expected pattern: "
            f"{ruleset_path.name!r} (expected SEVERITY_RULES_v<MAJOR>.<MINOR>.<PATCH>.toml)"
        )
    declared = (m.group("major"), m.group("minor"), m.group("patch"))
    embedded = (fm.group("major"), fm.group("minor"), fm.group("patch"))
    if declared != embedded:
        raise RulesetLoadError(
            f"ruleset version {version!r} does not match the version embedded "
            f"in the artifact filename {ruleset_path.name!r}"
        )


def _verify_integrity(ruleset_path: Path, raw: bytes) -> None:
    """Verify SHA-256 content integrity against the sidecar.

    The expected digest is the SHA-256 of the raw artifact bytes, stored in the
    ``.toml.sha256`` sidecar. A missing/mismatched digest is a fail-closed
    integrity failure.
    """
    sidecar = ruleset_path.with_name(ruleset_path.name + ".sha256")
    if not sidecar.exists():
        raise RulesetLoadError(f"content-integrity sidecar not found: {sidecar}")
    expected = sidecar.read_text(encoding="utf-8").strip()
    actual = hashlib.sha256(raw).hexdigest()
    if not hmac.compare_digest(expected, actual):
        raise RulesetLoadError(
            f"SHA-256 content-integrity mismatch for {ruleset_path.name} "
            f"(expected {expected!r}, got {actual!r})"
        )


def _materialize_rule(record: dict) -> BaselineRule:
    """Validate one executable rule record and materialize it.

    This performs STRUCTURAL validation only (required/known fields, field
    types, allowed severities/statuses, prohibited wildcards). It does NOT
    resolve classification precedence or assign meaning — that is the
    Baseline Classifier's sole responsibility.
    """
    if not isinstance(record, dict):
        raise RulesetLoadError("each [[rules]] entry must be a table")
    missing = _REQUIRED_RULE_FIELDS - set(record.keys())
    if missing:
        raise RulesetLoadError(
            f"rule missing required field(s): {sorted(missing)}"
        )
    unknown = set(record.keys()) - _ALLOWED_RULE_FIELDS
    if unknown:
        raise RulesetLoadError(
            f"rule has unknown field(s): {sorted(unknown)}"
        )

    rule_id = record["rule_id"]
    if not isinstance(rule_id, str) or not rule_id:
        raise RulesetLoadError("rule_id must be a non-empty string")

    event_type = record["event_type"]
    if not isinstance(event_type, str) or not event_type:
        raise RulesetLoadError(
            f"rule {rule_id}: event_type must be a non-empty string"
        )
    if event_type == "*":
        raise RulesetLoadError(
            f"rule {rule_id}: event_type='*' is NOT permitted for the "
            f"currently ratified executable rules"
        )

    source = record["source"]
    if not isinstance(source, str):
        raise RulesetLoadError(
            f"rule {rule_id}: source must be a string"
        )

    severity = record["severity"]
    if severity not in _VALID_SEVERITIES:
        raise RulesetLoadError(
            f"rule {rule_id}: invalid severity {severity!r} "
            f"(must be one of {sorted(_VALID_SEVERITIES)})"
        )

    status = record["status"]
    if status not in _VALID_RULE_STATUSES:
        raise RulesetLoadError(
            f"rule {rule_id}: invalid status {status!r} "
            f"(must be one of {sorted(_VALID_RULE_STATUSES)})"
        )

    # ``source = "*"`` is the machine-readable wildcard (source-agnostic);
    # it maps to runtime ``BaselineRule.source = None``.
    return BaselineRule(
        rule_id=rule_id,
        event_type=event_type,
        source=None if source == "*" else source,
        severity=Severity(severity),
    )


def _validate_non_executable(record: dict) -> str:
    """Validate one ``[[non_executable]]`` record and return its rule_id."""
    if not isinstance(record, dict):
        raise RulesetLoadError("each [[non_executable]] entry must be a table")
    missing = _REQUIRED_NON_EXEC_FIELDS - set(record.keys())
    if missing:
        raise RulesetLoadError(
            f"non_executable record missing required field(s): {sorted(missing)}"
        )
    unknown = set(record.keys()) - _ALLOWED_NON_EXEC_FIELDS
    if unknown:
        raise RulesetLoadError(
            f"non_executable record has unknown field(s): {sorted(unknown)}"
        )
    rule_id = record["rule_id"]
    if not isinstance(rule_id, str) or not rule_id:
        raise RulesetLoadError("non_executable rule_id must be a non-empty string")
    if record["status"] != "NOT_EXECUTABLE":
        raise RulesetLoadError(
            f"non_executable record {rule_id} must have status NOT_EXECUTABLE"
        )
    if not isinstance(record["reason"], str) or not record["reason"]:
        raise RulesetLoadError(
            f"non_executable record {rule_id} requires a non-empty reason"
        )
    return rule_id


def load_ruleset(
    path: Optional[Path] = None,
) -> Tuple[Tuple[BaselineRule, ...], str, str, Tuple[str, ...]]:
    """Load, validate, integrity-check, and materialize the ruleset.

    This is the single entry point for obtaining executable rule content. It is
    called exactly once per process at classifier initialization. It reads the
    authoritative TOML, verifies its SHA-256 content integrity, validates its
    structure, validates the version/filename binding, and materializes an
    immutable tuple of :class:`BaselineRule` objects.

    Returns ``(rules, version, status, non_executable_rule_ids)``.

    Raises :class:`RulesetLoadError` on any failure — missing artifact,
    malformed TOML, schema-invalid record, invalid version, filename/version
    mismatch, duplicate rule_id, structurally invalid/conflicting record,
    unknown field, unsupported semantics, missing sidecar, or SHA-256 mismatch.
    There is NO hardcoded-Python fallback and NO permissive recovery.
    """
    ruleset_path = _resolve_ruleset_path(path)
    if not ruleset_path.exists():
        raise RulesetLoadError(f"ruleset artifact not found: {ruleset_path}")

    raw = ruleset_path.read_bytes()
    _verify_integrity(ruleset_path, raw)

    try:
        parsed = tomllib.loads(raw.decode("utf-8"))
    except Exception as exc:  # tomllib.TOMLDecodeError and subclasses
        raise RulesetLoadError(f"malformed TOML in {ruleset_path.name}: {exc}") from exc

    ruleset_meta = parsed.get("ruleset")
    if not isinstance(ruleset_meta, dict):
        raise RulesetLoadError("missing [ruleset] table")

    version = ruleset_meta.get("version")
    status = ruleset_meta.get("status")
    governing_adr = ruleset_meta.get("governing_adr")
    if not isinstance(version, str) or not isinstance(status, str):
        raise RulesetLoadError("[ruleset] requires string 'version' and 'status'")
    _validate_version_binding(version, ruleset_path)
    if governing_adr != "ADR-012":
        raise RulesetLoadError(
            f"unexpected governing_adr: {governing_adr!r} (expected 'ADR-012')"
        )

    rules_raw = parsed.get("rules")
    if not isinstance(rules_raw, list) or not rules_raw:
        raise RulesetLoadError("ruleset requires a non-empty [[rules]] array")

    seen_ids: set[str] = set()
    rules: list[BaselineRule] = []
    for record in rules_raw:
        rule = _materialize_rule(record)
        if rule.rule_id in seen_ids:
            raise RulesetLoadError(f"duplicate rule_id: {rule.rule_id}")
        seen_ids.add(rule.rule_id)
        rules.append(rule)

    ne_raw = parsed.get("non_executable", [])
    if not isinstance(ne_raw, list):
        raise RulesetLoadError("non_executable must be an array")
    non_executable_ids: list[str] = []
    for record in ne_raw:
        ne_id = _validate_non_executable(record)
        if ne_id in seen_ids:
            raise RulesetLoadError(
                f"rule_id {ne_id} appears in both executable and non_executable"
            )
        non_executable_ids.append(ne_id)

    return tuple(rules), version, status, tuple(non_executable_ids)


# ---------------------------------------------------------------------------
# Classifier initialization — exactly once per process, before any
# classification request can be serviced. A load/integrity/validation failure
# here raises, so any process importing this module (e.g. the operator app)
# fails closed at startup instead of silently using an alternate rule source.
# ---------------------------------------------------------------------------
_RULES, RULESET_VERSION, RULESET_STATUS, NON_EXECUTABLE_RULE_IDS = load_ruleset()
RULES = _RULES


def _specificity(rule: BaselineRule) -> Tuple[bool, bool]:
    """Return an ordered specificity key for a rule.

    The tuple ``(constrains_event_type, constrains_source)`` orders rules
    lexicographically as:

        EVENT+SOURCE > EVENT-ONLY > SOURCE-ONLY > GENERIC

    which encodes EVENT-SPECIFIC > SOURCE-SPECIFIC > GENERIC, with an
    event+source rule ranked most specific of all (it constrains both).
    """
    return (rule.event_type is not None, rule.source is not None)


def _matches(rule: BaselineRule, event_type: str, source: str) -> bool:
    """Return True when a rule applies to the given event facts.

    A ``None`` event_type or source on a rule is a wildcard (matches any value),
    which is how the GENERIC / SOURCE-SPECIFIC precedence tiers are expressed.
    The four ratified rules always carry a concrete event_type, so their
    behaviour is fully determined by the ratified conditions.
    """
    if rule.event_type is not None and rule.event_type != event_type:
        return False
    if rule.source is not None and rule.source != source:
        return False
    return True


def _resolve(
    rules: Sequence[BaselineRule], event_type: str, source: str
) -> Severity:
    """Resolve the baseline severity for the given facts over a ruleset.

    Applies the ratified precedence (EVENT-SPECIFIC > SOURCE-SPECIFIC >
    GENERIC) and raises :class:`SeverityConflictError` when two rules of equal
    specificity match the same event (NO SILENT RESOLUTION).

    ``rules`` is the only mutable input (kept explicit so the invariant can be
    tested with a synthetic ruleset without polluting :data:`RULES`).
    """
    matching = [r for r in rules if _matches(r, event_type, source)]
    if not matching:
        return Severity.UNCLASSIFIED

    best = max(matching, key=_specificity)
    tied = [r for r in matching if _specificity(r) == _specificity(best)]
    if len(tied) > 1:
        ids = ", ".join(sorted(r.rule_id for r in tied))
        raise SeverityConflictError(
            f"equal-specificity severity conflict for "
            f"event_type={event_type!r}, source={source!r}: {ids}"
        )
    return best.severity


def classify_facts(event_type: str, source: str) -> Severity:
    """Classify an event from its deterministic facts.

    Args:
        event_type: the canonical event type string (e.g. ``"signal.failed"``).
        source: the canonical source identifier (e.g. ``"signal"``).

    Returns:
        The derived baseline :class:`Severity`, or ``UNCLASSIFIED`` when no
        ratified rule matches.

    Raises:
        SeverityConflictError: two rules of equal specificity match the same
            event (NO SILENT RESOLUTION).
    """
    return _resolve(RULES, event_type, source)


def classify(event: Event) -> Severity:
    """Classify a canonical :class:`Event`.

    The classifier consumes only the event's deterministic facts
    (``event_type`` and ``source``). It NEVER inspects ``payload`` content,
    per the CAND-004 limitation, and never mutates the event.
    """
    return classify_facts(str(event.event_type), event.source)
