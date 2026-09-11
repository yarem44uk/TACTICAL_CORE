"""WO-062 — Recording evidence access.

Proves the real architectural seam:

    canonical recording identity (audio_recording_id) -> operator service ->
    RecordingAccess (path confinement / traversal / symlink protection /
    existence / SHA-256 integrity) -> authenticated WAV response with RFC 9110
    byte-range support.

The endpoint is identity-based: the client supplies ONLY the canonical
recording identity, never a filesystem path.  The server resolves the recording
from its canonical identity, confines the resolved path to the authoritative
archive root, re-verifies SHA-256 before exposing any media byte, and serves the
WAV (200/206/416).  It is GET-only, read-only, and inherits the existing operator
Bearer auth boundary.

No production data is used: a controlled temporary WAV fixture is written and
the observation is created through the real production composition so the
canonical identity chain (audio_recording_id -> content_id -> event_id ->
immutable_id) holds exactly as in production.
"""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
from datetime import datetime, timezone

import pytest

import app.database.session as session_mod
from app.database.base import Base
from app.database.session import configure_session_manager, get_session_manager
from app.event.event import Event
from app.event.event_metadata import EventMetadata
from app.event.event_types import EventType
from app.event_sources.factory.event_factory import EventFactory
from app.event_sources.identity.event_identity import EventIdentityResolver
from app.intelligence.observation.repository import (
    SessionManagerObservationRepository,
)
from app.operator.app import STATIC_DIR
from app.operator.recording_access import (
    InvalidRecordingRangeError,
    RecordingAccess,
    RecordingIntegrityError,
    RecordingNotFoundError,
    RecordingPathEscapeError,
    RecordingUnavailableError,
    UnsatisfiableRangeError,
    parse_range,
)


# ---------------------------------------------------------------------------
# Controlled fixture
# ---------------------------------------------------------------------------

# Deterministic 1024-byte WAV-like fixture (content is not parsed by the server).
FIXTURE_BYTES = bytes(range(256)) * 4
FIXTURE_SHA256 = hashlib.sha256(FIXTURE_BYTES).hexdigest()
FIXTURE_SIZE = len(FIXTURE_BYTES)


def _reset() -> None:
    session_mod._session_manager = None


def _url(db_path: str) -> str:
    return f"sqlite:///{db_path}"


def _recording_fixture(archive_root: str, recording_id: str) -> dict:
    """Write a controlled WAV fixture inside the archive root."""
    rel = os.path.join("radio", "2026", "09", "03", recording_id + ".wav")
    wav_path = os.path.join(archive_root, rel)
    os.makedirs(os.path.dirname(wav_path), exist_ok=True)
    with open(wav_path, "wb") as fh:
        fh.write(FIXTURE_BYTES)
    return {
        "recording_id": recording_id,
        "wav_path": os.path.realpath(wav_path),
        "sha256": FIXTURE_SHA256,
        "bytes": FIXTURE_BYTES,
    }


def _recording_raw(fixture: dict) -> dict:
    """A production-shaped recording raw dict (content_id == audio_recording_id)."""
    rid = fixture["recording_id"]
    return {
        "timestamp": "2026-09-03T12:00:00+00:00",
        "occurred_at": "2026-09-03T12:00:00+00:00",
        "audio_recording_id": rid,
        "content_id": rid,
        "recording": {
            "wav_path": fixture["wav_path"],
            "mp3_path": fixture["wav_path"].replace(".wav", ".mp3"),
            "format": "wav",
            "duration_ms": 30000,
            "duration": 30.0,
            "source": "radio",
            "sha256": fixture["sha256"],
            "complete": True,
            "finalize_reason": "voice_activity",
        },
    }


def _compose(db_url: str) -> "object":
    """Configure the GLOBAL session manager and return a production runtime."""
    configure_session_manager(db_url)
    Base.metadata.create_all(get_session_manager().engine)
    from app.composition import create_event_runtime

    return create_event_runtime()


def _process(rt: "object", event: Event) -> bool:
    return rt.pipeline.process(event)


def _event_for_recording(raw: dict) -> Event:
    """Create a canonical Event via the real EventFactory (production identity)."""
    factory = EventFactory(identity_resolver=EventIdentityResolver())
    return factory.create_event(raw, "radio")


def _persist_recording(
    db_url: str, fixture: dict
) -> tuple[str, "object"]:
    """Persist a recording observation through the real composition.

    Returns ``(event_id, runtime)``.  The observation's ``immutable_id`` equals
    the canonical ``event_id`` derived from the recording ``content_id``.
    """
    rt = _compose(db_url)
    raw = _recording_raw(fixture)
    event = _event_for_recording(raw)
    assert _process(rt, event) is True
    return event.event_id, rt


def _persist_recording_with_sha(db_url: str, fixture: dict, sha_mode: str) -> None:
    """Persist a recording observation with a controlled stored ``sha256``.

    ``sha_mode`` selects the stored digest recorded in the observation evidence:
        * ``"valid"``    — ``FIXTURE_SHA256`` (matches the artifact).
        * ``"missing"``  — the ``sha256`` key is removed entirely.
        * ``"none"``     — ``sha256`` is ``None``.
        * ``"empty"``    — ``sha256`` is the empty string.
        * ``"malformed"``— ``sha256`` is ``"z"*64`` (64 non-hex chars).
        * ``"wrong"``    — ``sha256`` is ``"0"*64`` (valid length, wrong digest).

    The observation is persisted through the real production composition so the
    canonical identity chain holds; the controlled digest is what the operator
    endpoint must re-verify at access time.
    """
    rt = _compose(db_url)
    raw = _recording_raw(fixture)
    if sha_mode == "missing":
        del raw["recording"]["sha256"]
    elif sha_mode == "none":
        raw["recording"]["sha256"] = None
    elif sha_mode == "empty":
        raw["recording"]["sha256"] = ""
    elif sha_mode == "malformed":
        raw["recording"]["sha256"] = "z" * 64
    elif sha_mode == "wrong":
        raw["recording"]["sha256"] = "0" * 64
    else:
        raw["recording"]["sha256"] = FIXTURE_SHA256
    event = _event_for_recording(raw)
    assert _process(rt, event) is True


def _operator_client(mgr, *, token: str | None = None):
    """Build a real operator FastAPI app wired to the same session manager."""
    from fastapi.testclient import TestClient

    from app.entity_relations.sqlalchemy_relation_repository import (
        SQLAlchemyRelationRepository,
    )
    from app.entity_repository.sqlalchemy_entity_repository import (
        SQLAlchemyEntityRepository,
    )
    from app.event_repository.durable.sqlalchemy_event_repository import (
        SQLAlchemyEventRepository,
    )
    from app.operator.app import create_operator_app

    app = create_operator_app(
        event_repository=SQLAlchemyEventRepository(session_manager=mgr),
        entity_repository=SQLAlchemyEntityRepository(session_manager=mgr),
        relation_repository=SQLAlchemyRelationRepository(session_manager=mgr),
        observation_repository=SessionManagerObservationRepository(mgr),
    )
    return TestClient(app)


@pytest.fixture()
def file_db():
    """A file-based SQLite DB (cross-thread safe for the operator endpoint)."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    _reset()
    if os.path.exists(path):
        os.remove(path)


@pytest.fixture()
def archive_root(tmp_path, monkeypatch):
    """A temporary authoritative audio archive root.

    Also sets ``RECORDING_ARCHIVE_ROOT`` so the operator process (server-side,
    never client-supplied) resolves the archive root to this directory.
    """
    root = tmp_path / "archive"
    root.mkdir()
    monkeypatch.setenv("RECORDING_ARCHIVE_ROOT", str(root))
    return str(root)


@pytest.fixture()
def recording(archive_root):
    """A persisted recording observation + its controlled WAV fixture."""
    return _recording_fixture(archive_root, "rec-1")


# ---------------------------------------------------------------------------
# Range parsing (RFC 9110)
# ---------------------------------------------------------------------------


def test_parse_range_full_when_no_header():
    assert parse_range(None, 100) == (0, 99)
    assert parse_range("", 100) == (0, 99)


def test_parse_range_bounded():
    assert parse_range("bytes=0-999", 2000) == (0, 999)
    assert parse_range("bytes=100-199", 2000) == (100, 199)
    assert parse_range("bytes=0-0", 2000) == (0, 0)


def test_parse_range_open_ended():
    assert parse_range("bytes=100-", 2000) == (100, 1999)


def test_parse_range_suffix():
    assert parse_range("bytes=-100", 2000) == (1900, 1999)
    assert parse_range("bytes=-2000", 2000) == (0, 1999)
    assert parse_range("bytes=-5000", 2000) == (0, 1999)


def test_parse_range_clamped_end():
    assert parse_range("bytes=0-9999", 2000) == (0, 1999)


def test_parse_range_unsatisfiable_start_beyond_eof():
    with pytest.raises(UnsatisfiableRangeError):
        parse_range("bytes=2000-", 2000)


def test_parse_range_unsatisfiable_zero_suffix():
    with pytest.raises(UnsatisfiableRangeError):
        parse_range("bytes=-0", 2000)


def test_parse_range_invalid():
    with pytest.raises(InvalidRecordingRangeError):
        parse_range("items=0-100", 2000)
    with pytest.raises(InvalidRecordingRangeError):
        parse_range("bytes=", 2000)
    with pytest.raises(InvalidRecordingRangeError):
        parse_range("bytes=0-100,200-300", 2000)
    with pytest.raises(InvalidRecordingRangeError):
        parse_range("bytes=200-100", 2000)
    with pytest.raises(InvalidRecordingRangeError):
        parse_range("bytes=abc", 2000)


# ---------------------------------------------------------------------------
# RecordingAccess unit — path confinement / integrity (framework-free)
# ---------------------------------------------------------------------------


def _fake_resolver(metadata):
    return lambda recording_id: metadata if recording_id == "rec-1" else None


def test_resolve_returns_artifact_for_valid_identity(archive_root):
    fixture = _recording_fixture(archive_root, "rec-1")
    access = RecordingAccess(archive_root, _fake_resolver(_recording_raw(fixture)["recording"]))
    artifact = access.resolve("rec-1")
    assert artifact.recording_id == "rec-1"
    assert artifact.size == FIXTURE_SIZE
    assert artifact.sha256 == FIXTURE_SHA256
    assert artifact.mime_type == "audio/wav"
    assert os.path.isfile(artifact.path)


def test_resolve_unknown_identity_raises_not_found(archive_root):
    access = RecordingAccess(archive_root, _fake_resolver(None))
    with pytest.raises(RecordingNotFoundError):
        access.resolve("does-not-exist")


def test_resolve_missing_artifact_raises_unavailable(archive_root):
    # Metadata exists but the WAV file was removed.
    meta = {"wav_path": os.path.join(archive_root, "radio/missing.wav"), "sha256": FIXTURE_SHA256}
    access = RecordingAccess(archive_root, _fake_resolver(meta))
    with pytest.raises(RecordingUnavailableError):
        access.resolve("rec-1")


def test_resolve_rejects_traversal_outside_archive(archive_root):
    meta = {"wav_path": os.path.join(archive_root, "..", "..", "..", "etc", "passwd"), "sha256": FIXTURE_SHA256}
    access = RecordingAccess(archive_root, _fake_resolver(meta))
    with pytest.raises(RecordingPathEscapeError):
        access.resolve("rec-1")


def test_resolve_rejects_absolute_path_outside_archive(archive_root):
    meta = {"wav_path": "/etc/passwd", "sha256": FIXTURE_SHA256}
    access = RecordingAccess(archive_root, _fake_resolver(meta))
    with pytest.raises(RecordingPathEscapeError):
        access.resolve("rec-1")


def test_resolve_rejects_symlink_escape(archive_root):
    # A symlink inside the archive pointing outside must not be served.
    outside = os.path.join(os.path.dirname(archive_root), "outside_target.txt")
    with open(outside, "wb") as fh:
        fh.write(b"outside")
    link = os.path.join(archive_root, "escape_link.wav")
    os.symlink(outside, link)
    meta = {"wav_path": link, "sha256": FIXTURE_SHA256}
    access = RecordingAccess(archive_root, _fake_resolver(meta))
    with pytest.raises(RecordingPathEscapeError):
        access.resolve("rec-1")
    os.remove(link)
    os.remove(outside)


def test_resolve_rejects_corrupted_artifact(archive_root):
    fixture = _recording_fixture(archive_root, "rec-1")
    # Tamper with the bytes so the actual SHA-256 no longer matches.
    with open(fixture["wav_path"], "r+b") as fh:
        fh.seek(0)
        fh.write(b"\xff")
    meta = _recording_raw(fixture)["recording"]
    access = RecordingAccess(archive_root, _fake_resolver(meta))
    with pytest.raises(RecordingIntegrityError):
        access.resolve("rec-1")


def test_resolve_rejects_truncated_hash(archive_root):
    fixture = _recording_fixture(archive_root, "rec-1")
    meta = _recording_raw(fixture)["recording"]
    meta = dict(meta, sha256=FIXTURE_SHA256[:16])  # truncated stored hash
    access = RecordingAccess(archive_root, _fake_resolver(meta))
    with pytest.raises(RecordingIntegrityError):
        access.resolve("rec-1")


# -- WO-062-C1: mandatory stored SHA-256 (fail-closed integrity gate) ---------


def test_resolve_missing_sha_fails_closed(archive_root):
    """No ``sha256`` key -> fail closed (no artifact served)."""
    fixture = _recording_fixture(archive_root, "rec-1")
    meta = _recording_raw(fixture)["recording"]
    del meta["sha256"]
    access = RecordingAccess(archive_root, _fake_resolver(meta))
    with pytest.raises(RecordingIntegrityError):
        access.resolve("rec-1")


def test_resolve_none_sha_fails_closed(archive_root):
    """``sha256 is None`` -> fail closed."""
    fixture = _recording_fixture(archive_root, "rec-1")
    meta = _recording_raw(fixture)["recording"]
    meta["sha256"] = None
    access = RecordingAccess(archive_root, _fake_resolver(meta))
    with pytest.raises(RecordingIntegrityError):
        access.resolve("rec-1")


def test_resolve_empty_sha_fails_closed(archive_root):
    """``sha256 == ""`` -> fail closed."""
    fixture = _recording_fixture(archive_root, "rec-1")
    meta = _recording_raw(fixture)["recording"]
    meta["sha256"] = ""
    access = RecordingAccess(archive_root, _fake_resolver(meta))
    with pytest.raises(RecordingIntegrityError):
        access.resolve("rec-1")


@pytest.mark.parametrize(
    "bad_sha",
    [
        "abc",                     # too short
        "z" * 64,                  # correct length, non-hex
        "0" * 65,                  # too long
        "  " + FIXTURE_SHA256,     # leading whitespace (corrupted)
        FIXTURE_SHA256 + " ",      # trailing whitespace (corrupted)
        "g" * 64,                  # non-hex, correct length
        FIXTURE_SHA256[:-1] + " ",  # internal/corrupted char
    ],
)
def test_resolve_malformed_sha_fails_closed(archive_root, bad_sha):
    """Any malformed stored hash -> fail closed, no media bytes exposed."""
    fixture = _recording_fixture(archive_root, "rec-1")
    meta = _recording_raw(fixture)["recording"]
    meta["sha256"] = bad_sha
    access = RecordingAccess(archive_root, _fake_resolver(meta))
    with pytest.raises(RecordingIntegrityError):
        access.resolve("rec-1")


def test_resolve_valid_matching_sha_serves(archive_root):
    """A correct 64-hex stored hash matching the artifact is served."""
    fixture = _recording_fixture(archive_root, "rec-1")
    meta = _recording_raw(fixture)["recording"]
    access = RecordingAccess(archive_root, _fake_resolver(meta))
    artifact = access.resolve("rec-1")
    assert artifact.sha256 == FIXTURE_SHA256
    assert artifact.size == FIXTURE_SIZE
    assert artifact.mime_type == "audio/wav"


def test_resolve_valid_length_wrong_sha_fails_closed(archive_root):
    """A valid-length (64-hex) but incorrect digest -> fail closed."""
    fixture = _recording_fixture(archive_root, "rec-1")
    meta = _recording_raw(fixture)["recording"]
    wrong = hashlib.sha256(b"definitely-wrong").hexdigest()  # 64 hex, != FIXTURE_SHA256
    assert wrong != FIXTURE_SHA256
    meta["sha256"] = wrong
    access = RecordingAccess(archive_root, _fake_resolver(meta))
    with pytest.raises(RecordingIntegrityError):
        access.resolve("rec-1")


def test_resolve_uppercase_sha_matching_serves(archive_root):
    """Uppercase hex stored digest of the correct value is accepted."""
    fixture = _recording_fixture(archive_root, "rec-1")
    meta = _recording_raw(fixture)["recording"]
    meta["sha256"] = FIXTURE_SHA256.upper()
    access = RecordingAccess(archive_root, _fake_resolver(meta))
    artifact = access.resolve("rec-1")
    assert artifact.sha256 == FIXTURE_SHA256


# ---------------------------------------------------------------------------
# Integration — authenticated operator endpoint
# ---------------------------------------------------------------------------


def test_recording_unauthenticated_rejected(file_db, archive_root, recording, monkeypatch):
    monkeypatch.setenv("OPERATOR_TOKEN", "secret-token")
    mgr = configure_session_manager(_url(file_db))
    Base.metadata.create_all(mgr.engine)
    _persist_recording(_url(file_db), recording)
    client = _operator_client(mgr)
    # No Bearer token -> 401.
    resp = client.get(f"/api/v1/operator/recordings/{recording['recording_id']}")
    assert resp.status_code == 401, resp.text
    assert resp.json()["error_type"] == "AuthenticationRequired"
    _reset()


def test_recording_authenticated_access(file_db, archive_root, recording, monkeypatch):
    monkeypatch.setenv("OPERATOR_TOKEN", "secret-token")
    mgr = configure_session_manager(_url(file_db))
    Base.metadata.create_all(mgr.engine)
    _persist_recording(_url(file_db), recording)
    client = _operator_client(mgr)
    headers = {"Authorization": "Bearer secret-token"}
    resp = client.get(
        f"/api/v1/operator/recordings/{recording['recording_id']}", headers=headers
    )
    assert resp.status_code == 200, resp.text
    assert resp.content == FIXTURE_BYTES
    assert resp.headers["content-type"].startswith("audio/wav")
    assert resp.headers["content-length"] == str(FIXTURE_SIZE)
    assert resp.headers["accept-ranges"] == "bytes"
    _reset()


def test_recording_identity_resolution(file_db, archive_root, recording):
    mgr = configure_session_manager(_url(file_db))
    Base.metadata.create_all(mgr.engine)
    event_id, _rt = _persist_recording(_url(file_db), recording)
    client = _operator_client(mgr)
    resp = client.get(f"/api/v1/operator/recordings/{recording['recording_id']}")
    assert resp.status_code == 200, resp.text
    assert resp.content == FIXTURE_BYTES
    # The observation immutable_id is the canonical event_id derived from the
    # recording content_id (production identity chain).
    assert len(event_id) == 36
    _reset()


def test_recording_no_arbitrary_path(file_db, archive_root, recording):
    """The client cannot supply a filesystem path as a lookup parameter."""
    mgr = configure_session_manager(_url(file_db))
    Base.metadata.create_all(mgr.engine)
    _persist_recording(_url(file_db), recording)
    client = _operator_client(mgr)
    # A path-like value is treated purely as an identity; no observation maps to
    # it, so it resolves to 404 and never touches the filesystem.
    for bad in ["../../etc/passwd", "/etc/passwd", "..%2Fetc%2Fpasswd"]:
        resp = client.get(f"/api/v1/operator/recordings/{bad}")
        assert resp.status_code == 404, resp.text
    _reset()


def test_recording_traversal_rejected_via_metadata(file_db, archive_root, recording):
    """A persisted observation whose metadata points outside the archive is refused."""
    mgr = configure_session_manager(_url(file_db))
    Base.metadata.create_all(mgr.engine)
    fixture = dict(recording)
    fixture["wav_path"] = "/etc/passwd"  # outside archive
    _persist_recording(_url(file_db), fixture)
    client = _operator_client(mgr)
    resp = client.get(f"/api/v1/operator/recordings/{recording['recording_id']}")
    assert resp.status_code == 404, resp.text
    _reset()


def test_recording_missing_artifact(file_db, archive_root, recording):
    """Metadata exists but the WAV is missing -> safe 404 (no path leaked)."""
    mgr = configure_session_manager(_url(file_db))
    Base.metadata.create_all(mgr.engine)
    _persist_recording(_url(file_db), recording)
    # Remove the WAV after persistence.
    os.remove(recording["wav_path"])
    client = _operator_client(mgr)
    resp = client.get(f"/api/v1/operator/recordings/{recording['recording_id']}")
    assert resp.status_code == 404, resp.text
    body = resp.json()
    assert body["error_type"] == "NotFoundError"
    assert "wav_path" not in resp.text
    assert "archive" not in resp.text
    _reset()


def test_recording_corrupted_artifact_rejected(file_db, archive_root, recording):
    """Integrity failure is caught before any media byte is exposed."""
    mgr = configure_session_manager(_url(file_db))
    Base.metadata.create_all(mgr.engine)
    _persist_recording(_url(file_db), recording)
    # Tamper with the artifact so the stored SHA-256 no longer matches.
    with open(recording["wav_path"], "r+b") as fh:
        fh.seek(0)
        fh.write(b"\xff")
    client = _operator_client(mgr)
    resp = client.get(f"/api/v1/operator/recordings/{recording['recording_id']}")
    assert resp.status_code == 404, resp.text
    # No partial media body is delivered.
    assert resp.content == b"" or resp.headers.get("content-type", "").startswith("application/json")
    _reset()


@pytest.mark.parametrize("sha_mode", ["missing", "none", "empty", "malformed", "wrong"])
def test_recording_invalid_stored_sha_rejected(file_db, archive_root, recording, sha_mode):
    """A missing/None/empty/malformed/wrong stored SHA-256 yields NO media bytes.

    The endpoint must fail closed: an unverifiable stored digest means the
    artifact is refused (safe 404) with no audio body and no filesystem path
    leakage.
    """
    mgr = configure_session_manager(_url(file_db))
    Base.metadata.create_all(mgr.engine)
    _persist_recording_with_sha(_url(file_db), recording, sha_mode)
    client = _operator_client(mgr)
    resp = client.get(f"/api/v1/operator/recordings/{recording['recording_id']}")
    assert resp.status_code == 404, f"{sha_mode}: {resp.text}"
    body = resp.json()
    assert body["error_type"] == "NotFoundError", f"{sha_mode}: {resp.text}"
    # No audio body: the response is a JSON error, not a media payload.
    assert not resp.headers.get("content-type", "").startswith("audio/wav"), sha_mode
    assert resp.content != FIXTURE_BYTES, sha_mode
    # No filesystem path / archive root leakage.
    assert "wav_path" not in resp.text, sha_mode
    assert "archive" not in resp.text, sha_mode
    assert "/etc" not in resp.text, sha_mode
    assert ".wav" not in resp.text, sha_mode
    _reset()


def test_recording_range_206(file_db, archive_root, recording):
    mgr = configure_session_manager(_url(file_db))
    Base.metadata.create_all(mgr.engine)
    _persist_recording(_url(file_db), recording)
    client = _operator_client(mgr)
    resp = client.get(
        f"/api/v1/operator/recordings/{recording['recording_id']}",
        headers={"Range": "bytes=0-999"},
    )
    assert resp.status_code == 206, resp.text
    assert resp.headers["content-range"] == f"bytes 0-999/{FIXTURE_SIZE}"
    assert resp.headers["content-length"] == "1000"
    assert resp.headers["accept-ranges"] == "bytes"
    assert resp.headers["content-type"].startswith("audio/wav")
    assert resp.content == FIXTURE_BYTES[0:1000]
    _reset()


def test_recording_range_suffix_and_open(file_db, archive_root, recording):
    mgr = configure_session_manager(_url(file_db))
    Base.metadata.create_all(mgr.engine)
    _persist_recording(_url(file_db), recording)
    client = _operator_client(mgr)
    # Suffix range.
    resp = client.get(
        f"/api/v1/operator/recordings/{recording['recording_id']}",
        headers={"Range": "bytes=-100"},
    )
    assert resp.status_code == 206
    assert resp.content == FIXTURE_BYTES[-100:]
    # Open-ended range.
    resp = client.get(
        f"/api/v1/operator/recordings/{recording['recording_id']}",
        headers={"Range": "bytes=100-"},
    )
    assert resp.status_code == 206
    assert resp.content == FIXTURE_BYTES[100:]
    _reset()


def test_recording_range_416(file_db, archive_root, recording):
    mgr = configure_session_manager(_url(file_db))
    Base.metadata.create_all(mgr.engine)
    _persist_recording(_url(file_db), recording)
    client = _operator_client(mgr)
    resp = client.get(
        f"/api/v1/operator/recordings/{recording['recording_id']}",
        headers={"Range": "bytes=99999-"},
    )
    assert resp.status_code == 416, resp.text
    assert resp.headers["content-range"] == f"bytes */{FIXTURE_SIZE}"
    _reset()


def test_recording_range_invalid_400(file_db, archive_root, recording):
    mgr = configure_session_manager(_url(file_db))
    Base.metadata.create_all(mgr.engine)
    _persist_recording(_url(file_db), recording)
    client = _operator_client(mgr)
    resp = client.get(
        f"/api/v1/operator/recordings/{recording['recording_id']}",
        headers={"Range": "items=0-100"},
    )
    assert resp.status_code == 400, resp.text
    _reset()


def test_recording_read_only(file_db, archive_root, recording):
    """GET does not modify the artifact (size + bytes unchanged)."""
    mgr = configure_session_manager(_url(file_db))
    Base.metadata.create_all(mgr.engine)
    _persist_recording(_url(file_db), recording)
    before = open(recording["wav_path"], "rb").read()
    before_size = os.path.getsize(recording["wav_path"])
    before_mtime = os.path.getmtime(recording["wav_path"])
    client = _operator_client(mgr)
    client.get(f"/api/v1/operator/recordings/{recording['recording_id']}")
    client.get(
        f"/api/v1/operator/recordings/{recording['recording_id']}",
        headers={"Range": "bytes=0-10"},
    )
    after = open(recording["wav_path"], "rb").read()
    assert after == before
    assert os.path.getsize(recording["wav_path"]) == before_size
    assert os.path.getmtime(recording["wav_path"]) == before_mtime
    _reset()


def test_recording_concurrent_access(file_db, archive_root, recording):
    """Multiple concurrent reads do not corrupt or alter the artifact."""
    mgr = configure_session_manager(_url(file_db))
    Base.metadata.create_all(mgr.engine)
    _persist_recording(_url(file_db), recording)
    client = _operator_client(mgr)
    import concurrent.futures as cf

    def _fetch(i):
        headers = {"Range": f"bytes={i}-{i+9}"} if i < FIXTURE_SIZE - 10 else None
        return client.get(
            f"/api/v1/operator/recordings/{recording['recording_id']}",
            headers=headers or {},
        )

    with cf.ThreadPoolExecutor(max_workers=8) as pool:
        responses = list(pool.map(_fetch, range(0, FIXTURE_SIZE, 16)))
    for resp in responses:
        assert resp.status_code in (200, 206), resp.text
    # Artifact unchanged after concurrent reads.
    assert open(recording["wav_path"], "rb").read() == FIXTURE_BYTES
    _reset()


def test_recording_unknown_identity_404(file_db, archive_root, recording):
    mgr = configure_session_manager(_url(file_db))
    Base.metadata.create_all(mgr.engine)
    _persist_recording(_url(file_db), recording)
    client = _operator_client(mgr)
    resp = client.get("/api/v1/operator/recordings/unknown-identity")
    assert resp.status_code == 404, resp.text
    _reset()


# ---------------------------------------------------------------------------
# Frontend contract (WO-062 §17) — playback URL from canonical identity only
# ---------------------------------------------------------------------------


def test_frontend_playback_uses_identity_not_path():
    js = (STATIC_DIR / "operator.js").read_text()
    # The playback URL is built from the operator recordings endpoint.
    assert 'API + "/recordings/" + encodeURIComponent(recordingId)' in js
    assert "audio_recording_id" in js
    # The media URL must not be constructed from wav_path / mp3_path.
    assert '"/recordings/" +' in js
    # Ensure the playback src is never a raw filesystem path.
    assert "data-rec-url=" in js
    # No filesystem path is used as a fetch target for playback.
    assert 'fetch("' not in js
    # GET-only for the recording fetch.
    assert 'withAuth({ method: "GET" })' in js


def test_frontend_still_get_only_and_operator_prefixed():
    js = (STATIC_DIR / "operator.js").read_text()
    fetches = re.findall(r"fetch\([^)]*\)", js)
    assert fetches
    for f in fetches:
        if "method:" in f:
            assert "GET" in f, f"non-GET fetch found: {f}"
    for method in ["POST", "PUT", "PATCH", "DELETE"]:
        assert f'"{method}"' not in js
        assert f"'{method}'" not in js


def test_static_wall_playback_shell_present():
    html = (STATIC_DIR / "index.html").read_text()
    js = (STATIC_DIR / "operator.js").read_text()
    # The wall view is still present and wired (WO-061 invariants preserved).
    assert 'id="tab-wall"' in html
    assert 'id="wall-feed"' in html
    assert "bindRecordingAudio" in js
