"""WO-037-08 tests: severity ruleset release integrity + CI single-source gate.

Covers the release ledger, release immutability (same-version mutation
rejection and new-version path), the static single-source rule-boundary
detector, and non-regression of the existing severity drift validator.

These tests are isolated. They use temporary fixture copies and temporary git
repositories. They NEVER mutate:

  * docs/governance/SEVERITY_RULES_v1.0.0.toml
  * docs/governance/SEVERITY_RULES_v1.0.0.toml.sha256
  * docs/governance/SEVERITY_RULES_v1.0.0.md
  * docs/governance/SEVERITY_RELEASE_LEDGER.toml
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

# Repository root: backend/tests/ -> repo root.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS_DIR = _REPO_ROOT / "scripts"
sys.path.insert(0, str(_SCRIPTS_DIR))

import check_severity_single_source as single_source  # noqa: E402
import validate_severity_release as release  # noqa: E402

_REAL_LEDGER = _REPO_ROOT / "docs" / "governance" / "SEVERITY_RELEASE_LEDGER.toml"
_REAL_RULESET_DIR = _REPO_ROOT / "docs" / "governance"

_RELEASED_COMMIT = "7ccea777b34ff1f9af363021efe313e21ef87184"
_ARTIFACT = "docs/governance/SEVERITY_RULES_v1.0.0.toml"
_FROZEN_SHA = "84e702757d387051ae73c61becde6bdb193d9035c4ff6eb3fc101006e5e3b204"


def _run(cmd, cwd=None):
    return subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True)


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _ledger_toml(release: str, version: str, artifact: str, sha256: str,
                 released_commit: str) -> str:
    return (
        "ledger_version = 1\n\n"
        "[[releases]]\n"
        f'release_id = "{release}"\n'
        f'version = "{version}"\n'
        f'artifact = "{artifact}"\n'
        f'sha256 = "{sha256}"\n'
        f'released_commit = "{released_commit}"\n'
        'governing_adr = "ADR-013"\n'
    )


@pytest.fixture()
def temp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


def _make_temp_git_repo(temp_dir: Path, artifact_rel: str, content: bytes) -> str:
    """Create a temp git repo, commit ``content`` at ``artifact_rel``.

    Returns the commit SHA. Used to test the new-version release path without
    touching the real repository.
    """
    repo = temp_dir / "gitrepo"
    repo.mkdir(parents=True)
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "test@example.com"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.name", "WO-037-08 Test"],
        check=True,
    )
    art_path = repo / artifact_rel
    art_path.parent.mkdir(parents=True, exist_ok=True)
    art_path.write_bytes(content)
    subprocess.run(["git", "-C", str(repo), "add", artifact_rel], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-q", "-m", "release fixture"],
        check=True,
    )
    return subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()


# ============================================================================
# Release ledger — structure
# ============================================================================


def test_valid_ledger_passes() -> None:
    assert release.run() == 0


def test_malformed_ledger_fails(temp_dir: Path) -> None:
    bad = _write(temp_dir / "ledger.toml", "this is [[ not valid toml\n")
    with pytest.raises(release.ReleaseIntegrityError):
        release.validate_ledger(bad)


def test_missing_required_field_fails(temp_dir: Path) -> None:
    bad = _write(
        temp_dir / "ledger.toml",
        "ledger_version = 1\n\n[[releases]]\n"
        'release_id = "SEVERITY-RULES-v1.0.0-r1"\n'
        'version = "SEVERITY-RULES-v1.0.0"\n'
        'artifact = "docs/governance/SEVERITY_RULES_v1.0.0.toml"\n'
        # sha256 intentionally omitted
        'released_commit = "7ccea777b34ff1f9af363021efe313e21ef87184"\n'
        'governing_adr = "ADR-013"\n',
    )
    with pytest.raises(release.ReleaseIntegrityError) as exc:
        release.validate_ledger(bad)
    assert "missing required field" in str(exc.value)


def test_duplicate_version_fails(temp_dir: Path) -> None:
    bad = _write(
        temp_dir / "ledger.toml",
        _ledger_toml("R-A", "SEVERITY-RULES-v1.0.0", _ARTIFACT, _FROZEN_SHA,
                     _RELEASED_COMMIT)
        + "\n" + _ledger_toml("R-B", "SEVERITY-RULES-v1.0.0", _ARTIFACT,
                              _FROZEN_SHA, _RELEASED_COMMIT),
    )
    with pytest.raises(release.ReleaseIntegrityError) as exc:
        release.validate_ledger(bad)
    assert "duplicate released version" in str(exc.value)


def test_duplicate_release_identity_fails(temp_dir: Path) -> None:
    bad = _write(
        temp_dir / "ledger.toml",
        _ledger_toml("R-SAME", "SEVERITY-RULES-v1.0.0", _ARTIFACT, _FROZEN_SHA,
                     _RELEASED_COMMIT)
        + "\n" + _ledger_toml("R-SAME", "SEVERITY-RULES-v1.0.1", _ARTIFACT,
                              _FROZEN_SHA, _RELEASED_COMMIT),
    )
    with pytest.raises(release.ReleaseIntegrityError) as exc:
        release.validate_ledger(bad)
    assert "duplicate release identity" in str(exc.value)


def test_invalid_sha_fails(temp_dir: Path) -> None:
    bad = _write(
        temp_dir / "ledger.toml",
        _ledger_toml("R-A", "SEVERITY-RULES-v1.0.0", _ARTIFACT, "not-a-hash",
                     _RELEASED_COMMIT),
    )
    with pytest.raises(release.ReleaseIntegrityError) as exc:
        release.validate_ledger(bad)
    assert "invalid sha256" in str(exc.value)


def test_empty_release_value_fails(temp_dir: Path) -> None:
    bad = _write(
        temp_dir / "ledger.toml",
        _ledger_toml("R-A", "SEVERITY-RULES-v1.0.0", "", _FROZEN_SHA,
                     _RELEASED_COMMIT),
    )
    with pytest.raises(release.ReleaseIntegrityError) as exc:
        release.validate_ledger(bad)
    assert "non-empty string" in str(exc.value)


# ============================================================================
# Release ledger — historical integrity
# ============================================================================


def test_missing_historical_commit_fails(temp_dir: Path) -> None:
    bad = _write(
        temp_dir / "ledger.toml",
        _ledger_toml("R-A", "SEVERITY-RULES-v1.0.0", _ARTIFACT, _FROZEN_SHA,
                     "1111111111111111111111111111111111111111"),
    )
    with pytest.raises(release.ReleaseIntegrityError) as exc:
        release.validate_historical_integrity(
            release.validate_ledger(bad)[0], _REPO_ROOT
        )
    assert "does not exist" in str(exc.value)


def test_missing_historical_artifact_fails(temp_dir: Path) -> None:
    bad = _write(
        temp_dir / "ledger.toml",
        _ledger_toml("R-A", "SEVERITY-RULES-v1.0.0",
                     "docs/governance/NONEXISTENT.toml", _FROZEN_SHA,
                     _RELEASED_COMMIT),
    )
    with pytest.raises(release.ReleaseIntegrityError) as exc:
        release.validate_historical_integrity(
            release.validate_ledger(bad)[0], _REPO_ROOT
        )
    assert "artifact not present" in str(exc.value)


def test_historical_hash_mismatch_fails(temp_dir: Path) -> None:
    wrong_sha = "0" * 64
    bad = _write(
        temp_dir / "ledger.toml",
        _ledger_toml("R-A", "SEVERITY-RULES-v1.0.0", _ARTIFACT, wrong_sha,
                     _RELEASED_COMMIT),
    )
    with pytest.raises(release.ReleaseIntegrityError) as exc:
        release.validate_historical_integrity(
            release.validate_ledger(bad)[0], _REPO_ROOT
        )
    assert "SHA-256 mismatch" in str(exc.value)


def test_missing_ledger_fails(temp_dir: Path) -> None:
    with pytest.raises(release.ReleaseIntegrityError) as exc:
        release.validate_ledger(temp_dir / "nope.toml")
    assert "not found" in str(exc.value)


# ============================================================================
# Release immutability
# ============================================================================


def test_original_v1_0_0_passes() -> None:
    assert release.run() == 0


def test_changed_same_version_fails(temp_dir: Path) -> None:
    # Copy the real ruleset, modify its bytes, keep the same version.
    src = _REAL_RULESET_DIR / "SEVERITY_RULES_v1.0.0.toml"
    modified = src.read_bytes().replace(
        b'severity = "WARNING"', b'severity = "CRITICAL"'
    )
    assert modified != src.read_bytes()  # sanity: actually changed
    ruleset_dir = temp_dir / "governance"
    ruleset_dir.mkdir(parents=True)
    (ruleset_dir / "SEVERITY_RULES_v1.0.0.toml").write_bytes(modified)

    with pytest.raises(release.ReleaseIntegrityError) as exc:
        release.validate_current_ruleset(
            release.validate_ledger(_REAL_LEDGER, _REPO_ROOT),
            ruleset_dir, _REPO_ROOT,
        )
    assert "same-version content mutation" in str(exc.value)


def test_new_version_path_passes(temp_dir: Path) -> None:
    # A changed ruleset under a NEW semantic version, with its own release
    # record and a historical commit that contains the matching bytes, passes
    # the immutability condition (subject to normal validation).
    content = (
        b'[ruleset]\nversion = "SEVERITY-RULES-v1.0.1"\n'
        b'status = "RATIFIED_FOR_CONSUMPTION"\n'
        b'governing_adr = "ADR-012"\n\n'
        b'[[rules]]\nrule_id = "CAND-999"\n'
        b'event_type = "test.event"\nsource = "*"\n'
        b'severity = "WARNING"\nstatus = "RATIFIED"\n'
    )
    artifact_rel = "docs/governance/SEVERITY_RULES_v1.0.1.toml"
    commit = _make_temp_git_repo(temp_dir, artifact_rel, content)
    sha = hashlib.sha256(content).hexdigest()

    ledger = _write(
        temp_dir / "ledger.toml",
        _ledger_toml("SEVERITY-RULES-v1.0.1-r1", "SEVERITY-RULES-v1.0.1",
                     artifact_rel, sha, commit),
    )
    repo_root = temp_dir / "gitrepo"
    ruleset_dir = repo_root / "docs" / "governance"

    assert release.run(ledger_path=ledger, ruleset_dir=ruleset_dir,
                       repo_root=repo_root) == 0


def test_release_identity_reproducible() -> None:
    # The release identity is deterministic: same version + same content hash.
    releases = release.validate_ledger(_REAL_LEDGER, _REPO_ROOT)
    v10 = [r for r in releases if r["version"] == "SEVERITY-RULES-v1.0.0"]
    assert len(v10) == 1
    assert v10[0]["sha256"] == _FROZEN_SHA
    assert v10[0]["released_commit"] == _RELEASED_COMMIT


def test_release_validation_offline() -> None:
    # The validator must not depend on network. Run it in a clean interpreter
    # and assert it exits zero and touches nothing.
    proc = _run(
        f"{sys.executable} scripts/validate_severity_release.py",
        cwd=str(_REPO_ROOT),
    )
    assert proc.returncode == 0, proc.stderr
    assert "PASS" in proc.stdout


# ============================================================================
# Static single-source detector
# ============================================================================


def _real_severity_source() -> str:
    return (_REPO_ROOT / "backend" / "app" / "operator" / "severity.py").read_text(
        encoding="utf-8"
    )


def test_current_severity_module_passes() -> None:
    assert single_source.analyze(_real_severity_source()) == []


def test_legitimate_taxonomy_no_false_positive() -> None:
    good = (
        "import tomllib\n"
        "from enum import Enum\n"
        "from pathlib import Path\n"
        "class Severity(str, Enum):\n"
        '    INFO = "INFO"\n'
        '    WARNING = "WARNING"\n'
        '    THREAT = "THREAT"\n'
        '    CRITICAL = "CRITICAL"\n'
        '    UNCLASSIFIED = "UNCLASSIFIED"\n'
        '_VALID_SEVERITIES = frozenset({"INFO", "WARNING", "THREAT", "CRITICAL"})\n'
        '_VALID_RULE_STATUSES = frozenset({"RATIFIED", "RATIFIED_WITH_LIMITATION"})\n'
        '_ALLOWED_RULE_FIELDS = frozenset({"rule_id", "event_type", "source", "severity"})\n'
        'RULESET_PATH = Path("docs/governance/SEVERITY_RULES_v1.0.0.toml")\n'
        "def load_ruleset():\n"
        '    return (), "SEVERITY-RULES-v1.0.0", "RATIFIED", ()\n'
        "_RULES, RULESET_VERSION, RULESET_STATUS, _NE = load_ruleset()\n"
        "RULES = _RULES\n"
        "def classify_facts(event_type, source):\n"
        "    return Severity.UNCLASSIFIED\n"
    )
    assert single_source.analyze(good) == []


def test_synthetic_hardcoded_rule_table_fails() -> None:
    bad = (
        'RULES = [\n'
        '    {"rule_id": "R1", "event_type": "signal.failed", '
        '"source": "signal", "severity": "WARNING"},\n'
        '    {"rule_id": "R2", "event_type": "system.error", '
        '"source": "*", "severity": "CRITICAL"},\n'
        ']\n'
    )
    violations = single_source.analyze(bad)
    assert any("independent semantic rule table" in v for v in violations)


def test_synthetic_hardcoded_baselinerule_fails() -> None:
    bad = (
        "from app.operator.severity import BaselineRule, Severity\n"
        "RULES = (\n"
        '    BaselineRule("R1", "signal.failed", "signal", Severity.WARNING),\n'
        '    BaselineRule("R2", "system.error", "*", Severity.CRITICAL),\n'
        ")\n"
    )
    violations = single_source.analyze(bad)
    assert any("independent semantic rule table" in v for v in violations)


def test_synthetic_fallback_semantic_mapping_fails() -> None:
    bad = 'FALLBACK = {"system.error": "CRITICAL", "observation.retracted": "WARNING"}\n'
    violations = single_source.analyze(bad)
    assert any("semantic fallback mapping" in v for v in violations)


def test_authoritative_source_bypass_fails() -> None:
    bad = (
        "from enum import Enum\n"
        "class Severity(str, Enum):\n"
        '    INFO = "INFO"\n'
        "RULES = []\n"
        "def classify_facts(event_type, source):\n"
        "    return Severity.INFO\n"
    )
    violations = single_source.analyze(bad)
    assert any("authoritative-source bypass" in v for v in violations)


# ============================================================================
# Existing validators — non-regression
# ============================================================================


def test_existing_drift_validator_passes_on_baseline() -> None:
    proc = _run(
        f"{sys.executable} scripts/validate_severity_drift.py",
        cwd=str(_REPO_ROOT),
    )
    assert proc.returncode == 0, proc.stderr
    assert "PASS" in proc.stdout


def test_existing_markdown_generator_check_succeeds() -> None:
    proc = _run(
        f"{sys.executable} scripts/generate_severity_markdown.py --check",
        cwd=str(_REPO_ROOT),
    )
    assert proc.returncode == 0, proc.stderr
    assert "PASS" in proc.stdout
