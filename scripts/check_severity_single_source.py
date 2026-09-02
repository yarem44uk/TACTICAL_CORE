"""WO-037-08 — Static single-source rule-boundary detector.

Deterministic AST analysis of the runtime severity module
(``backend/app/operator/severity.py``) to detect any FORBIDDEN independent
hardcoded semantic rule content that would bypass the authoritative
machine-readable ruleset (ADR-013).

The detector distinguishes legitimate taxonomy/loader machinery from forbidden
semantic hardcoding:

  * ALLOWED — the ``Severity`` enum, taxonomy constants
    (``_VALID_SEVERITIES``, ``_VALID_RULE_STATUSES``), schema field-name sets,
    version regexes, the loader implementation, precedence resolution, and
    classification functions. These are structural, not rule content.

  * FORBIDDEN — an independent, executable semantic rule table encoded as
    literals (``rule_id`` / ``event_type`` / ``source`` / ``severity``),
    hardcoded ``BaselineRule(...)`` constructions carrying literal semantic
    values, fallback semantic mappings, or an authoritative-source bypass
    (a module that does not consume the authoritative artifact).

The detector NEVER edits the module. It only reads and parses.

Usage:
    python scripts/check_severity_single_source.py [--source PATH]

Exit code 0 = PASS (no forbidden semantic hardcoding); exit code 1 = FAIL.
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path
from typing import List, Optional

_DEFAULT_SOURCE = (
    Path(__file__).resolve().parents[1]
    / "backend" / "app" / "operator" / "severity.py"
)

_SEVERITY_VALUES = {"INFO", "WARNING", "THREAT", "CRITICAL", "UNCLASSIFIED"}


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------


def _is_constant_str(node: Optional[ast.AST]) -> bool:
    return isinstance(node, ast.Constant) and isinstance(node.value, str)


def _is_severity_attr(node: Optional[ast.AST]) -> bool:
    """True for ``Severity.INFO`` style attribute access."""
    return (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "Severity"
        and node.attr in _SEVERITY_VALUES
    )


def _dict_is_rule_table(node: ast.AST) -> bool:
    """True if ``node`` is a dict literal encoding an independent rule.

    A rule table entry carries a literal ``rule_id`` plus ``event_type`` and/or
    ``source`` plus a literal ``severity``.
    """
    if not isinstance(node, ast.Dict):
        return False
    keys = {}
    for k, v in zip(node.keys, node.values):
        if k is not None and isinstance(k, ast.Constant) and isinstance(k.value, str):
            keys[k.value] = v
    if "rule_id" not in keys:
        return False
    if not _is_constant_str(keys["rule_id"]):
        return False
    has_event_or_source = "event_type" in keys or "source" in keys
    if not has_event_or_source:
        return False
    if "severity" not in keys:
        return False
    sev = keys["severity"]
    return _is_constant_str(sev) or _is_severity_attr(sev)


def _call_is_literal_baselinerule(node: ast.AST) -> bool:
    """True if ``node`` is a ``BaselineRule(...)`` call with literal semantics."""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    func_name = None
    if isinstance(func, ast.Name):
        func_name = func.id
    elif isinstance(func, ast.Attribute):
        func_name = func.attr
    if func_name != "BaselineRule":
        return False
    # Collect arguments by field name: positional (dataclass order
    # rule_id, event_type, source, severity) and keyword.
    fields = ["rule_id", "event_type", "source", "severity"]
    args: dict[str, ast.AST] = {}
    for i, arg in enumerate(node.args):
        if i < len(fields):
            args[fields[i]] = arg
    for kw in node.keywords:
        if kw.arg is not None:
            args[kw.arg] = kw.value
    # A hardcoded rule must carry a literal rule_id (and a literal or enum
    # severity). The legitimate loader constructs BaselineRule from parsed
    # TOML variables, never from literal semantic values.
    if "rule_id" not in args or not _is_constant_str(args["rule_id"]):
        return False
    has_event_or_source = "event_type" in args or "source" in args
    if not has_event_or_source:
        return False
    if "severity" not in args:
        return False
    sev = args["severity"]
    return _is_constant_str(sev) or _is_severity_attr(sev)


def _value_encodes_rule_table(node: ast.AST) -> bool:
    """True if ``node`` (an assigned value) encodes an independent rule table."""
    # A list/tuple whose element(s) are rule-table dicts or literal BaselineRule.
    if isinstance(node, (ast.List, ast.Tuple)):
        for elt in node.elts:
            if _dict_is_rule_table(elt):
                return True
            if _call_is_literal_baselinerule(elt):
                return True
    # A single dict that is itself a rule table.
    if _dict_is_rule_table(node):
        return True
    # A single literal BaselineRule call.
    if _call_is_literal_baselinerule(node):
        return True
    return False


def _value_is_fallback_mapping(node: ast.AST) -> bool:
    """True if ``node`` is a dict mapping keys to literal severity values.

    This catches a fallback semantic mapping (e.g. ``{"system.error":
    "CRITICAL"}``) that would bypass the authoritative ruleset.
    """
    if not isinstance(node, ast.Dict):
        return False
    for k, v in zip(node.keys, node.values):
        if not _is_constant_str(k) or not _is_constant_str(v):
            continue
        if v.value in _SEVERITY_VALUES:
            return True
    return False


def _module_calls_load_ruleset(tree: ast.Module) -> bool:
    """True if the module invokes ``load_ruleset()`` (authoritative consumption)."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "load_ruleset":
                return True
            if isinstance(func, ast.Attribute) and func.attr == "load_ruleset":
                return True
    return False


def _module_references_ruleset_path(tree: ast.Module) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == "RULESET_PATH":
            return True
    return False


# ---------------------------------------------------------------------------
# Detector entry point
# ---------------------------------------------------------------------------


def analyze(source: str) -> List[str]:
    """Return a list of detected single-source violations.

    An empty list means the source is PASS (no forbidden semantic hardcoding).
    """
    violations: List[str] = []

    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return [f"source is not parseable: {exc}"]

    # Authoritative-source enforcement: the module must consume the
    # authoritative artifact (or at least reference the authoritative path).
    if not _module_calls_load_ruleset(tree) and not _module_references_ruleset_path(
        tree
    ):
        violations.append(
            "authoritative-source bypass: module does not invoke load_ruleset() "
            "nor reference RULESET_PATH"
        )

    # Walk assignments and detect independent semantic rule tables / fallbacks.
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if _value_encodes_rule_table(node.value):
                    name = _target_name(target)
                    violations.append(
                        "independent semantic rule table: module-level assignment "
                        f"{name!r} hardcodes rule_id/event_type/source/severity "
                        "instead of loading from the authoritative ruleset"
                    )
                if _value_is_fallback_mapping(node.value):
                    name = _target_name(target)
                    violations.append(
                        "semantic fallback mapping: module-level assignment "
                        f"{name!r} maps keys to literal severity values"
                    )

    # Deduplicate while preserving order.
    seen: set[str] = set()
    unique: List[str] = []
    for v in violations:
        if v not in seen:
            seen.add(v)
            unique.append(v)
    return unique


def _target_name(target: ast.AST) -> str:
    if isinstance(target, ast.Name):
        return target.id
    if isinstance(target, ast.Attribute):
        return target.attr
    return "<target>"


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Detect forbidden hardcoded severity rule content (read-only)."
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=_DEFAULT_SOURCE,
        help="Python source module to analyze.",
    )
    args = parser.parse_args(argv)

    if not args.source.exists():
        print(f"SINGLE SOURCE: FAIL — source module not found: {args.source}")
        return 1

    source = args.source.read_text(encoding="utf-8")
    violations = analyze(source)
    if violations:
        print("SINGLE SOURCE: FAIL — forbidden semantic hardcoding detected:")
        for v in violations:
            print(f"  - {v}")
        return 1

    print("SINGLE SOURCE: PASS — runtime bound to authoritative ruleset, "
          "no independent hardcoded rule table")
    return 0


if __name__ == "__main__":
    sys.exit(main())
