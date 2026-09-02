"""WO-038 tests — Audio pipeline components (framing, decode, STT, callsign).

Unit-level tests for the WO-038 components.  These do NOT mock away the vertical
path; they exercise the real framing codec, the real ffmpeg decode, the STT seam
(DeterministicTestTranscriber), the deterministic callsign detector, and the
audio-to-canonical-event conversion.  The full integrated path (multicast ->
durable -> operator) is covered separately in test_wo038_multicast_e2e.py.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from datetime import datetime, timezone

import pytest
from app.audio.audio_config import AudioConfig
from app.audio.audio_segment import AudioSegment, decode_frame, encode_frame
from app.audio.callsign import CallsignDetector
from app.audio.decoder import AudioDecoder
from app.audio.orchestrator import segment_to_raw
from app.audio.transcriber import DeterministicTestTranscriber, TranscriptResult
from app.database.session import DatabaseSessionManager
from app.event.event import Event
from app.event_repository.durable.sqlalchemy_event_repository import (
    SQLAlchemyEventRepository,
)
from app.event_sources.factory.event_factory import EventFactory
from app.event_sources.identity.event_identity import (
    EventIdentityResolver,
)

PHRASE = "Буревій-2, прийом. Виходжу на позицію."
CONTENT_ID = "bureviy-2"
CALLSIGN = "Буревій-2"


def _cfg(**overrides) -> AudioConfig:
    return AudioConfig(multicast_address="239.255.0.1", multicast_port=50000, codec="wav", source_name="radio", **overrides)


# -- framing -----------------------------------------------------------------


def test_frame_round_trip() -> None:
    occ = datetime(2026, 9, 2, 10, 31, 4, tzinfo=timezone.utc)
    frame = encode_frame(b"\x00\x01\x02\x03", content_id=CONTENT_ID, occurred_at=occ, metadata={"chan": "A"})
    seg = decode_frame(frame)
    assert seg.content_id == CONTENT_ID
    assert seg.occurred_at == occ
    assert seg.audio_bytes == b"\x00\x01\x02\x03"
    assert seg.metadata == {"chan": "A"}


def test_frame_no_occurred_at_uses_receive_time() -> None:
    seg = decode_frame(encode_frame(b"abc", content_id="x"))
    assert seg.occurred_at is not None
    assert seg.occurred_at.tzinfo is not None


@pytest.mark.parametrize(
    "bad",
    [
        b"",                      # empty
        b"XXXX",                  # bad magic
        b"TCA1",                  # truncated header
        b"TCA1\x00\x00\x00\xff" + b"{" * 10,  # truncated header JSON
    ],
)
def test_frame_malformed_raises(bad: bytes) -> None:
    with pytest.raises(ValueError):
        decode_frame(bad)


# -- decoder -----------------------------------------------------------------


def test_decoder_decodes_wav_to_pcm() -> None:
    wav = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
         "-i", "sine=frequency=440:duration=0.2", "-ar", "16000", "-ac", "1",
         "-f", "wav", "pipe:1"],
        capture_output=True,
        check=False,
    ).stdout
    assert wav
    decoder = AudioDecoder(sample_rate=16000, channels=1)
    pcm = decoder.decode_segment(wav, "wav")
    assert len(pcm) > 0
    assert len(pcm) == 16000 * 2 * 1 * 0.2  # s16le mono at 16kHz for 0.2s


def test_decoder_malformed_returns_empty() -> None:
    decoder = AudioDecoder(sample_rate=16000, channels=1)
    assert decoder.decode_segment(b"not-audio", "wav") == b""
    assert decoder.decode(b"not-audio") == b""


# -- transcriber -------------------------------------------------------------


def test_transcriber_interface_returns_deterministic_text() -> None:
    tr = DeterministicTestTranscriber(phrase_map={CONTENT_ID: PHRASE}, default_text="(none)")
    # Interface method: deterministic via content resolver (hash of bytes).
    result = tr.transcribe(b"some-audio-bytes")
    assert isinstance(result, str)
    # Same input -> same output (determinism).
    assert result == tr.transcribe(b"some-audio-bytes")
    assert tr.model == "deterministic-test"
    assert tr.is_ready() is True


def test_transcriber_detailed_uses_content_id() -> None:
    tr = DeterministicTestTranscriber(phrase_map={CONTENT_ID: PHRASE}, default_text="(none)", language="uk")
    occ = datetime(2026, 9, 2, 10, 31, 4, tzinfo=timezone.utc)
    res = tr.transcribe_detailed(CONTENT_ID, b"pcm-bytes", occurred_at=occ, sample_rate=16000, channels=1)
    assert isinstance(res, TranscriptResult)
    assert res.text == PHRASE
    assert res.occurred_at == occ
    assert res.confidence == 1.0
    assert res.language == "uk"
    assert res.metadata["engine"] == "deterministic-test"
    assert res.metadata["content_id"] == CONTENT_ID


# -- callsign ----------------------------------------------------------------


def test_callsign_configured_detection_preserves_text() -> None:
    det = CallsignDetector(callsigns=[CALLSIGN])
    res = det.detect(PHRASE)
    assert res.text == PHRASE
    assert res.detected_callsigns == [CALLSIGN]
    assert res.detection_method == "configured-callsigns"
    assert res.confidence == 1.0


def test_callsign_pattern_detection() -> None:
    det = CallsignDetector(patterns=[r"[^\W\d_]+-\d+"])
    res = det.detect("Буревій-2, прийом. Виходжу на позицію.")
    assert res.detected_callsigns == ["Буревій-2"]
    assert res.detection_method == "configured-pattern"


def test_callsign_heuristic_detection() -> None:
    det = CallsignDetector()
    res = det.detect("Говорить Сокіл-1, прийом.")
    assert "Сокіл-1" in res.detected_callsigns
    assert res.detection_method == "heuristic"
    assert res.text == "Говорить Сокіл-1, прийом."


def test_callsign_no_match() -> None:
    det = CallsignDetector(callsigns=["Alpha-1"])
    res = det.detect("просто текст без позивного")
    assert res.detected_callsigns == []
    assert res.detection_method == "none"


# -- identity ----------------------------------------------------------------


def test_radio_content_id_identity_is_deterministic() -> None:
    raw = {"content_id": CONTENT_ID, "transcript": PHRASE, "timestamp": "2026-09-02T10:31:04+00:00"}
    resolver = EventIdentityResolver()
    id1 = resolver.resolve(raw, "radio")
    id2 = resolver.resolve(raw, "radio")
    assert id1 == id2
    assert id1 is not None and len(id1) == 36


def test_radio_content_id_identity_differs_across_content() -> None:
    resolver = EventIdentityResolver()
    a = resolver.resolve({"content_id": "msg-a"}, "radio")
    b = resolver.resolve({"content_id": "msg-b"}, "radio")
    assert a != b


def test_radio_legacy_frequency_callsign_backward_compatible() -> None:
    # Legacy RadioPayloadNormalizer raw dicts (no content_id) still resolve via
    # the frequency+callsign fallback.
    resolver = EventIdentityResolver()
    legacy = {"frequency": "145.500", "callsign": "Alpha-1"}
    ident = resolver.resolve(legacy, "radio")
    assert ident is not None and len(ident) == 36


def test_unknown_source_non_deduplicable() -> None:
    resolver = EventIdentityResolver()
    assert resolver.resolve({"content_id": "x"}, "unknown-source") is None


# -- segment_to_raw ----------------------------------------------------------


def test_segment_to_raw_round_trip() -> None:
    cfg = _cfg()
    decoder = AudioDecoder(sample_rate=16000, channels=1)
    tr = DeterministicTestTranscriber(phrase_map={CONTENT_ID: PHRASE}, default_text="")
    det = CallsignDetector(callsigns=[CALLSIGN])
    occ = datetime(2026, 9, 2, 10, 31, 4, tzinfo=timezone.utc)
    seg = AudioSegment(content_id=CONTENT_ID, audio_bytes=b"pcm", occurred_at=occ, received_at=occ)
    raw = segment_to_raw(seg, cfg, decoder, tr, det)
    assert raw["transcript"] == PHRASE
    assert raw["detected_callsigns"] == [CALLSIGN]
    assert raw["content_id"] == CONTENT_ID
    assert raw["timestamp"] == occ.isoformat()
    assert raw["occurred_at"] == occ.isoformat()
    assert raw["callsign"] == CALLSIGN


# -- orchestrator process_segment (real durable repo) ------------------------


@pytest.fixture()
def repo():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    sm = DatabaseSessionManager(database_url=f"sqlite:///{path}", echo=False)
    sm.initialize()
    r = SQLAlchemyEventRepository(session_manager=sm)
    r.initialize()
    yield r
    sm.close()
    if os.path.exists(path):
        os.remove(path)


def test_process_segment_persists_canonical_event(repo) -> None:
    from app.audio.orchestrator import AudioEventOrchestrator

    cfg = _cfg()
    factory = EventFactory(identity_resolver=EventIdentityResolver())
    orch = AudioEventOrchestrator(
        cfg,
        factory,
        repo,
        transcriber=DeterministicTestTranscriber(phrase_map={CONTENT_ID: PHRASE}),
        callsign_detector=CallsignDetector(callsigns=[CALLSIGN]),
    )
    occ = datetime(2026, 9, 2, 10, 31, 4, tzinfo=timezone.utc)
    seg = AudioSegment(content_id=CONTENT_ID, audio_bytes=b"pcm", occurred_at=occ, received_at=occ)
    event = orch.process_segment(seg)
    assert isinstance(event, Event)
    assert event.source == "radio"
    assert event.timestamp == occ  # occurred_at preserved, not ingestion time
    assert repo.exists(event.event_id)
    restored = repo.get(event.event_id)
    assert restored.payload["transcript"] == PHRASE
    assert restored.payload["detected_callsigns"] == [CALLSIGN]
