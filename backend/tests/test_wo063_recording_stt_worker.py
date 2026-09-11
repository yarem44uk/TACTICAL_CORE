"""WO-063 — STT processing worker against an accepted durable recording.

Proves the real architectural seam:

    audio_recording_id
        -> resolve accepted recording (authoritative RecordingAccess)
        -> verify recording integrity (mandatory stored SHA-256, WO-062-C1)
        -> obtain authoritative media (read-only)
        -> STT (ITranscriber seam)
        -> deterministic transcript evidence
        -> enrichment seam (on_transcript) -> canonical event path

Invariants proven here:
  * identity-only: the caller supplies the canonical recording identity, never a
    filesystem path; the verified media path comes from the trusted resolver.
  * WO-062-C1 mandatory integrity gate: NO verified stored SHA-256 -> NO media
    bytes consumed (missing / null / empty / malformed / wrong hash fails closed).
  * read-only source: the authoritative WAV is never modified.
  * engine-neutral: consumes the existing ``ITranscriber`` seam; no engine
    selection, no model download, no network.
  * deterministic transcript evidence with a distinct content_id
    (``<audio_recording_id>|transcript``).
  * idempotent: same recording + same STT contract/version -> same result, no
    duplicate STT execution.
  * safe, typed failures with no filesystem path / internal detail leak.

No production data is used: a controlled temporary WAV fixture is written and
the recording is resolved through a real ``RecordingAccess`` (or a controlled
fake resolver) so the integrity/confinement contract holds as in production.
"""

from __future__ import annotations

import hashlib
import os
import struct
import tempfile
import threading
import wave

import pytest

from app.audio.recording_stt_worker import (
    RecordingIdentityInvalidError,
    RecordingIntegrityViolationError,
    RecordingMediaUnavailableError,
    RecordingMediaUnreadableError,
    RecordingMissingError,
    RecordingSttError,
    RecordingSttWorker,
    RecordingTranscriptResult,
    SttExecutionFailedError,
)
from app.audio.wav_writer import write_wav_atomic
from app.contracts.audio import ITranscriber
from app.operator.recording_access import RecordingAccess


# --------------------------------------------------------------------------- #
# Fixtures / helpers
# --------------------------------------------------------------------------- #


def _wav_pcm(samples: int = 1600, value: int = 1000) -> bytes:
    return struct.pack(f"<{samples}h", *([value] * samples))


def _write_wav(
    root: str,
    name: str = "rec",
    *,
    sample_rate: int = 8000,
    channels: int = 1,
    sampwidth: int = 2,
    pcm: bytes | None = None,
) -> tuple[str, bytes]:
    pcm = pcm if pcm is not None else _wav_pcm()
    path = os.path.join(root, f"{name}.wav")
    write_wav_atomic(pcm, path, sample_rate, channels, sampwidth)
    return path, pcm


def _sha256_file(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _recording_metadata(wav_path: str, sha256: str | None) -> dict:
    """Recording metadata shaped like the production observation evidence."""
    meta = {
        "wav_path": os.path.realpath(wav_path),
        "sha256": sha256,
        "format": "wav",
    }
    return meta


def _make_access(archive_root: str, metadata: dict | None) -> RecordingAccess:
    """Build a real ``RecordingAccess`` with a fixed metadata resolver."""
    return RecordingAccess(
        archive_root=archive_root,
        metadata_resolver=lambda rid: metadata if rid == "rec-1" else None,
    )


class _FakeSttTranscriber(ITranscriber):
    """Deterministic fake transcriber (no engine, no model, no network)."""

    def __init__(
        self,
        text: str = "test transcript",
        ready: bool = True,
        fail_for: set[str] | None = None,
        empty_for: set[str] | None = None,
    ) -> None:
        self._text = text
        self._ready = ready
        self._fail_for = set(fail_for or ())
        self._empty_for = set(empty_for or ())
        self.transcribe_calls: list[tuple[bytes, str | None]] = []
        self.caller_threads: list[str] = []

    @property
    def model(self) -> str:
        return "fake-stt"

    def is_ready(self) -> bool:
        return self._ready

    def transcribe(self, audio_data: bytes, language: str | None = None) -> str:
        self.transcribe_calls.append((audio_data, language))
        self.caller_threads.append(threading.current_thread().name)
        key = hashlib.sha256(audio_data).hexdigest()
        if key in self._fail_for:
            raise RuntimeError("fake STT engine failure")
        if key in self._empty_for:
            return ""
        return self._text


def _worker(
    transcriber: ITranscriber | None,
    resolver,
    *,
    source: str = "radio",
    on_transcript=None,
    language: str | None = None,
) -> RecordingSttWorker:
    return RecordingSttWorker(
        transcriber,
        resolver,
        source=source,
        language=language,
        on_transcript=on_transcript,
    )


@pytest.fixture()
def archive_root(tmp_path):
    root = tmp_path / "archive"
    root.mkdir()
    return str(root)


# --------------------------------------------------------------------------- #
# Case 1 — accepted valid recording -> success with transcript
# --------------------------------------------------------------------------- #


def test_wo063_01_valid_recording_success(archive_root):
    wav, pcm = _write_wav(os.path.join(archive_root, "radio"), name="rec-1")
    sha = _sha256_file(wav)
    access = _make_access(archive_root, _recording_metadata(wav, sha))
    emitted: list[dict] = []
    fake = _FakeSttTranscriber(text="прийом")
    worker = _worker(fake, access.resolve, on_transcript=emitted.append)

    result = worker.transcribe("rec-1")

    assert isinstance(result, RecordingTranscriptResult)
    assert result.audio_recording_id == "rec-1"
    assert result.text == "прийом"
    assert result.content_id == "rec-1|transcript"
    assert result.engine == "fake-stt"
    assert result.model == "fake-stt"
    assert result.wav_sha256 == sha
    assert result.raw["audio_recording_id"] == "rec-1"
    assert result.raw["content_id"] == "rec-1|transcript"
    assert result.raw["transcript"]["text"] == "прийом"
    assert result.raw["transcript"]["wav_sha256"] == sha
    # Enrichment seam emitted the derived transcript evidence.
    assert len(emitted) == 1
    assert emitted[0]["content_id"] == "rec-1|transcript"
    # The transcriber received the decoded PCM of the master.
    assert len(fake.transcribe_calls) == 1
    assert fake.transcribe_calls[0][0] == pcm
    assert worker.failures == 0


def test_wo063_01b_no_callsign_enrichment(archive_root):
    """WO-063 scope: callsign/speaker enrichment is deferred to WO-064."""
    wav, _ = _write_wav(os.path.join(archive_root, "radio"), name="rec-1")
    sha = _sha256_file(wav)
    access = _make_access(archive_root, _recording_metadata(wav, sha))
    worker = _worker(_FakeSttTranscriber(text="ok"), access.resolve)
    result = worker.transcribe("rec-1")
    raw = result.raw
    # No invented callsign / confidence / detection_method in the derived evidence.
    assert "detected_callsigns" not in raw
    assert "callsign" not in raw
    assert "detection_method" not in raw
    assert raw["transcript"]["text"] == "ok"


# --------------------------------------------------------------------------- #
# Case 2 — missing recording
# --------------------------------------------------------------------------- #


def test_wo063_02_missing_recording(archive_root):
    wav, _ = _write_wav(os.path.join(archive_root, "radio"), name="rec-1")
    sha = _sha256_file(wav)
    access = _make_access(archive_root, _recording_metadata(wav, sha))
    worker = _worker(_FakeSttTranscriber(), access.resolve)
    with pytest.raises(RecordingMissingError):
        worker.transcribe("does-not-exist")


# --------------------------------------------------------------------------- #
# Case 3 — invalid recording identity
# --------------------------------------------------------------------------- #


def test_wo063_03_invalid_identity(archive_root):
    wav, _ = _write_wav(os.path.join(archive_root, "radio"), name="rec-1")
    sha = _sha256_file(wav)
    access = _make_access(archive_root, _recording_metadata(wav, sha))
    worker = _worker(_FakeSttTranscriber(), access.resolve)
    for bad in ["", "   ", None, 123]:
        with pytest.raises(RecordingIdentityInvalidError):
            worker.transcribe(bad)


# --------------------------------------------------------------------------- #
# Cases 4 / 5 / 6 — mandatory SHA-256 integrity gate (WO-062-C1)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "sha_mode",
    ["missing", "none", "empty", "malformed", "wrong"],
)
def test_wo063_04_05_06_sha_gate_fails_closed(archive_root, sha_mode):
    wav, _ = _write_wav(os.path.join(archive_root, "radio"), name="rec-1")
    real_sha = _sha256_file(wav)
    meta = _recording_metadata(wav, real_sha)
    if sha_mode == "missing":
        del meta["sha256"]
    elif sha_mode == "none":
        meta["sha256"] = None
    elif sha_mode == "empty":
        meta["sha256"] = ""
    elif sha_mode == "malformed":
        meta["sha256"] = "z" * 64
    elif sha_mode == "wrong":
        meta["sha256"] = "0" * 64
    access = _make_access(archive_root, meta)
    worker = _worker(_FakeSttTranscriber(text="should-not-run"), access.resolve)
    with pytest.raises(RecordingIntegrityViolationError):
        worker.transcribe("rec-1")
    # No media bytes consumed: the transcriber never ran.
    # (RecordingAccess fails closed before the worker reads the artifact.)
    assert worker.failures == 0


def test_wo063_06b_truncated_hash_fails_closed(archive_root):
    wav, _ = _write_wav(os.path.join(archive_root, "radio"), name="rec-1")
    sha = _sha256_file(wav)
    access = _make_access(archive_root, _recording_metadata(wav, sha[:16]))
    worker = _worker(_FakeSttTranscriber(), access.resolve)
    with pytest.raises(RecordingIntegrityViolationError):
        worker.transcribe("rec-1")


# --------------------------------------------------------------------------- #
# Case 7 — missing media artifact
# --------------------------------------------------------------------------- #


def test_wo063_07_missing_media_artifact(archive_root):
    # Metadata points at a WAV that does not exist.
    missing = os.path.join(archive_root, "radio", "gone.wav")
    access = _make_access(archive_root, _recording_metadata(missing, "a" * 64))
    worker = _worker(_FakeSttTranscriber(), access.resolve)
    with pytest.raises(RecordingMediaUnavailableError):
        worker.transcribe("rec-1")


def test_wo063_07b_path_escape_is_media_unavailable(archive_root):
    # A persisted path that escapes the archive root is refused (no leak).
    escaping = os.path.join(archive_root, "..", "..", "etc", "passwd")
    access = _make_access(archive_root, _recording_metadata(escaping, "a" * 64))
    worker = _worker(_FakeSttTranscriber(), access.resolve)
    with pytest.raises(RecordingMediaUnavailableError):
        worker.transcribe("rec-1")


# --------------------------------------------------------------------------- #
# Case 8 — unreadable media
# --------------------------------------------------------------------------- #


def test_wo063_08_unreadable_media(archive_root):
    # A resolver returns an artifact whose file is not a usable WAV.
    bad = os.path.join(archive_root, "radio", "bad.wav")
    os.makedirs(os.path.dirname(bad), exist_ok=True)
    with open(bad, "wb") as fh:
        fh.write(b"not-a-wav" * 100)
    artifact = _recording_metadata(bad, _sha256_file(bad))

    def resolver(rid):
        from app.operator.recording_access import RecordingArtifact

        return RecordingArtifact(
            recording_id=rid,
            path=os.path.realpath(bad),
            size=os.path.getsize(bad),
            sha256=_sha256_file(bad),
            mime_type="audio/wav",
        )

    worker = _worker(_FakeSttTranscriber(text="ok"), resolver)
    with pytest.raises(RecordingMediaUnreadableError):
        worker.transcribe("rec-1")


# --------------------------------------------------------------------------- #
# Case 9 — STT failure
# --------------------------------------------------------------------------- #


def test_wo063_09_stt_failure(archive_root):
    wav, pcm = _write_wav(os.path.join(archive_root, "radio"), name="rec-1")
    sha = _sha256_file(wav)
    access = _make_access(archive_root, _recording_metadata(wav, sha))
    fail_key = hashlib.sha256(pcm).hexdigest()
    fake = _FakeSttTranscriber(text="ok", fail_for={fail_key})
    worker = _worker(fake, access.resolve)
    with pytest.raises(SttExecutionFailedError):
        worker.transcribe("rec-1")
    assert worker.failures == 1


def test_wo063_09b_not_ready_transcriber_fails_closed(archive_root):
    wav, _ = _write_wav(os.path.join(archive_root, "radio"), name="rec-1")
    sha = _sha256_file(wav)
    access = _make_access(archive_root, _recording_metadata(wav, sha))
    fake = _FakeSttTranscriber(text="ok", ready=False)
    worker = _worker(fake, access.resolve)
    with pytest.raises(SttExecutionFailedError):
        worker.transcribe("rec-1")
    # No silent fallback: transcribe() was never called.
    assert fake.transcribe_calls == []


def test_wo063_09c_no_engine_fail_closed(archive_root):
    wav, _ = _write_wav(os.path.join(archive_root, "radio"), name="rec-1")
    sha = _sha256_file(wav)
    access = _make_access(archive_root, _recording_metadata(wav, sha))
    worker = _worker(None, access.resolve)
    assert worker.available is False
    assert worker.state == "UNAVAILABLE"
    with pytest.raises(SttExecutionFailedError):
        worker.transcribe("rec-1")
    assert worker.failures == 1


# --------------------------------------------------------------------------- #
# Case 10 — valid recording with no speech (empty transcript = success)
# --------------------------------------------------------------------------- #


def test_wo063_10_empty_transcript_is_success(archive_root):
    wav, pcm = _write_wav(os.path.join(archive_root, "radio"), name="rec-1")
    sha = _sha256_file(wav)
    access = _make_access(archive_root, _recording_metadata(wav, sha))
    empty_key = hashlib.sha256(pcm).hexdigest()
    emitted: list[dict] = []
    fake = _FakeSttTranscriber(text="unused", empty_for={empty_key})
    worker = _worker(fake, access.resolve, on_transcript=emitted.append)

    result = worker.transcribe("rec-1")

    # No speech is a SUCCESSFUL STT execution, not a failure.
    assert result.text == ""
    assert result.raw["transcript"]["text"] == ""
    assert len(emitted) == 1
    assert worker.failures == 0


# --------------------------------------------------------------------------- #
# Idempotency
# --------------------------------------------------------------------------- #


def test_wo063_idempotent_same_contract_no_rerun(archive_root):
    wav, _ = _write_wav(os.path.join(archive_root, "radio"), name="rec-1")
    sha = _sha256_file(wav)
    access = _make_access(archive_root, _recording_metadata(wav, sha))
    fake = _FakeSttTranscriber(text="прийом")
    worker = _worker(fake, access.resolve)

    r1 = worker.transcribe("rec-1")
    r2 = worker.transcribe("rec-1")

    # Same recording + same STT contract -> same logical result, no re-run.
    assert r1.raw == r2.raw
    assert len(fake.transcribe_calls) == 1
    assert worker.has_result("rec-1") is True


def test_wo063_idempotent_different_contract_runs_again(archive_root):
    wav, _ = _write_wav(os.path.join(archive_root, "radio"), name="rec-1")
    sha = _sha256_file(wav)
    access = _make_access(archive_root, _recording_metadata(wav, sha))
    fake = _FakeSttTranscriber(text="прийом")
    worker = _worker(fake, access.resolve)

    worker.transcribe("rec-1")
    # A different engine contract is a different logical result.
    worker._engine = "different-engine"
    worker.transcribe("rec-1")
    assert len(fake.transcribe_calls) == 2


# --------------------------------------------------------------------------- #
# Read-only source + no-path leak
# --------------------------------------------------------------------------- #


def test_wo063_read_only_artifact_unchanged(archive_root):
    wav, _ = _write_wav(os.path.join(archive_root, "radio"), name="rec-1")
    sha = _sha256_file(wav)
    access = _make_access(archive_root, _recording_metadata(wav, sha))
    before = open(wav, "rb").read()
    before_size = os.path.getsize(wav)
    before_mtime = os.path.getmtime(wav)
    worker = _worker(_FakeSttTranscriber(text="ok"), access.resolve)
    worker.transcribe("rec-1")
    after = open(wav, "rb").read()
    assert after == before
    assert os.path.getsize(wav) == before_size
    assert os.path.getmtime(wav) == before_mtime
    assert os.path.exists(wav)


def test_wo063_no_path_leak_in_errors(archive_root):
    wav, _ = _write_wav(os.path.join(archive_root, "radio"), name="rec-1")
    sha = _sha256_file(wav)
    access = _make_access(archive_root, _recording_metadata(wav, sha))

    # Collect a representative set of worker failures and assert none of them
    # leaks the archive root or the media path.
    cases: list[RecordingSttWorker] = []

    # Missing recording (identity does not resolve).
    access_none = _make_access(archive_root, None)
    cases.append(_worker(_FakeSttTranscriber(), access_none.resolve))

    # Missing media artifact (path not exposed).
    missing = os.path.join(archive_root, "radio", "gone.wav")
    access2 = _make_access(archive_root, _recording_metadata(missing, "a" * 64))
    cases.append(_worker(_FakeSttTranscriber(), access2.resolve))

    # Integrity violation.
    access3 = _make_access(archive_root, _recording_metadata(wav, "0" * 64))
    cases.append(_worker(_FakeSttTranscriber(), access3.resolve))

    for worker in cases:
        try:
            worker.transcribe("rec-1")
        except RecordingSttError as exc:
            msg = str(exc)
            assert archive_root not in msg, f"path leaked: {msg!r}"
            assert "wav" not in msg.lower(), f"path leaked: {msg!r}"
            assert os.path.basename(wav) not in msg, f"path leaked: {msg!r}"
        else:
            raise AssertionError("expected a RecordingSttError")


def test_wo063_no_path_leak_in_result(archive_root):
    wav, _ = _write_wav(os.path.join(archive_root, "radio"), name="rec-1")
    sha = _sha256_file(wav)
    access = _make_access(archive_root, _recording_metadata(wav, sha))
    worker = _worker(_FakeSttTranscriber(text="ok"), access.resolve)
    result = worker.transcribe("rec-1")
    # The result carries the canonical identity, not a filesystem path.
    assert result.audio_recording_id == "rec-1"
    assert result.wav_sha256 == sha
    assert archive_root not in str(result.raw)
    assert "wav" not in result.raw["transcript"]["text"]


# --------------------------------------------------------------------------- #
# Deterministic content identity
# --------------------------------------------------------------------------- #


def test_wo063_deterministic_content_id_distinct_from_recording(archive_root):
    wav, _ = _write_wav(os.path.join(archive_root, "radio"), name="rec-1")
    sha = _sha256_file(wav)
    access = _make_access(archive_root, _recording_metadata(wav, sha))
    from app.event_sources.identity.event_identity import EventIdentityResolver

    resolver = EventIdentityResolver()
    worker = _worker(_FakeSttTranscriber(text="ok"), access.resolve)
    result = worker.transcribe("rec-1")
    recording_id = resolver.resolve({"content_id": "rec-1"}, "radio")
    transcript_id = resolver.resolve(result.raw, "radio")
    assert recording_id is not None
    assert transcript_id is not None
    assert recording_id != transcript_id
    # Deterministic and idempotent.
    assert resolver.resolve(result.raw, "radio") == transcript_id
