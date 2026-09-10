"""WO-059 — Radio recording observation mapping tests.

WO-059 corrects the observation-boundary classification bug verified during
forensic discovery: a canonical radio RECORDING event (produced by the RTP ->
VAD -> WAV path, WO-058) carries a ``recording`` block but no frequency or
callsign, yet the observation boundary previously classified every source
``radio`` event as ``radio.transmission`` and rejected it as missing required
fields.

The fix distinguishes the two at the observation classification boundary only:

    radio canonical event
        |
        +-- payload carries a ``recording`` block  ->  radio.recording
        |
        +-- otherwise                              ->  radio.transmission
                                                      (frequency+callsign
                                                       contract preserved)

These tests prove:
  * a real recording-only radio event reaches the observation layer and creates
    an Observation (radio.recording, no frequency/callsign required);
  * a genuine radio transmission event still maps to radio.transmission and
    creates an Observation;
  * the radio.transmission contract (frequency+callsign) is NOT weakened;
  * a recording event with extra optional radio metadata still validates;
  * non-radio source mappings are unchanged;
  * the canonical Event payload / recording block is never mutated.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.database import session as session_mod
from app.database.session import configure_session_manager, get_session_manager
from app.event.event import Event
from app.event.event_metadata import EventMetadata
from app.event.event_types import EventType
from app.observation.canonical_adapter import CanonicalEventToObservationAdapter
from app.observation.models import EVENT_TYPE_MAPPINGS
from app.intelligence.observation.repository import ObservationRepository


@pytest.fixture()
def global_session_manager():
    """Configure the GLOBAL DatabaseSessionManager to an isolated in-memory
    SQLite database and reset it afterwards (mirrors WO-015 test setup)."""
    manager = configure_session_manager("sqlite:///:memory:")
    from app.database.base import Base

    Base.metadata.create_all(manager.engine)
    yield manager
    session_mod._session_manager = None


def make_event(
    *,
    event_id: str,
    source: str = "radio",
    event_type: EventType = EventType.CUSTOM,
    payload: dict | None = None,
    metadata: EventMetadata | None = None,
) -> Event:
    """Build a canonical domain Event with deterministic values."""
    return Event(
        event_id=event_id,
        event_type=event_type,
        timestamp=datetime(2026, 8, 17, 12, 0, 0, tzinfo=timezone.utc),
        source=source,
        payload=payload or {},
        metadata=metadata or EventMetadata(),
    )


def recording_payload(**overrides) -> dict:
    """Build a realistic WO-058 production radio recording payload.

    Matches the shape produced by ``RecordingMetadata.to_event_raw``: a
    ``recording`` block plus the recording identifiers.  It deliberately carries
    NO ``frequency`` and NO ``callsign`` (the production path has no source for
    them, and STT is disabled).
    """
    rec = {
        "wav_path": "/tmp/wo059_recording_master.wav",
        "mp3_path": "/tmp/wo059_recording_master.mp3",
        "format": "wav",
        "started_at": "2026-09-03T12:00:00Z",
        "ended_at": "2026-09-03T12:00:30Z",
        "duration_ms": 30000,
        "duration": 30.0,
        "source": "radio",
        "multicast_address": "239.233.18.30",
        "udp_port": 5033,
        "codec": "pcm",
        "sample_rate": 8000,
        "channels": 1,
        "sha256": "a" * 64,
        "complete": False,
        "finalize_reason": "source_shutdown",
    }
    rec.update(overrides)
    return {
        "occurred_at": "2026-09-03T12:00:00Z",
        "audio_recording_id": "rec-wo059-1",
        "content_id": "content-wo059-1",
        "recording": rec,
    }


def _create_observation_for(event: Event) -> bool:
    """Drive a canonical Event through the REAL production composition
    boundary (create_event_runtime -> pipeline.process -> canonical EventBus ->
    ObservationService -> ObservationProcessor -> Observation repository)."""
    from app.composition import create_event_runtime

    runtime = create_event_runtime()
    return runtime.pipeline.process(event)


# ---------------------------------------------------------------------------
# TEST 1 — recording positive path
# ---------------------------------------------------------------------------


def test_wo059_01_recording_positive_path(global_session_manager):
    """A recording-only radio event maps to ``radio.recording`` and creates an
    Observation without any frequency/callsign."""
    adapter = CanonicalEventToObservationAdapter()
    payload = recording_payload()
    assert "frequency" not in payload
    assert "callsign" not in payload

    ev = make_event(event_id="e-rec-1", source="radio", payload=payload)

    # Classification at the adapter boundary.
    assert adapter.derive_event_type(ev) == "radio.recording"

    # Real canonical Event -> observation path.
    assert _create_observation_for(ev) is True

    repo = ObservationRepository(get_session_manager().get_session())
    obs = repo.get_by_immutable_id("e-rec-1")
    assert obs is not None, "recording-only radio event must create an Observation"
    assert obs.source == "radio"
    assert obs.observation_type == "radio"
    # The recording reference survives into the observation evidence.
    evidence = obs.evidence_payload or {}
    assert "recording" in evidence.get("raw_data", {})
    assert evidence["raw_data"]["recording"]["wav_path"] == "/tmp/wo059_recording_master.wav"


# ---------------------------------------------------------------------------
# TEST 2 — transmission positive path
# ---------------------------------------------------------------------------


def test_wo059_02_transmission_positive_path(global_session_manager):
    """A genuine radio transmission event still maps to ``radio.transmission``
    and creates an Observation."""
    adapter = CanonicalEventToObservationAdapter()
    payload = {"frequency": 100.5, "callsign": "BRAVO"}
    ev = make_event(event_id="e-tx-1", source="radio", payload=payload)

    assert adapter.derive_event_type(ev) == "radio.transmission"
    assert _create_observation_for(ev) is True

    repo = ObservationRepository(get_session_manager().get_session())
    obs = repo.get_by_immutable_id("e-tx-1")
    assert obs is not None, "genuine transmission event must create an Observation"
    assert obs.source == "radio"
    assert obs.observation_type == "radio"


# ---------------------------------------------------------------------------
# TEST 3 — transmission contract is NOT weakened
# ---------------------------------------------------------------------------


def test_wo059_03_transmission_contract_not_weakened(global_session_manager):
    """A radio event WITHOUT a recording block that is missing frequency and
    callsign must NOT silently become a valid radio.transmission observation.

    The implementation must not solve the problem by removing required fields.
    """
    adapter = CanonicalEventToObservationAdapter()
    mapping = EVENT_TYPE_MAPPINGS["radio.transmission"]
    assert mapping.required_fields == ["frequency", "callsign"], (
        "radio.transmission contract must still require frequency + callsign"
    )

    # Radio event with NO recording block, NO frequency, NO callsign.
    ev = make_event(event_id="e-tx-missing", source="radio", payload={"some": "metadata"})
    assert adapter.derive_event_type(ev) == "radio.transmission"

    # The pipeline must still succeed (canonical durability is authoritative),
    # but the observation projection must be rejected by the unchanged
    # radio.transmission contract.
    assert _create_observation_for(ev) is True

    repo = ObservationRepository(get_session_manager().get_session())
    obs = repo.get_by_immutable_id("e-tx-missing")
    assert obs is None, (
        "a radio event missing frequency+callsign (no recording block) must NOT "
        "create a radio.transmission Observation"
    )


# ---------------------------------------------------------------------------
# TEST 4 — recording with optional metadata
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "extra",
    [
        {"modulation": "FM"},
        {"frequency": 100.5},  # has frequency, still no callsign
        {"callsign": "ALPHA"},  # has callsign, still no frequency
        {"modulation": "FM", "signal_strength": -78},  # neither, plus extras
    ],
)
def test_wo059_04_recording_with_optional_metadata(extra, global_session_manager):
    """A recording event with optional radio metadata but missing one or both of
    frequency/callsign must remain ``radio.recording`` and validate."""
    adapter = CanonicalEventToObservationAdapter()
    payload = recording_payload()
    payload.update(extra)

    ev = make_event(event_id="e-rec-meta", source="radio", payload=payload)
    assert adapter.derive_event_type(ev) == "radio.recording"
    assert _create_observation_for(ev) is True

    repo = ObservationRepository(get_session_manager().get_session())
    obs = repo.get_by_immutable_id("e-rec-meta")
    assert obs is not None, (
        "recording event with optional metadata must create an Observation"
    )
    assert obs.observation_type == "radio"


# ---------------------------------------------------------------------------
# TEST 5 — other sources unchanged
# ---------------------------------------------------------------------------


def test_wo059_05_other_sources_unchanged():
    """Non-radio source mappings are unchanged by the radio fix."""
    adapter = CanonicalEventToObservationAdapter()
    cases = {
        "signal": "signal.message",
        "mqtt": "mqtt.message",
        "atak": "atak.map_object",
        "telegram": "telegram.message",
    }
    for source, expected in cases.items():
        ev = make_event(event_id=f"e-{source}", source=source, payload={})
        assert adapter.derive_event_type(ev) == expected, f"{source} -> {expected}"


# ---------------------------------------------------------------------------
# TEST 6 — canonical event integrity
# ---------------------------------------------------------------------------


def test_wo059_06_canonical_event_integrity(global_session_manager):
    """The observation conversion must not mutate the canonical Event payload or
    replace/remove its recording block."""
    adapter = CanonicalEventToObservationAdapter()
    payload = recording_payload()
    rec_before = dict(payload["recording"])
    ev = make_event(event_id="e-int-1", source="radio", payload=payload)

    d = adapter.to_observation_dict(ev)
    assert d["event_type"] == "radio.recording"

    # The canonical Event payload is unchanged.
    assert "recording" in ev.payload
    assert ev.payload["recording"] == rec_before
    assert ev.payload["recording"]["wav_path"] == "/tmp/wo059_recording_master.wav"
    assert ev.payload["recording"]["sha256"] == "a" * 64

    # The observation data retains the recording block.
    assert "recording" in d["data"]
    assert d["data"]["recording"]["wav_path"] == "/tmp/wo059_recording_master.wav"


# ---------------------------------------------------------------------------
# Mapping contract assertions
# ---------------------------------------------------------------------------


def test_wo059_07_recording_mapping_does_not_require_frequency_or_callsign():
    """The radio.recording mapping must not require frequency/callsign and must
    validate a recording-only payload."""
    mapping = EVENT_TYPE_MAPPINGS["radio.recording"]
    assert "frequency" not in mapping.required_fields
    assert "callsign" not in mapping.required_fields
    # A recording-only payload validates.
    payload = recording_payload()
    assert mapping.is_valid_event(payload) is True
