"""WO-037-07 — CI drift validation for the severity ruleset.

Verifies that the committed Markdown representation
(``docs/governance/SEVERITY_RULES_v1.0.0.md``) is byte-identical to the output
of the deterministic generator applied to the authoritative TOML ruleset
(``docs/governance/SEVERITY_RULES_v1.0.0.toml``).

This is the regenerate-and-compare CI drift-detection model. It fails the
build when:

  * the Markdown is stale (the ruleset changed but the Markdown was not
    regenerated);
  * the Markdown was manually edited;
  * the ruleset/version diverges from the generated output.

Exit code 0 = PASS (no drift); exit code 1 = FAIL (drift detected).

Usage (CI or local):
    python scripts/validate_severity_drift.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import generate_severity_markdown as generator  # noqa: E402


def main() -> int:
    return generator._check()


if __name__ == "__main__":
    sys.exit(main())
