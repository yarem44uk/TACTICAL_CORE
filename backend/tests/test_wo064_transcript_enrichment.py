"""WO-064 — Transcript enrichment / callsign detection.

Proves the real architectural seam:

    Transcript Evidence
            |
            v
        Enrichment Engine (deterministic)
            |
            v
        Enrichment Result (DERIVED evidence)

Invariants proven here:
  * deterministic: the same transcript evidence yields the same enrichment.
  * DERIVED, never a replacement: the original recording, recording identity
    (``audio_recording_id``), WAV SHA-256, transcript identity
    (``<rid>|transcript``) and transcript text are all preserved verbatim and
    never mutated.
  * distinct derived identity: the enrichment ``content_id``
    (``<rid>|transcript|enrichment``) is distinct from both the recording and
    the transcript identities (verified via EventIdentityResolver).
  * no fabrication: a transcript without a callsign yields an empty
    ``detected_callsigns`` list and no ``callsign`` key.
  * WO-038 callsign contract preserved at the top level of the enriched raw
    dict (``detected_callsigns`` / ``confidence`` / ``detection_method`` /
    ``callsign``).
  * input is never mutated (deep equality before/after enrich).

No production data is used.
"""

from __future__ import annotations

import copy
from typing import Any

import pytest

from app.audio.callsign import CallsignDetector
from app.audio.transcript_enrichment import (
    EnrichmentResult,
    TranscriptEnrichmentEngine,
    TranscriptEvidenceInvalidError,
)
from app.event_sources.identity.event_identity import EventIdentityResolver


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _transcript_raw(
    *,
    audio_recording_id: str = "rec-1",
    text: str = "прийом Буревій-2, слідую",
    wav_sha256: str = "a" * 64,
    language: str | None = "uk",
    engine: str = "fake-stt",
    model: str = "fake-stt",
) -> dict[str, Any]:
    """A transcript-evidence raw dict shaped like ``build_transcript_raw`` output."""
    return {
        "timestamp": "2026-01-01T00:00:00+00:00",
        "occurred_at": "2026-01-01T00:00:00+00:00",
        "audio_recording_id": audio_recording_id,
        "content_id": f"{audio_recording_id}|transcript",
        "correlation_id": audio_recording_id,
        "source": "radio",
        "transcript": {
            "text": text,
            "language": language,
            "engine": engine,
            "model": model,
            "audio_recording_id": audio_recording_id,
            "processed_at": "2026-01-01T00:00:01+00:00",
            "processing_ms": 12.3,
            "wav_sha256": wav_sha256,
        },
    }


# --------------------------------------------------------------------------- #
# Case 1 — deterministic callsign detection
# --------------------------------------------------------------------------- #


def test_wo064_01_detects_callsign_deterministic() -> None:
    engine = TranscriptEnrichmentEngine()
    raw = _transcript_raw(text="Буревій-2, виходимо на зв'язок")
    result = engine.enrich(raw)

    assert isinstance(result, EnrichmentResult)
    assert result.audio_recording_id == "rec-1"
    assert result.transcript_text == "Буревій-2, виходимо на зв'язок"
    # WO-038 heuristic: `<letters>-<digits>`.
    assert "Буревій-2" in result.detected_callsigns
    assert result.callsign == "Буревій-2"
    assert result.confidence == 0.7  # heuristic confidence
    assert result.detection_method == "heuristic"


# --------------------------------------------------------------------------- #
# Case 2 — original identities preserved verbatim
# --------------------------------------------------------------------------- #


def test_wo064_02_preserves_original_identities() -> None:
    sha = "f" * 64
    engine = TranscriptEnrichmentEngine()
    raw = _transcript_raw(text="Сокіл-1 прийом", wav_sha256=sha)
    result = engine.enrich(raw)

    assert result.audio_recording_id == "rec-1"
    assert result.transcript_content_id == "rec-1|transcript"
    assert result.wav_sha256 == sha
    assert result.transcript_text == "Сокіл-1 прийом"
    # The enriched raw preserves the transcript block verbatim.
    assert result.raw["transcript"]["text"] == "Сокіл-1 прийом"
    assert result.raw["transcript"]["wav_sha256"] == sha
    assert result.raw["transcript"]["audio_recording_id"] == "rec-1"
    assert result.raw["audio_recording_id"] == "rec-1"


# --------------------------------------------------------------------------- #
# Case 3 — distinct derived enrichment identity
# --------------------------------------------------------------------------- #


def test_wo064_03_derived_identity_distinct_from_recording_and_transcript() -> None:
    engine = TranscriptEnrichmentEngine()
    resolver = EventIdentityResolver()

    raw = _transcript_raw(text="Буревій-2")
    result = engine.enrich(raw)

    # Enrichment identity is distinct and deterministic.
    assert result.content_id == "rec-1|transcript|enrichment"

    recording_id = resolver.resolve({"content_id": "rec-1"}, "radio")
    transcript_id = resolver.resolve({"content_id": "rec-1|transcript"}, "radio")
    enrichment_id = resolver.resolve(result.raw, "radio")

    assert recording_id is not None
    assert transcript_id is not None
    assert enrichment_id is not None
    assert recording_id != transcript_id
    assert transcript_id != enrichment_id
    assert recording_id != enrichment_id
    # Deterministic: resolving the enriched raw again gives the same id.
    assert resolver.resolve(result.raw, "radio") == enrichment_id


# --------------------------------------------------------------------------- #
# Case 4 — no callsign: no fabrication
# --------------------------------------------------------------------------- #


def test_wo064_04_no_callsign_no_fabrication() -> None:
    engine = TranscriptEnrichmentEngine()
    raw = _transcript_raw(text="просто звичайна розмова без позивних")
    result = engine.enrich(raw)

    assert result.detected_callsigns == []
    assert result.callsign is None
    assert result.detection_method == "none"
    assert result.confidence == 0.0
    # No primary callsign key is fabricated in the raw dict.
    assert "callsign" not in result.raw
    assert "callsign" not in result.raw["enrichment"]


# --------------------------------------------------------------------------- #
# Case 5 — input never mutated
# --------------------------------------------------------------------------- #


def test_wo064_05_input_never_mutated() -> None:
    engine = TranscriptEnrichmentEngine()
    raw = _transcript_raw(text="Буревій-2 прийом")
    before = copy.deepcopy(raw)
    engine.enrich(raw)
    assert raw == before
    assert raw["transcript"]["text"] == "Буревій-2 прийом"
    assert "enrichment" not in raw


# --------------------------------------------------------------------------- #
# Case 6 — configured detector honored
# --------------------------------------------------------------------------- #


def test_wo064_06_configured_detector_honored() -> None:
    detector = CallsignDetector(callsigns=["АЛЬФА-1"], confidence=1.0)
    engine = TranscriptEnrichmentEngine(detector=detector)
    raw = _transcript_raw(text="АЛЬФА-1 на зв'язку")
    result = engine.enrich(raw)

    assert result.detected_callsigns == ["АЛЬФА-1"]
    assert result.callsign == "АЛЬФА-1"
    assert result.detection_method == "configured-callsigns"
    assert result.confidence == 1.0
    # The detector is observable on the engine.
    assert engine.detector is detector


# --------------------------------------------------------------------------- #
# Case 7 — invalid evidence
# --------------------------------------------------------------------------- #


def test_wo064_07_invalid_evidence() -> None:
    engine = TranscriptEnrichmentEngine()
    with pytest.raises(TranscriptEvidenceInvalidError):
        engine.enrich("not-a-dict")  # type: ignore[arg-type]
    with pytest.raises(TranscriptEvidenceInvalidError):
        engine.enrich({})
    with pytest.raises(TranscriptEvidenceInvalidError):
        engine.enrich({"audio_recording_id": "rec-1"})
    with pytest.raises(TranscriptEvidenceInvalidError):
        engine.enrich({"audio_recording_id": "rec-1", "transcript": {}})
    with pytest.raises(TranscriptEvidenceInvalidError):
        engine.enrich(_transcript_raw(audio_recording_id="   "))
    # A transcript whose text is None is invalid (no usable text).
    bad = _transcript_raw()
    bad["transcript"]["text"] = None
    with pytest.raises(TranscriptEvidenceInvalidError):
        engine.enrich(bad)


# --------------------------------------------------------------------------- #
# Case 8 — deterministic / idempotent
# --------------------------------------------------------------------------- #


def test_wo064_08_deterministic_idempotent() -> None:
    engine = TranscriptEnrichmentEngine()
    raw = _transcript_raw(text="Буревій-2 та Сокіл-1 прийом")
    r1 = engine.enrich(raw)
    r2 = engine.enrich(raw)
    assert r1 == r2
    assert r1.raw == r2.raw


# --------------------------------------------------------------------------- #
# Case 9 — empty transcript text is a valid enrichment (no speech)
# --------------------------------------------------------------------------- #


def test_wo064_09_empty_text_is_valid() -> None:
    engine = TranscriptEnrichmentEngine()
    raw = _transcript_raw(text="")
    result = engine.enrich(raw)
    assert result.transcript_text == ""
    assert result.detected_callsigns == []
    assert result.callsign is None
    assert result.detection_method == "none"
    assert result.confidence == 0.0


# --------------------------------------------------------------------------- #
# Case 10 — WO-038 callsign contract preserved at the top level
# --------------------------------------------------------------------------- #


def test_wo064_10_wo038_contract_fields_preserved() -> None:
    engine = TranscriptEnrichmentEngine()
    raw = _transcript_raw(text="Буревій-2")
    result = engine.enrich(raw)
    enriched = result.raw

    assert enriched["detected_callsigns"] == ["Буревій-2"]
    assert enriched["confidence"] == 0.7
    assert enriched["detection_method"] == "heuristic"
    assert enriched["callsign"] == "Буревій-2"
    # Derived layer present and labelled.
    assert enriched["enrichment"]["content_id"] == "rec-1|transcript|enrichment"
    assert enriched["enrichment"]["detected_callsigns"] == ["Буревій-2"]


# --------------------------------------------------------------------------- #
# Case 11 — to_dict is serialisable and preserves everything
# --------------------------------------------------------------------------- #


def test_wo064_11_to_dict_serialisable() -> None:
    engine = TranscriptEnrichmentEngine()
    raw = _transcript_raw(text="Буревій-2")
    result = engine.enrich(raw)
    d = result.to_dict()
    assert d["audio_recording_id"] == "rec-1"
    assert d["transcript_content_id"] == "rec-1|transcript"
    assert d["content_id"] == "rec-1|transcript|enrichment"
    assert d["transcript_text"] == "Буревій-2"
    assert d["detected_callsigns"] == ["Буревій-2"]
    assert d["raw"]["transcript"]["text"] == "Буревій-2"
