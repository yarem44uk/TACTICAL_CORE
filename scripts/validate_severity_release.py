"""WO-037-08 — Severity ruleset release-integrity validator.

Validates the authoritative severity release ledger
(``docs/governance/SEVERITY_RELEASE_LEDGER.toml``) and the release-integrity
identity of the currently checked-out authoritative ruleset.

This validator is:

  * deterministic — same inputs always yield the same result;
  * offline — no network, no external rules service, no cloud dependency;
  * read-only — it NEVER modifies the ledger, the ruleset, or the sidecar;
  * fail-closed — any integrity/structure failure exits non-zero;
  * stdlib-only — depends only on the Python standard library;
  * immutable — it does not regenerate or "accept" a freshly computed hash
    as release evidence. The ledger ``sha256`` is FROZEN release evidence.

Release-integrity model (ADR-013 / WO-037-08):

    released semantic version
      + historically released artifact bytes
      + historical release commit
      = immutable release identity

A released semantic version MUST NOT be silently changed while retaining the
same semantic version. The validator detects exactly that case (same version,
different authoritative bytes => RELEASE INTEGRITY VIOLATION).

Usage:
    python scripts/validate_severity_release.py

Exit code 0 = PASS; exit code 1 = FAIL (any integrity/structure violation).
"""

from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import List, Optional

# ---------------------------------------------------------------------------
# Defaults (repo-relative, CWD-independent).
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LEDGER = _REPO_ROOT / "docs" / "governance" / "SEVERITY_RELEASE_LEDGER.toml"
DEFAULT_RULESET_DIR = _REPO_ROOT / "docs" / "governance"

_LEDGER_VERSION_RE = re.compile(r"^\d+$")
_VERSION_RE = re.compile(
    r"^SEVERITY-RULES-v(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)$"
)
_FILENAME_VERSION_RE = re.compile(
    r"^SEVERITY_RULES_v(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)\.toml$"
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

_REQUIRED_RELEASE_FIELDS = (
    "release_id",
    "version",
    "artifact",
    "sha256",
    "released_commit",
    "governing_adr",
)


class ReleaseIntegrityError(RuntimeError):
    """Raised when the release ledger or release-integrity is invalid."""


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _git(repo_root: Path, *args: str) -> subprocess.CompletedProcess:
    """Run a local, read-only git command against ``repo_root``.

    Only local object access is used (``cat-file`` / ``show``). No network.
    """
    return subprocess.run(
        ["git", "-C", str(repo_root), *args],
        capture_output=True,
        text=True,
    )


def _artifact_bytes_at_commit(
    repo_root: Path, commit: str, artifact: str
) -> Optional[bytes]:
    """Return the artifact bytes as stored in ``commit``'s tree, or None.

    Uses ``git cat-file`` (read-only, local object access). Returns None when
    the commit does not exist or the artifact path is not present in it.
    """
    # Verify the commit object exists first.
    rc = _git(repo_root, "cat-file", "-e", f"{commit}^{{commit}}")
    if rc.returncode != 0:
        return None
    # Retrieve the blob for the artifact path at that commit.
    rc = _git(repo_root, "cat-file", "blob", f"{commit}:{artifact}")
    if rc.returncode != 0:
        return None
    return rc.stdout.encode("utf-8")


def _load_ledger(ledger_path: Path) -> dict:
    if not ledger_path.exists():
        raise ReleaseIntegrityError(
            f"release ledger not found: {ledger_path}"
        )
    try:
        with open(ledger_path, "rb") as fh:
            return tomllib.load(fh)
    except tomllib.TOMLDecodeError as exc:
        raise ReleaseIntegrityError(
            f"release ledger is malformed TOML: {exc}"
        ) from exc


def _validate_ledger_structure(ledger: dict, ledger_path: Path) -> List[dict]:
    """Validate the ledger container and return the list of release records."""
    errors: List[str] = []

    if "ledger_version" in ledger:
        if not isinstance(ledger["ledger_version"], int) or not _LEDGER_VERSION_RE.match(
            str(ledger["ledger_version"])
        ):
            errors.append(
                "ledger_version must be a positive integer"
            )
    # ledger_version is optional; if absent we do not fail the structure.

    releases = ledger.get("releases")
    if not isinstance(releases, list) or not releases:
        raise ReleaseIntegrityError(
            "release ledger requires a non-empty [[releases]] array"
        )

    if errors:
        raise ReleaseIntegrityError("; ".join(errors))

    return releases


def _validate_release_record(record: dict, ledger_path: Path) -> None:
    if not isinstance(record, dict):
        raise ReleaseIntegrityError(
            "each [[releases]] entry must be a table"
        )
    missing = [f for f in _REQUIRED_RELEASE_FIELDS if f not in record]
    if missing:
        raise ReleaseIntegrityError(
            f"release record missing required field(s): {sorted(missing)}"
        )
    for field in _REQUIRED_RELEASE_FIELDS:
        val = record[field]
        if not isinstance(val, str) or not val.strip():
            raise ReleaseIntegrityError(
                f"release record field {field!r} must be a non-empty string"
            )

    release_id = record["release_id"]
    version = record["version"]
    sha256 = record["sha256"]
    artifact = record["artifact"]
    released_commit = record["released_commit"]

    if not _VERSION_RE.match(version):
        raise ReleaseIntegrityError(
            f"release {release_id}: invalid version {version!r} "
            f"(expected SEVERITY-RULES-v<MAJOR>.<MINOR>.<PATCH>)"
        )
    if not _SHA256_RE.match(sha256):
        raise ReleaseIntegrityError(
            f"release {release_id}: invalid sha256 value {sha256!r}"
        )
    # Artifact must be a repo-relative path (no absolute path, no traversal).
    if Path(artifact).is_absolute():
        raise ReleaseIntegrityError(
            f"release {release_id}: artifact must be a repo-relative path: {artifact!r}"
        )
    if ".." in Path(artifact).parts:
        raise ReleaseIntegrityError(
            f"release {release_id}: artifact must not traverse outside the repo: {artifact!r}"
        )
    # Released commit must be a valid 40-hex commit SHA (allow full or short).
    if not re.match(r"^[0-9a-f]{4,40}$", released_commit):
        raise ReleaseIntegrityError(
            f"release {release_id}: invalid released_commit {released_commit!r}"
        )


def _find_current_ruleset(ruleset_dir: Path) -> Path:
    """Return the single authoritative ruleset file in ``ruleset_dir``.

    Exactly one ``SEVERITY_RULES_v<MAJOR>.<MINOR>.<PATCH>.toml`` file must be
    present. Zero => missing ruleset; more than one => ambiguous.
    """
    if not ruleset_dir.exists():
        raise ReleaseIntegrityError(
            f"ruleset directory not found: {ruleset_dir}"
        )
    candidates = sorted(
        p for p in ruleset_dir.iterdir()
        if p.is_file() and _FILENAME_VERSION_RE.match(p.name)
    )
    if not candidates:
        raise ReleaseIntegrityError(
            f"no authoritative ruleset artifact found in {ruleset_dir}"
        )
    if len(candidates) > 1:
        names = ", ".join(p.name for p in candidates)
        raise ReleaseIntegrityError(
            f"ambiguous authoritative ruleset: multiple artifacts present ({names})"
        )
    return candidates[0]


def validate_ledger(
    ledger_path: Path = DEFAULT_LEDGER,
    repo_root: Path = _REPO_ROOT,
) -> List[dict]:
    """Validate the ledger structure and return the (cleaned) release records."""
    ledger = _load_ledger(ledger_path)
    releases = _validate_ledger_structure(ledger, ledger_path)

    seen_versions: dict[str, str] = {}
    seen_ids: set[str] = set()
    for record in releases:
        _validate_release_record(record, ledger_path)
        release_id = record["release_id"]
        version = record["version"]
        if release_id in seen_ids:
            raise ReleaseIntegrityError(
                f"duplicate release identity: {release_id}"
            )
        seen_ids.add(release_id)
        if version in seen_versions:
            raise ReleaseIntegrityError(
                f"duplicate released version: {version!r} "
                f"(also used by {seen_versions[version]!r})"
            )
        seen_versions[version] = release_id
    return releases


def validate_historical_integrity(
    record: dict, repo_root: Path = _REPO_ROOT
) -> None:
    """Verify the release record's historical identity.

    Requires ``git cat-file <released_commit>:<artifact>`` to yield bytes whose
    SHA-256 equals the frozen ledger ``sha256``. This proves the recorded
    content was genuinely released at the recorded commit.
    """
    release_id = record["release_id"]
    released_commit = record["released_commit"]
    artifact = record["artifact"]
    expected_sha = record["sha256"]

    raw = _artifact_bytes_at_commit(repo_root, released_commit, artifact)
    if raw is None:
        # Distinguish missing commit vs missing artifact for a precise message.
        rc = _git(repo_root, "cat-file", "-e", f"{released_commit}^{{commit}}")
        if rc.returncode != 0:
            raise ReleaseIntegrityError(
                f"release {release_id}: released_commit does not exist: "
                f"{released_commit}"
            )
        raise ReleaseIntegrityError(
            f"release {release_id}: artifact not present at released_commit "
            f"{released_commit}: {artifact}"
        )
    actual_sha = _sha256_bytes(raw)
    if actual_sha != expected_sha:
        raise ReleaseIntegrityError(
            f"release {release_id}: historical artifact SHA-256 mismatch "
            f"(ledger {expected_sha}, historical {actual_sha})"
        )


def validate_current_ruleset(
    releases: List[dict],
    ruleset_dir: Path = DEFAULT_RULESET_DIR,
    repo_root: Path = _REPO_ROOT,
) -> None:
    """Validate the currently checked-out authoritative ruleset.

    The current ruleset's declared version must have exactly one matching
    release record, whose frozen ``sha256`` must equal both the current
    on-disk bytes and the historical bytes at the released commit.
    """
    current = _find_current_ruleset(ruleset_dir)

    try:
        with open(current, "rb") as fh:
            current_raw = fh.read()
    except OSError as exc:
        raise ReleaseIntegrityError(
            f"cannot read current ruleset {current}: {exc}"
        ) from exc

    try:
        parsed = tomllib.loads(current_raw.decode("utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
        raise ReleaseIntegrityError(
            f"current ruleset is malformed: {current.name}: {exc}"
        ) from exc

    ruleset_meta = parsed.get("ruleset")
    if not isinstance(ruleset_meta, dict):
        raise ReleaseIntegrityError(
            f"current ruleset {current.name} missing [ruleset] table"
        )
    version = ruleset_meta.get("version")
    if not isinstance(version, str) or not _VERSION_RE.match(version):
        raise ReleaseIntegrityError(
            f"current ruleset {current.name} has invalid version: {version!r}"
        )

    # Locate the matching release record.
    matches = [r for r in releases if r["version"] == version]
    if not matches:
        raise ReleaseIntegrityError(
            f"current ruleset version {version!r} has no release record in the ledger"
        )
    if len(matches) > 1:
        raise ReleaseIntegrityError(
            f"current ruleset version {version!r} has multiple release records"
        )
    record = matches[0]

    # Artifact-path binding: the record must point at the actual file.
    expected_rel = Path(record["artifact"])
    if expected_rel.name != current.name:
        raise ReleaseIntegrityError(
            f"release {record['release_id']}: artifact-path mismatch "
            f"(ledger {record['artifact']!r}, on-disk {current.name!r})"
        )

    # Current on-disk bytes must equal the frozen released SHA-256.
    current_sha = _sha256_bytes(current_raw)
    if current_sha != record["sha256"]:
        raise ReleaseIntegrityError(
            f"release {record['release_id']}: same-version content mutation "
            f"(version {version!r}, ledger {record['sha256']}, "
            f"current {current_sha})"
        )

    # Historical identity must also match the frozen SHA-256.
    validate_historical_integrity(record, repo_root)


def run(
    ledger_path: Path = DEFAULT_LEDGER,
    ruleset_dir: Path = DEFAULT_RULESET_DIR,
    repo_root: Path = _REPO_ROOT,
) -> int:
    """Run the full release-integrity validation. Returns 0 on PASS, 1 on FAIL."""
    releases = validate_ledger(ledger_path, repo_root)
    # Every ledger record must have valid historical identity.
    for record in releases:
        validate_historical_integrity(record, repo_root)
    # The currently checked-out authoritative ruleset must be intact.
    validate_current_ruleset(releases, ruleset_dir, repo_root)
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate severity ruleset release integrity (read-only, offline)."
    )
    parser.add_argument(
        "--ledger",
        type=Path,
        default=DEFAULT_LEDGER,
        help="Path to the release ledger TOML.",
    )
    parser.add_argument(
        "--ruleset-dir",
        type=Path,
        default=DEFAULT_RULESET_DIR,
        help="Directory containing the authoritative ruleset artifact.",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=_REPO_ROOT,
        help="Repository root for local git object access.",
    )
    args = parser.parse_args(argv)

    try:
        run(
            ledger_path=args.ledger,
            ruleset_dir=args.ruleset_dir,
            repo_root=args.repo_root,
        )
    except ReleaseIntegrityError as exc:
        print(f"RELEASE INTEGRITY: FAIL — {exc}")
        return 1

    print("RELEASE INTEGRITY: PASS — released versions immutable and intact")
    return 0


if __name__ == "__main__":
    sys.exit(main())
