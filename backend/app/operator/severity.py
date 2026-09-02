"""WO-037-06 — Baseline operational severity classifier.

Implements the ratified SEVERITY-RULES-v1.0.0 ruleset (governed by ADR-012,
Accepted) as a deterministic, read-only, consumer-side, computed-on-demand
classifier.

Architecture contract (ADR-012 / WO-037-06):
  * deterministic — same event facts + same ruleset version => same severity;
  * read-only — never mutates the event, the schema, the database or the
    pipeline;
  * derived — the severity is computed on demand, never durably persisted;
  * replayable / offline — depends on no operator state, wall-clock time,
    network, external API, cloud service, or AI nondeterminism;
  * Git-versioned — the ruleset version is a Git-controlled constant;
  * consumer-side — the operator process (a CONSUMER of the durable engine)
    derives the classification, never the durable engine itself.

Scope:
  * Only the four ratified executable rules are implemented (CAND-002,
    CAND-004, CAND-005, CAND-006).
  * CAND-001 and CAND-003 are NOT_EXECUTABLE and are intentionally NOT
    implemented (they require facts the event model does not carry).
  * Unmapped events classify as UNCLASSIFIED. UNCLASSIFIED != INFO; there is
    no silent UNCLASSIFIED -> INFO conversion.
  * CAND-004 limitation: the classifier never inspects payload content. A
    verified observation being INFO does not mean its content is harmless.

Precedence (SEVERITY-RULES-v1.0.0 §7): EVENT-SPECIFIC > SOURCE-SPECIFIC >
GENERIC. Two rules of equal specificity matching the same event raise
:class:`SeverityConflictError` — NO SILENT RESOLUTION.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Sequence, Tuple

from app.event.event import Event

# Ruleset identity (SEVERITY-RULES-v1.0.0 §3/§9).
RULESET_VERSION = "SEVERITY-RULES-v1.0.0"
RULESET_STATUS = "RATIFIED_FOR_CONSUMPTION"


class Severity(str, Enum):
    """Operational baseline severity taxonomy (ADR-012.8)."""

    INFO = "INFO"
    WARNING = "WARNING"
    THREAT = "THREAT"
    CRITICAL = "CRITICAL"
    UNCLASSIFIED = "UNCLASSIFIED"

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class BaselineRule:
    """One ratified baseline classification rule.

    ``event_type`` of ``None`` is a wildcard (matches any event type), used to
    express the GENERIC precedence tier in the resolution logic. The four
    ratified rules always carry a concrete event_type.

    ``source`` of ``None`` means the rule applies regardless of source
    (generic / source-agnostic), as in CAND-004/005/006.
    """

    rule_id: str
    event_type: Optional[str]
    source: Optional[str]
    severity: Severity


# The four ratified executable rules (SEVERITY-RULES-v1.0.0 §3).
RATIFIED_RULES: Tuple[BaselineRule, ...] = (
    # CAND-002: event_type == "signal.failed" AND source == "signal" -> WARNING.
    BaselineRule(
        rule_id="CAND-002",
        event_type="signal.failed",
        source="signal",
        severity=Severity.WARNING,
    ),
    # CAND-004: event_type == "observation.verified" -> INFO (any source).
    # Ratified WITH limitation: payload content is NOT classified.
    BaselineRule(
        rule_id="CAND-004",
        event_type="observation.verified",
        source=None,
        severity=Severity.INFO,
    ),
    # CAND-005: event_type == "relation.severed" -> INFO (any source).
    BaselineRule(
        rule_id="CAND-005",
        event_type="relation.severed",
        source=None,
        severity=Severity.INFO,
    ),
    # CAND-006: event_type == "system.startup" -> INFO (any source).
    BaselineRule(
        rule_id="CAND-006",
        event_type="system.startup",
        source=None,
        severity=Severity.INFO,
    ),
)

# Non-executable candidate rules (SEVERITY-RULES-v1.0.0 §5). Preserved as
# record only; deliberately NOT implemented.
NON_EXECUTABLE_RULE_IDS: Tuple[str, ...] = ("CAND-001", "CAND-003")

# Event types that are intentionally NOT mapped and MUST classify as
# UNCLASSIFIED (SEVERITY-RULES-v1.0.0 §8 / the ruleset expansion prohibition).
_UNMAPPED_EVENT_TYPES: Tuple[str, ...] = (
    "system.error",
    "observation.retracted",
    "signal.received",
    "signal.processed",
    "entity.created",
    "entity.updated",
    "entity.removed",
    "observation.created",
    "system.shutdown",
    "custom",
)


class SeverityConflictError(RuntimeError):
    """Raised when two rules of equal specificity match the same event.

    Per SEVERITY-RULES-v1.0.0 §7 there is NO SILENT RESOLUTION: the baseline
    classifier must not silently choose the higher severity or the first match.
    """


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
    tested with a synthetic ruleset without polluting :data:`RATIFIED_RULES`).
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
    return _resolve(RATIFIED_RULES, event_type, source)


def classify(event: Event) -> Severity:
    """Classify a canonical :class:`Event`.

    The classifier consumes only the event's deterministic facts
    (``event_type`` and ``source``). It NEVER inspects ``payload`` content,
    per the CAND-004 limitation, and never mutates the event.
    """
    return classify_facts(str(event.event_type), event.source)
