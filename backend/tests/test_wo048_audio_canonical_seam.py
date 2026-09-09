"""WO-048 — Audio canonical seam integration.

Proves that an audio-generated event reaches the canonical ingestion boundary
and that the orchestrator does NOT own canonical event creation or durable
persistence.

Target architecture (WO-048):

    AudioOrchestrator
        |  audio buffering / segmentation / artifact production ONLY
        v
    canonical-input raw dict (SourceEnvelope)
        v
    AdapterRuntime
        v
    EventFactory.create_event()
        v
    EventPipeline.process(event)
        v
    EventRepository.save + ProjectionEngine

These are STRUCTURAL / CONTRACT-level guards, mirroring the WO-014-013
invariants.  They do not mock away the seam; they exercise the real
``AdapterRuntime._process_raw`` -> ``EventFactory.create_event`` ->
``EventPipeline.process`` path and assert ownership boundaries.
"""

from __future__ import annotations

import io
import re
import tokenize
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.audio.audio_config import AudioConfig
from app.audio.audio_segment import AudioSegment
from app.audio.callsign import CallsignDetector
from app.audio.orchestrator import AudioEventOrchestrator
from app.audio.transcriber import DeterministicTestTranscriber
from app.event.event import Event
from app.event_pipeline.event_pipeline import EventPipeline
from app.event_sources.factory.event_factory import EventFactory
from app.event_sources.identity.event_identity import EventIdentityResolver
from app.event_sources.interfaces.i_event_source_adapter import IEventSourceAdapter
from app.event_sources.runtime.adapter_runtime import AdapterRuntime

PHRASE = "Буревій-2, прийом. Виходжу на позицію."
CONTENT_ID = "bureviy-2"
CALLSIGN = "Буревій-2"

_ORCHESTRATOR_PATH = (
    Path(__file__).resolve().parent.parent / "app" / "audio" / "orchestrator.py"
)


def _cfg(**overrides) -> AudioConfig:
    return AudioConfig(
        multicast_address="239.255.0.1",
        multicast_port=50000,
        codec="wav",
        source_name="radio",
        **overrides,
    )


def _segment() -> AudioSegment:
    occ = datetime(2026, 9, 2, 10, 31, 4, tzinfo=timezone.utc)
    return AudioSegment(
        content_id=CONTENT_ID,
        audio_bytes=b"pcm",
        occurred_at=occ,
        received_at=occ,
    )


def _make_orchestrator() -> AudioEventOrchestrator:
    return AudioEventOrchestrator(
        _cfg(),
        transcriber=DeterministicTestTranscriber(
            phrase_map={CONTENT_ID: PHRASE}, default_text=""
        ),
        callsign_detector=CallsignDetector(callsigns=[CALLSIGN]),
    )


class _FakeAdapter(IEventSourceAdapter):
    """Minimal IEventSourceAdapter exposing the orchestrator's raw dicts."""

    def __init__(self, raws):
        self._raws = list(raws)
        self._started = False

    def start(self) -> None:
        self._started = True

    def stop(self) -> None:
        self._started = False

    def health(self) -> bool:
        return True

    def read_events(self) -> list[dict]:
        raws = self._raws
        self._raws = []
        return raws

    def source_name(self) -> str:
        return "radio"


class _SpyRepository:
    """Records canonical Events passed to save() (persistence seam spy)."""

    def __init__(self) -> None:
        self.saved: list[Event] = []

    def save(self, event: Event) -> None:
        self.saved.append(event)


class _SpyProjection:
    """Records canonical Events passed to the projection callable."""

    def __init__(self) -> None:
        self.events: list[Event] = []

    def __call__(self, event: Event) -> None:
        self.events.append(event)


# --- Static / structural helpers (mirror WO-014-013) --------------------------


def _code_only(src: str) -> str:
    """Return module source with docstrings, string literals and comments
    blanked out, preserving positions of real code (no docstring false-positives)."""
    lines = src.splitlines(keepends=True)
    chars = list(src)
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type in (tokenize.COMMENT, tokenize.STRING):
                start, end = tok.start, tok.end
                for line_idx in range(start[0] - 1, end[0]):
                    line_start = sum(len(l) for l in lines[:line_idx])
                    line_len = len(lines[line_idx])
                    c0 = start[1] if line_idx == start[0] - 1 else 0
                    c1 = end[1] if line_idx == end[0] - 1 else line_len - 1
                    for ci in range(c0, c1):
                        if chars[line_start + ci] not in "\r\n":
                            chars[line_start + ci] = " "
    except Exception:
        return src
    return "".join(chars)


def _import_statements(src: str) -> list[str]:
    code = _code_only(src)
    imports: list[str] = []
    for m in re.finditer(r"(?:^|\s)((?:import|from)\s+\S[^\n]*)", code):
        imports.append(m.group(1))
    return imports


# --- Test C: orchestrator has no direct factory / persistence ----------------


def test_orchestrator_has_no_direct_factory_or_persistence() -> None:
    """WO-048 / INV-1: AudioEventOrchestrator must not call EventFactory,
    construct a canonical Event, instantiate an EventPipeline, or persist."""
    src = _ORCHESTRATOR_PATH.read_text(encoding="utf-8")
    code = _code_only(src)

    # No canonical event factory call / construction in the orchestrator.
    assert ".create_event(" not in code, (
        "AudioEventOrchestrator must not call EventFactory.create_event (INV-1)."
    )
    assert "EventFactory(" not in code, "AudioEventOrchestrator must not build an EventFactory."

    # No direct pipeline instantiation / persistence ownership.
    assert "EventPipeline(" not in code, (
        "AudioEventOrchestrator must not instantiate an EventPipeline (Rule D)."
    )
    assert "self._repository" not in code, (
        "AudioEventOrchestrator must not own an EventRepository (Rule B)."
    )
    assert ".save(" not in code, (
        "AudioEventOrchestrator must not persist directly (Rule B)."
    )

    # No EventFactory import (single canonical seam is AdapterRuntime only).
    for imp in _import_statements(src):
        assert "event_sources.factory.event_factory" not in imp, (
            "AudioEventOrchestrator must not import EventFactory (INV-1)."
        )
        assert "event_pipeline" not in imp, (
            "AudioEventOrchestrator must not import the pipeline (Rule D)."
        )


# --- Test B / D / E: audio event reaches the canonical ingestion path ---------


def test_audio_event_reaches_canonical_ingestion() -> None:
    """WO-048: an audio-generated event reaches the canonical ingestion
    boundary and is processed by the existing EventPipeline instance."""
    orch = _make_orchestrator()
    raw = orch.process_segment(_segment())
    assert isinstance(raw, dict), "orchestrator must produce the canonical raw dict"

    # Canonical ingestion boundary: AdapterRuntime -> EventFactory -> EventPipeline.
    pipeline = EventPipeline()
    repo = _SpyRepository()
    projection = _SpyProjection()
    pipeline.set_repository(repo)
    pipeline.set_projection(projection)
    factory = EventFactory(identity_resolver=EventIdentityResolver())
    adapter = _FakeAdapter([raw])
    runtime = AdapterRuntime(adapter=adapter, factory=factory, pipeline=pipeline)

    runtime._process_raw(raw)  # the canonical RAW -> Event seam (INV-1)

    # The audio raw dict became exactly one canonical Event, durably persisted
    # through the canonical pipeline (not by the orchestrator).
    assert len(repo.saved) == 1
    event = repo.saved[0]
    assert isinstance(event, Event)
    assert event.source == "radio"
    assert event.payload["transcript"] == PHRASE
    assert event.payload["detected_callsigns"] == [CALLSIGN]

    # The existing EventPipeline instance processed the event (Rule D) and the
    # projection ran (Rule: reaches ProjectionEngine through EventPipeline).
    assert len(projection.events) == 1
    assert projection.events[0].event_id == event.event_id


# --- Test E: projection runs on the audio event ------------------------------


def test_audio_event_reaches_projection_engine() -> None:
    """WO-048: the canonical pipeline projects the audio event (ProjectionEngine
    is reached through EventPipeline, not bypassed)."""
    orch = _make_orchestrator()
    raw = orch.process_segment(_segment())

    pipeline = EventPipeline()
    repo = _SpyRepository()
    projection = _SpyProjection()
    pipeline.set_repository(repo)
    pipeline.set_projection(projection)
    factory = EventFactory(identity_resolver=EventIdentityResolver())
    adapter = _FakeAdapter([raw])
    runtime = AdapterRuntime(adapter=adapter, factory=factory, pipeline=pipeline)

    runtime._process_raw(raw)

    assert len(projection.events) == 1, (
        "the audio event must reach the ProjectionEngine through EventPipeline"
    )
    assert isinstance(projection.events[0], Event)
    # Projection runs AFTER the durable persistence (canonical pipeline order).
    assert len(repo.saved) == 1


# --- Test F: one logical audio event -> one durable persistence --------------


def test_no_duplicate_persistence_for_single_audio_event() -> None:
    """WO-048: one logical audio event results in exactly one durable event
    persistence operation.  The orchestrator never saves; only the canonical
    pipeline persists."""
    orch = _make_orchestrator()
    raw = orch.process_segment(_segment())

    pipeline = EventPipeline()
    repo = _SpyRepository()
    pipeline.set_repository(repo)
    factory = EventFactory(identity_resolver=EventIdentityResolver())
    adapter = _FakeAdapter([raw])
    runtime = AdapterRuntime(adapter=adapter, factory=factory, pipeline=pipeline)

    runtime._process_raw(raw)

    # Exactly one save for one logical audio event (no orchestrator.save()).
    assert len(repo.saved) == 1, (
        "one logical audio event must produce exactly one durable persistence"
    )

    # The orchestrator itself performed no persistence (no repository exists).
    assert not hasattr(orch, "_repository")


# --- Orchestrator is a producer for the ingestion boundary -------------------


def test_orchestrator_read_events_drains_canonical_input() -> None:
    """WO-048: the orchestrator exposes queued canonical-input raw dicts via
    read_events(), so an AdapterRuntime can consume them directly."""
    orch = _make_orchestrator()
    # Simulate the receiver hook queueing a produced raw dict.
    orch._on_segment(_segment())
    assert orch.pending_count() == 1

    drained = orch.read_events()
    assert len(drained) == 1
    assert isinstance(drained[0], dict)
    assert drained[0]["transcript"] == PHRASE
    assert drained[0]["detected_callsigns"] == [CALLSIGN]
    # After draining, nothing remains.
    assert orch.read_events() == []
    assert orch.pending_count() == 0


def test_orchestrator_fail_closed_without_transcriber() -> None:
    """WO-041-CORR F-01: with no transcriber the orchestrator is fail-closed
    (raises) rather than fabricating a transcript."""
    orch = AudioEventOrchestrator(_cfg())
    with pytest.raises(ValueError):
        orch.process_segment(_segment())
