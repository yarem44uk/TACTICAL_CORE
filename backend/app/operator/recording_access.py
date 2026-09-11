"""WO-062 — Read-only recording evidence access (server-side resolution).

Pure, framework-free module that turns a canonical ``recording_id`` into a
confined, integrity-verified, servable WAV artifact.  It deliberately contains
no HTTP, no SQLAlchemy, no Event/Observation import — the operator service wires
in a ``metadata_resolver`` callable and the HTTP router turns the resulting
:class:`RecordingArtifact` into a 200/206/416 response.

Security guarantees implemented here:
  * identity-only lookup (the caller supplies a canonical recording identity,
    never a filesystem path);
  * strict path confinement to the configured authoritative archive root;
  * traversal protection (``..`` / absolute / encoded components cannot escape);
  * symlink protection (``os.path.realpath`` resolves the final target, so a
    symlink pointing outside the archive is rejected);
  * existence validation;
  * SHA-256 integrity re-verification against the stored hash (access-time gate
    — a mismatch is refused BEFORE any media byte is exposed).

Author: Tactical Core Engineering Team
Version: 1.0
"""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from typing import Callable, Optional

# WAV MIME type (authoritative recording artifact; MP3 is only a derivative).
WAV_MIME_TYPE = "audio/wav"

# Chunk size for streaming SHA-256 (1 MiB) and range reads (64 KiB).
_SHA_CHUNK = 1 << 20
_READ_CHUNK = 1 << 16

# RFC 9110 single byte-range: ``bytes=start-end`` / ``bytes=start-`` /
# ``bytes=-suffix``.
_RANGE_RE = re.compile(r"^\s*(\d*)-(\d*)\s*$")

# A valid SHA-256 hex digest is exactly 64 lowercase/uppercase hex chars.
# Anything else (missing, empty, truncated, padded, non-hex, whitespace) is a
# malformed stored hash and must fail closed.
_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


class RecordingAccessError(Exception):
    """Base error for recording evidence access."""


class RecordingNotFoundError(RecordingAccessError):
    """The canonical recording identity does not resolve to a recording."""


class RecordingUnavailableError(RecordingAccessError):
    """The recording exists in metadata but its artifact is absent / invalid."""


class RecordingPathEscapeError(RecordingAccessError):
    """The resolved WAV path escapes the configured archive root."""


class RecordingIntegrityError(RecordingAccessError):
    """The actual artifact SHA-256 does not match the stored hash."""


class InvalidRecordingRangeError(RecordingAccessError):
    """Malformed / unsupported Range header (client error, 400)."""


class UnsatisfiableRangeError(RecordingAccessError):
    """Syntactically valid but unsatisfiable Range header (416)."""


@dataclass(frozen=True)
class RecordingArtifact:
    """A verified, confined, servable recording artifact."""

    recording_id: str
    path: str
    size: int
    sha256: str
    mime_type: str


def parse_range(range_header: Optional[str], size: int) -> tuple[int, int]:
    """Parse a single HTTP byte-range per RFC 9110.

    Returns the inclusive ``(start, end)`` range.  A ``None`` / empty header
    yields the full range ``(0, size - 1)``.

    Raises:
        InvalidRecordingRangeError: unsupported/malformed range (HTTP 400).
        UnsatisfiableRangeError: range start is at/after EOF, or a zero-length
            suffix range (HTTP 416).
    """
    if size <= 0:
        raise RecordingUnavailableError("recording artifact is empty")
    if range_header is None or range_header.strip() == "":
        return (0, size - 1)
    header = range_header.strip()
    if not header.lower().startswith("bytes="):
        raise InvalidRecordingRangeError("only byte ranges are supported")
    spec = header[len("bytes="):].strip()
    if "," in spec:
        raise InvalidRecordingRangeError("multiple ranges are not supported")
    match = _RANGE_RE.match(spec)
    if not match:
        raise InvalidRecordingRangeError("malformed byte range")
    start_s, end_s = match.group(1), match.group(2)
    if start_s == "" and end_s == "":
        raise InvalidRecordingRangeError("malformed byte range")

    if start_s == "":
        # Suffix range: last N bytes.
        suffix = int(end_s)
        if suffix <= 0:
            raise UnsatisfiableRangeError("suffix length must be positive")
        start = max(0, size - suffix)
        end = size - 1
    else:
        start = int(start_s)
        if end_s == "":
            end = size - 1
        else:
            end = int(end_s)

    if start >= size:
        raise UnsatisfiableRangeError("range start beyond EOF")
    if start > end:
        raise InvalidRecordingRangeError("range start exceeds end")
    if end >= size:
        end = size - 1
    return (start, end)


class RecordingAccess:
    """Resolve a canonical recording identity to a confined, verified artifact.

    Args:
        archive_root: the configured authoritative audio archive root.  Every
            served WAV path must resolve inside this root (confinement).
        metadata_resolver: callable ``(recording_id) -> Optional[dict]`` that
            returns the recording metadata (containing ``wav_path`` and
            ``sha256``) for a canonical recording identity, or ``None`` when the
            identity is unknown.
    """

    def __init__(
        self,
        archive_root: str,
        metadata_resolver: Callable[[str], Optional[dict]],
    ) -> None:
        self._archive_root = os.path.realpath(archive_root)
        self._metadata_resolver = metadata_resolver

    def resolve(self, recording_id: str) -> RecordingArtifact:
        """Resolve ``recording_id`` to a verified, confined WAV artifact.

        The stored SHA-256 is mandatory: a missing, ``None``, empty, or
        malformed stored hash fails closed (``RecordingIntegrityError``) and NO
        media byte is exposed, even if the on-disk artifact is intact.

        Raises:
            RecordingNotFoundError: identity unknown / no recording metadata.
            RecordingPathEscapeError: resolved path escapes the archive root.
            RecordingUnavailableError: artifact absent or not a regular file.
            RecordingIntegrityError: stored SHA-256 missing/malformed, or the
                actual artifact SHA-256 does not match the stored hash.
        """
        if not recording_id or not isinstance(recording_id, str):
            raise RecordingNotFoundError("invalid recording identity")

        metadata = self._metadata_resolver(recording_id)
        if metadata is None:
            raise RecordingNotFoundError("recording not found")

        wav_path = metadata.get("wav_path")
        if not wav_path:
            raise RecordingUnavailableError("recording artifact path unavailable")

        resolved = self._confine(wav_path)

        if not os.path.isfile(resolved):
            raise RecordingUnavailableError("recording artifact missing")
        size = os.path.getsize(resolved)

        actual_sha = self._sha256(resolved)
        # Mandatory fail-closed integrity gate: NO verified stored SHA-256 means
        # NO media bytes are exposed.  A missing, empty, malformed, or
        # non-verifiable stored hash is refused BEFORE any byte is served, even
        # if the on-disk bytes happen to be intact.
        stored_sha = metadata.get("sha256")
        self._verify_integrity(stored_sha, actual_sha)

        return RecordingArtifact(
            recording_id=recording_id,
            path=resolved,
            size=size,
            sha256=actual_sha,
            mime_type=WAV_MIME_TYPE,
        )

    def _confine(self, wav_path: str) -> str:
        """Resolve ``wav_path`` and verify it stays inside the archive root.

        ``os.path.realpath`` collapses ``..`` and resolves symlinks, so a path
        that traverses or a symlink that points outside the archive yields a
        real path outside ``archive_root`` and is rejected.

        Raises:
            RecordingPathEscapeError: the resolved path escapes the archive root.
        """
        if os.path.isabs(wav_path):
            candidate = wav_path
        else:
            candidate = os.path.join(self._archive_root, wav_path)
        resolved = os.path.realpath(candidate)
        root = self._archive_root
        if resolved != root and not resolved.startswith(root + os.sep):
            raise RecordingPathEscapeError("recording path escapes the archive root")
        return resolved

    @staticmethod
    def _sha256(path: str) -> str:
        """Compute the SHA-256 hex digest of a file without loading it whole."""
        digest = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(_SHA_CHUNK), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _verify_integrity(stored_sha: object, actual_sha: str) -> None:
        """Fail-closed SHA-256 integrity verification.

        The stored hash MUST be a well-formed SHA-256 digest: exactly 64 hex
        characters (lower- or upper-case) with no surrounding or embedded
        whitespace.  Anything else — missing key, ``None``, empty string,
        truncated/padded value, non-hex characters, whitespace-corrupted value
        — is a malformed stored hash and is refused
        (``RecordingIntegrityError``), so NO media byte is ever exposed without
        a verified stored digest.  The stored value is validated as-is (not
        stripped), so a whitespace-corrupted digest cannot be silently
        "repaired" into an accepted one.

        For a valid stored digest, the actual on-disk artifact is hashed and
        compared; a mismatch is refused.  The stored hash is never rewritten and
        metadata is never mutated — this is an access-time verification gate.

        Raises:
            RecordingIntegrityError: stored hash missing/malformed, or the
                actual digest does not match the stored digest.
        """
        if not isinstance(stored_sha, str):
            raise RecordingIntegrityError(
                "stored recording sha256 is missing or invalid"
            )
        if not _SHA256_RE.fullmatch(stored_sha):
            raise RecordingIntegrityError(
                "stored recording sha256 is missing or invalid"
            )
        if not _safe_hex_compare(stored_sha, actual_sha):
            raise RecordingIntegrityError("recording artifact integrity mismatch")


def _safe_hex_compare(expected: str, actual: str) -> bool:
    """Length-safe hex digest comparison.

    Returns ``False`` for any length mismatch (a truncated/corrupt hash) and
    otherwise compares the two lowercase hex strings.  No partial comparison is
    ever reported as equal.
    """
    if not isinstance(expected, str) or not isinstance(actual, str):
        return False
    e = expected.strip().lower()
    a = actual.strip().lower()
    if len(e) != len(a):
        return False
    return e == a
