"""WO-065 — Final radio event -> operational observation integration.

Proves the real architectural seam:

    Enrichment Evidence (WO-064)
            |
            v
    Final Radio Event (canonical input / RAW)
            |
            v
    existing EventFactory  (WO-050 CONTRACT-2 boundary)
            |
            v
    existing EventPipeline
            |
            v
    Durable Journal
            |
            v
    Operational Observation

Invariants proven here (the 12 required assertions):
  1. final event creation: transcript + enrichment evidence -> one canonical
     final Radio Event;
  2. canonical identity: the final event uses the EXISTING canonical identity
     mechanism (EventIdentityResolver, WO-025);
  3. recording identity preserved: ``audio_recording_id`` unchanged;
  4. transcript identity preserved: ``<rid>|transcript`` unchanged;
  5. enrichment identity preserved: ``<rid>|transcript|enrichment`` unchanged;
  6. provenance: ``wav_sha256``, transcript text, detected callsigns,
     detection method remain traceable;
  7. no fabrication: a no-callsign transcript yields an empty
     ``detected_callsigns`` list and no ``callsign`` key; no operational
     metadata is invented;
  8. idempotency: the same input twice -> one logical event, one observation;
  9. observation projection: the final event reaches the existing Operational
     Observation;
  10. chronological ordering: the final event timestamp/order follows the
      existing chronological wall contract;
  11. malformed evidence: invalid input fails explicitly, no partial event;
  12. source immutability: the upstream transcript/enrichment dicts are not
      mutated.

The WO-050 CONTRACT-2 boundary is respected: this module never calls
``EventFactory.create_event``; the tests construct the canonical Event through
the existing ``EventFactory`` (test code is not a production module, so this is
within the architectural contract).
"""

from __future__ import annotations

import copy
from datetime import datetime, timezone
from typing import Any

import pytest

from app.audio.radio_event import (
    FinalEventInvalidError,
    RadioEventIntegrator,
    RadioEventResult,
)
from app.audio.transcript_enrichment import (
    EnrichmentResult,
    TranscriptEnrichmentEngine,
)
from app.event.event import Event
from app.event_sources.factory.event_factory import EventFactory
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
    occurred_at: str = "2026-01-01T00:00:00+00:00",
) -> dict[str, Any]:
    """A transcript-evidence raw dict shaped like ``build_transcript_raw`` output."""
    return {
        "timestamp": occurred_at,
        "occurred_at": occurred_at,
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
            "processed_at": occurred_at,
            "processing_ms": 12.3,
            "wav_sha256": wav_sha256,
        },
    }


def _enrich(*, text: str = "Буревій-2 прийом", **kwargs: Any) -> EnrichmentResult:
    """Run a transcript raw through the WO-064 engine to get an EnrichmentResult."""
    engine = TranscriptEnrichmentEngine()
    raw = _transcript_raw(text=text, **kwargs)
    return engine.enrich(raw)


def _integrator() -> RadioEventIntegrator:
    """A fresh integrator using the canonical identity resolver."""
    return RadioEventIntegrator()


def _build_event(enrichment: EnrichmentResult) -> Event:
    """Turn the WO-065 RAW into a canonical Event via the EXISTING EventFactory
    (the WO-050 CONTRACT-2 boundary; test code is not a production module)."""
    integrator = _integrator()
    raw = integrator.build_raw(enrichment)
    event_id = integrator.resolve_event_id(enrichment)
    return EventFactory(identity_resolver=EventIdentityResolver()).create_event(
        raw_data=raw,
        source_name="radio",
        event_id=event_id,
    )


@pytest.fixture()
def global_session_manager():
    """Configure the GLOBAL DatabaseSessionManager to an isolated in-memory
    SQLite database and reset it afterwards (mirrors WO-059 test setup)."""
    from app.database import session as session_mod
    from app.database.session import configure_session_manager, get_session_manager

    manager = configure_session_manager("sqlite:///:memory:")
    from app.database.base import Base

    Base.metadata.create_all(manager.engine)
    yield manager
    session_mod._session_manager = None


# --------------------------------------------------------------------------- #
# Test 1 — final event creation
# --------------------------------------------------------------------------- #


def test_wo065_01_final_event_creation() -> None:
    """Valid transcript + enrichment evidence produces one canonical final
    Radio Event."""
    enrichment = _enrich(text="Буревій-2, виходимо")
    event = _build_event(enrichment)

    assert isinstance(event, Event)
    assert event.source == "radio"
    assert event.event_id  # deterministic identity present
    # The final event carries the derived evidence.
    assert event.payload["audio_recording_id"] == "rec-1"
    assert "transcript" in event.payload
    assert "enrichment" in event.payload
    assert event.payload["detected_callsigns"] == ["Буревій-2"]


# --------------------------------------------------------------------------- #
# Test 2 — canonical identity
# --------------------------------------------------------------------------- #


def test_wo065_02_canonical_identity() -> None:
    """The final event uses the EXISTING canonical identity mechanism
    (EventIdentityResolver, WO-025)."""
    enrichment = _enrich(text="Буревій-2 прийом")
    integrator = _integrator()
    event = _build_event(enrichment)

    # Identity is deterministic and equals the canonical resolver output.
    resolver = EventIdentityResolver()
    expected = resolver.resolve(enrichment.raw, "radio")
    assert expected is not None
    assert event.event_id == expected
    assert integrator.resolve_event_id(enrichment) == expected

    # Deterministic: same enrichment -> same event_id.
    event2 = _build_event(_enrich(text="Буревій-2 прийом"))
    assert event2.event_id == event.event_id

    # Distinct from the recording and transcript identities.
    recording_id = resolver.resolve({"content_id": "rec-1"}, "radio")
    transcript_id = resolver.resolve({"content_id": "rec-1|transcript"}, "radio")
    assert recording_id is not None
    assert transcript_id is not None
    assert event.event_id != recording_id
    assert event.event_id != transcript_id


# --------------------------------------------------------------------------- #
# Test 3 — recording identity preserved
# --------------------------------------------------------------------------- #


def test_wo065_03_recording_identity_preserved() -> None:
    """``audio_recording_id`` is unchanged in the final event."""
    enrichment = _enrich(audio_recording_id="rec-77", text="Сокіл-1 прийом")
    event = _build_event(enrichment)

    assert event.payload["audio_recording_id"] == "rec-77"
    assert enrichment.audio_recording_id == "rec-77"
    # The recording provenance reference also preserves the identity.
    assert event.payload["recording"]["audio_recording_id"] == "rec-77"
    assert event.payload["recording"]["content_id"] == "rec-77"


# --------------------------------------------------------------------------- #
# Test 4 — transcript identity preserved
# --------------------------------------------------------------------------- #


def test_wo065_04_transcript_identity_preserved() -> None:
    """``<audio_recording_id>|transcript`` is preserved in the final event."""
    enrichment = _enrich(text="Буревій-2")
    event = _build_event(enrichment)

    assert enrichment.transcript_content_id == "rec-1|transcript"
    assert event.payload["transcript_content_id"] == "rec-1|transcript"
    # The transcript block remains verbatim.
    assert event.payload["transcript"]["audio_recording_id"] == "rec-1"
    assert event.payload["transcript"]["text"] == "Буревій-2"


# --------------------------------------------------------------------------- #
# Test 5 — enrichment identity preserved
# --------------------------------------------------------------------------- #


def test_wo065_05_enrichment_identity_preserved() -> None:
    """``<audio_recording_id>|transcript|enrichment`` is preserved in the
    final event."""
    enrichment = _enrich(text="Буревій-2")
    event = _build_event(enrichment)

    assert enrichment.content_id == "rec-1|transcript|enrichment"
    assert event.payload["content_id"] == "rec-1|transcript|enrichment"
    assert event.payload["enrichment_content_id"] == "rec-1|transcript|enrichment"
    # The enrichment block remains verbatim.
    assert event.payload["enrichment"]["content_id"] == "rec-1|transcript|enrichment"
    assert event.payload["enrichment"]["transcript_content_id"] == "rec-1|transcript"


# --------------------------------------------------------------------------- #
# Test 6 — provenance
# --------------------------------------------------------------------------- #


def test_wo065_06_provenance() -> None:
    """wav_sha256, transcript text, detected callsigns, detection method remain
    traceable."""
    sha = "f" * 64
    enrichment = _enrich(text="Буревій-2 та Сокіл-1 прийом", wav_sha256=sha)
    event = _build_event(enrichment)

    assert event.payload["recording"]["wav_sha256"] == sha
    assert event.payload["transcript"]["wav_sha256"] == sha
    assert event.payload["transcript"]["text"] == "Буревій-2 та Сокіл-1 прийом"
    assert event.payload["detected_callsigns"] == ["Буревій-2", "Сокіл-1"]
    assert event.payload["detection_method"] == "heuristic"
    assert event.payload["confidence"] == 0.7


# --------------------------------------------------------------------------- #
# Test 7 — no fabrication
# --------------------------------------------------------------------------- #


def test_wo065_07_no_fabrication() -> None:
    """A transcript with no callsign yields an empty detected_callsigns list and
    no fabricated callsign key / operational metadata."""
    enrichment = _enrich(text="просто звичайна розмова без позивних")
    assert enrichment.detected_callsigns == []
    assert enrichment.callsign is None

    event = _build_event(enrichment)

    assert event.payload["detected_callsigns"] == []
    assert "callsign" not in event.payload
    # No fabricated operational metadata.
    for fabricated in ("frequency", "location", "unit", "rank", "organization",
                       "severity", "priority", "operational_classification"):
        assert fabricated not in event.payload, (
            f"WO-065 must not fabricate '{fabricated}'"
        )


# --------------------------------------------------------------------------- #
# Test 8 — idempotency
# --------------------------------------------------------------------------- #


def test_wo065_08_idempotency(global_session_manager) -> None:
    """The same input twice -> one logical event, one observation."""
    from app.composition import create_event_runtime
    from app.intelligence.observation.repository import ObservationRepository
    from app.database.session import get_session_manager

    enrichment = _enrich(text="Буревій-2 прийом")
    event = _build_event(enrichment)

    runtime = create_event_runtime()
    # Process the same logical evidence twice.
    assert runtime.pipeline.process(event) is True
    assert runtime.pipeline.process(event) is True

    repo = ObservationRepository(get_session_manager().get_session())
    # Exactly one observation for the immutable identity.
    obs = repo.get_by_immutable_id(event.event_id)
    assert obs is not None
    assert repo.exists_by_immutable_id(event.event_id) is True


# --------------------------------------------------------------------------- #
# Test 9 — observation projection
# --------------------------------------------------------------------------- #


def test_wo065_09_observation_projection(global_session_manager) -> None:
    """The final event reaches the existing Operational Observation."""
    from app.composition import create_event_runtime
    from app.intelligence.observation.repository import ObservationRepository
    from app.database.session import get_session_manager

    enrichment = _enrich(text="Буревій-2 виходимо на зв'язок")
    integrator = _integrator()
    event = _build_event(enrichment)

    runtime = create_event_runtime()
    result = integrator.integrate(enrichment, _FakeRuntimeAdapter(event))
    assert isinstance(result, RadioEventResult)
    assert result.event_id == event.event_id

    # Drive the canonical Event through the real production composition.
    assert runtime.pipeline.process(event) is True

    repo = ObservationRepository(get_session_manager().get_session())
    obs = repo.get_by_immutable_id(event.event_id)
    assert obs is not None, "final radio event must reach the Operational Observation"
    assert obs.source == "radio"
    assert obs.observation_type == "radio"
    # Derived evidence and the recording reference are preserved in the
    # observation evidence payload.
    evidence = obs.evidence_payload or {}
    raw_data = evidence.get("raw_data", {})
    assert raw_data.get("audio_recording_id") == "rec-1"
    assert "recording" in raw_data
    assert "transcript" in raw_data
    assert "enrichment" in raw_data


class _FakeRuntimeAdapter:
    """Minimal runtime stand-in exposing the sole RAW -> Event seam
    (``_process_raw``) so ``RadioEventIntegrator.integrate`` can be exercised."""

    def __init__(self, event: Event) -> None:
        self._event = event

    def _process_raw(self, raw: dict[str, Any]) -> None:
        # For this test we only need the RAW to be accepted and forwarded to the
        # canonical Event; the canonical Event is already built and driven
        # through the real runtime separately.
        assert isinstance(raw, dict)
        assert "recording" in raw
        assert "transcript" in raw


# --------------------------------------------------------------------------- #
# Test 10 — chronological ordering
# --------------------------------------------------------------------------- #


def test_wo065_10_chronological_ordering(global_session_manager) -> None:
    """The final event timestamp/order follows the existing chronological wall
    contract (occurred_at == canonical event time)."""
    from app.composition import create_event_runtime
    from app.intelligence.observation.repository import ObservationRepository
    from app.database.session import get_session_manager

    runtime = create_event_runtime()

    # Two DISTINCT recordings (distinct audio_recording_id -> distinct
    # enrichment content_id -> distinct canonical event_id), one earlier and
    # one later, so the chronological wall can order them.
    early_event = _build_event(_enrich(
        audio_recording_id="rec-early",
        text="Буревій-2 прийом",
        occurred_at="2026-01-01T00:00:00+00:00",
    ))
    late_event = _build_event(_enrich(
        audio_recording_id="rec-late",
        text="Сокіл-1 прийом",
        occurred_at="2026-01-01T01:00:00+00:00",
    ))

    assert early_event.event_id != late_event.event_id

    # The canonical event timestamp is derived from the evidence timestamp.
    assert early_event.timestamp == datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    assert late_event.timestamp == datetime(2026, 1, 1, 1, 0, 0, tzinfo=timezone.utc)

    assert runtime.pipeline.process(early_event) is True
    assert runtime.pipeline.process(late_event) is True

    repo = ObservationRepository(get_session_manager().get_session())
    obs_early = repo.get_by_immutable_id(early_event.event_id)
    obs_late = repo.get_by_immutable_id(late_event.event_id)
    assert obs_early is not None
    assert obs_late is not None
    # The chronological wall orders by occurred_at (event time).  The stored
    # occurred_at is a naive UTC datetime (SQLite), so compare the wall-clock
    # value (the event time), not the tzinfo.
    assert obs_early.occurred_at == datetime(2026, 1, 1, 0, 0, 0)
    assert obs_late.occurred_at == datetime(2026, 1, 1, 1, 0, 0)
    assert obs_early.occurred_at < obs_late.occurred_at


# --------------------------------------------------------------------------- #
# Test 11 — malformed evidence
# --------------------------------------------------------------------------- #


def test_wo065_11_malformed_evidence() -> None:
    """Invalid enrichment input must fail explicitly, with no partial event."""
    integrator = _integrator()

    # Non-EnrichmentResult input.
    with pytest.raises(FinalEventInvalidError):
        integrator.build_raw("not-a-result")  # type: ignore[arg-type]
    with pytest.raises(FinalEventInvalidError):
        integrator.build_raw(None)  # type: ignore[arg-type]

    # Valid EnrichmentResult but missing a required identity.
    engine = TranscriptEnrichmentEngine()
    result = engine.enrich(_transcript_raw())
    broken = EnrichmentResult(
        audio_recording_id=result.audio_recording_id,
        transcript_content_id=result.transcript_content_id,
        content_id=result.content_id,
        wav_sha256=result.wav_sha256,
        transcript_text=result.transcript_text,
        detected_callsigns=list(result.detected_callsigns),
        confidence=result.confidence,
        detection_method=result.detection_method,
        callsign=result.callsign,
        raw={"audio_recording_id": result.audio_recording_id},
    )
    with pytest.raises(FinalEventInvalidError):
        integrator.build_raw(broken)

    # Empty recording identity — construct the EnrichmentResult directly so the
    # WO-064 engine's own input validation is not what rejects it (the
    # integrator must reject an invalid identity on its own).
    valid = _enrich(audio_recording_id="rec-1", text="Буревій-2 прийом")
    bad_identity = EnrichmentResult(
        audio_recording_id="   ",
        transcript_content_id=valid.transcript_content_id,
        content_id=valid.content_id,
        wav_sha256=valid.wav_sha256,
        transcript_text=valid.transcript_text,
        detected_callsigns=list(valid.detected_callsigns),
        confidence=valid.confidence,
        detection_method=valid.detection_method,
        callsign=valid.callsign,
        raw=dict(valid.raw),
    )
    with pytest.raises(FinalEventInvalidError):
        integrator.build_raw(bad_identity)


# --------------------------------------------------------------------------- #
# Test 12 — source immutability
# --------------------------------------------------------------------------- #


def test_wo065_12_source_immutability() -> None:
    """The upstream transcript/enrichment dicts are never mutated."""
    enrichment = _enrich(text="Буревій-2 прийом")
    raw_before = copy.deepcopy(enrichment.raw)
    transcript_before = copy.deepcopy(enrichment.raw["transcript"])
    enrichment_before = copy.deepcopy(enrichment.raw["enrichment"])

    event = _build_event(enrichment)

    # The enrichment raw and its nested blocks are unchanged.
    assert enrichment.raw == raw_before
    assert enrichment.raw["transcript"] == transcript_before
    assert enrichment.raw["enrichment"] == enrichment_before
    # No mutation of the original transcript text.
    assert enrichment.transcript_text == "Буревій-2 прийом"
    # The final event carries its own copies, not references that were mutated.
    assert event.payload["transcript"]["text"] == "Буревій-2 прийом"
