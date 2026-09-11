"""WO-066 — End-to-end verification of the production radio chain (corrective).

Proves the real architectural seam end-to-end through the production
composition / runtime path:

    accepted durable radio recording (WAV + verified SHA-256)
        -> recording evidence (``radio.recording`` observation)
        -> RecordingAccess identity resolution (operator observation store)
        -> STT (ITranscriber seam) -> transcript evidence
        -> enrichment (callsign detection) -> enrichment evidence
        -> final radio event (WO-065) -> canonical RAW
        -> production composition -> RadioEventIntegrator (composition-owned)
        -> production AdapterRuntime._process_raw (sole RAW->Event boundary, CONTRACT-2)
        -> EventFactory -> EventPipeline -> durable journal
        -> canonical Observation
        -> chronological wall (``/api/v1/operator/observations``)
        -> evidence / playback retrieval (``/api/v1/operator/recordings/{id}``)

The central question this answers: does ONE accepted durable radio recording
traverse the real production runtime path and result in the expected canonical
Observation that is visible to the chronological operational wall?

Corrective (WO-066): the primary path NO LONGER manually assembles
``RadioEventIntegrator()`` or ``AdapterRuntime(_DummyAdapter(), ...)``.  The
runtime/application is obtained through the real production composition
(``create_production_runtime``), which constructs and owns the
``RadioEventIntegrator`` and ``EventFactory``.  The production ``AdapterRuntime``
is obtained through the production supervisor.  The test additionally proves:

  * persistence-level idempotency (COUNT(observations for immutable_id) == 1
    after re-delivering the same logical final radio event);
  * source immutability (recording / transcript / enrichment evidence are not
    mutated by the production chain);
  * the complete canonical identity chain.

No production data is used.  A controlled temporary WAV fixture is written and
the recording is persisted through the real production composition so the
canonical identity chain (audio_recording_id -> content_id -> event_id ->
immutable_id) holds exactly as in production.  STT is exercised through the
existing ``ITranscriber`` seam with a deterministic fake engine (the production
engine is abstracted behind that seam; no model is downloaded and no network
call is made).  The multicast radio adapter is the external-source boundary and
is constructed from the production source catalog definition; the canonical
runtime (AdapterRuntime, EventFactory, EventPipeline, Observation) is the
production one.

Author: Tactical Core Engineering Team
Version: 2.0
"""

from __future__ import annotations

import copy
import hashlib
import os
import struct
import tempfile

import pytest
from sqlalchemy import func, select

import app.database.session as session_mod
from app.audio.radio_event import RadioEventIntegrator
from app.audio.recording_stt_worker import RecordingSttWorker
from app.audio.source_adapter import MulticastAudioSourceAdapter
from app.audio.transcript_enrichment import TranscriptEnrichmentEngine
from app.audio.wav_writer import write_wav_atomic
from app.bootstrap import create_production_runtime
from app.contracts.audio import ITranscriber
from app.database.base import Base
from app.database.session import configure_session_manager, get_session_manager
from app.event_sources.config.production_source_config import PRODUCTION_SOURCE_CATALOG
from app.event_sources.identity.event_identity import EventIdentityResolver
from app.intelligence.observation.model import Observation
from app.intelligence.observation.repository import (
    ObservationRepository,
    SessionManagerObservationRepository,
)
from app.operator.service import OperatorService
from app.event_repository.durable.sqlalchemy_event_repository import (
    SQLAlchemyEventRepository,
)
from app.entity_repository.sqlalchemy_entity_repository import (
    SQLAlchemyEntityRepository,
)
from app.entity_relations.sqlalchemy_relation_repository import (
    SQLAlchemyRelationRepository,
)

SAMPLE_RATE = 8000
CHANNELS = 1
SAMPWIDTH = 2
RECORDING_ID = "rec-wo066-1"
TRANSCRIPT_TEXT = "Буревій-2 виходимо на зв'язок"
DETECTED_CALLSIGNS = ["Буревій-2"]


def _reset() -> None:
    session_mod._session_manager = None


def _url(db_path: str) -> str:
    return f"sqlite:///{db_path}"


def _wav_pcm(samples: int = 1600, value: int = 1000) -> bytes:
    return struct.pack(f"<{samples}h", *([value] * samples))


def _sha256_file(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


class _DeterministicTranscriber(ITranscriber):
    """Deterministic fake STT engine (implements the production seam)."""

    def __init__(self, text: str = TRANSCRIPT_TEXT) -> None:
        self._text = text

    @property
    def model(self) -> str:
        return "fake-stt"

    def is_ready(self) -> bool:
        return True

    def transcribe(self, audio_data: bytes, language: str | None = None) -> str:
        return self._text


def _write_recording_wav(archive_root: str) -> tuple[str, bytes, str]:
    """Write a controlled WAV inside the archive root.

    Returns ``(wav_path, pcm, sha256)``.
    """
    wav_path = os.path.join(archive_root, "radio", f"{RECORDING_ID}.wav")
    os.makedirs(os.path.dirname(wav_path), exist_ok=True)
    pcm = _wav_pcm()
    write_wav_atomic(pcm, wav_path, SAMPLE_RATE, CHANNELS, SAMPWIDTH)
    return os.path.realpath(wav_path), pcm, _sha256_file(wav_path)


def _recording_raw(wav_path: str, sha256: str) -> dict:
    """Production-shaped recording raw (content_id == audio_recording_id)."""
    return {
        "timestamp": "2026-09-03T12:00:00+00:00",
        "occurred_at": "2026-09-03T12:00:00+00:00",
        "audio_recording_id": RECORDING_ID,
        "content_id": RECORDING_ID,
        "recording": {
            "wav_path": wav_path,
            "mp3_path": wav_path.replace(".wav", ".mp3"),
            "format": "wav",
            "duration_ms": 30000,
            "duration": 30.0,
            "source": "radio",
            "sha256": sha256,
            "complete": True,
            "finalize_reason": "voice_activity",
        },
    }


def _compose_runtime() -> "object":
    """Return a production composition runtime against the configured DB."""
    return create_production_runtime()


def _production_radio_runtime(runtime) -> "object":
    """Register the production radio adapter through the production composition.

    The multicast radio adapter is the external-source boundary: it is built
    from the production source catalog definition and is injected with the
    composition-owned ``RadioEventIntegrator`` (WO-066 seam) so a derived
    transcript drives the WO-065 final-radio-event producer.  The returned
    ``AdapterRuntime`` is the PRODUCTION runtime created by the production
    supervisor (not a manual ``AdapterRuntime`` construction).
    """
    definition = PRODUCTION_SOURCE_CATALOG[0]
    assert definition.name == "radio"
    adapter = MulticastAudioSourceAdapter(
        definition,
        enrichment_engine=TranscriptEnrichmentEngine(),
        radio_event_integrator=runtime.radio_event_integrator,
    )
    return runtime.add_source(adapter)


def _operator_service(mgr) -> OperatorService:
    """Build a real operator service wired to the same session manager."""
    return OperatorService(
        event_repository=SQLAlchemyEventRepository(session_manager=mgr),
        entity_repository=SQLAlchemyEntityRepository(session_manager=mgr),
        relation_repository=SQLAlchemyRelationRepository(session_manager=mgr),
        observation_repository=SessionManagerObservationRepository(mgr),
    )


def _operator_client(mgr):
    """Build a real operator FastAPI app wired to the same session manager."""
    from fastapi.testclient import TestClient

    from app.operator.app import create_operator_app

    app = create_operator_app(
        event_repository=SQLAlchemyEventRepository(session_manager=mgr),
        entity_repository=SQLAlchemyEntityRepository(session_manager=mgr),
        relation_repository=SQLAlchemyRelationRepository(session_manager=mgr),
        observation_repository=SessionManagerObservationRepository(mgr),
    )
    return TestClient(app)


@pytest.fixture()
def env(monkeypatch, tmp_path):
    """Isolated archive root + file DB + token, reset after the test."""
    archive_root = tmp_path / "archive"
    archive_root.mkdir()
    monkeypatch.setenv("RECORDING_ARCHIVE_ROOT", str(archive_root))
    monkeypatch.setenv("OPERATOR_TOKEN", "wo066-secret")

    db_path = str(tmp_path / "wo066.db")
    _reset()
    mgr = configure_session_manager(_url(db_path))
    Base.metadata.create_all(mgr.engine)

    yield {"archive_root": str(archive_root), "db_path": db_path, "mgr": mgr}

    _reset()


def _persist_recording(env, runtime) -> tuple[str, dict]:
    """Persist an accepted durable recording observation via the production
    composition (production EventFactory + pipeline).

    Returns ``(event_id, fixture)`` where ``fixture`` carries the WAV path and
    SHA-256.  The observation's ``immutable_id`` equals the canonical
    ``event_id`` derived from the recording ``content_id``.
    """
    wav_path, pcm, sha = _write_recording_wav(env["archive_root"])
    raw = _recording_raw(wav_path, sha)
    event = runtime.event_factory.create_event(raw, "radio")
    assert runtime.pipeline.process(event) is True
    return event.event_id, {"wav_path": wav_path, "pcm": pcm, "sha256": sha}


def _run_full_chain(env, runtime, op, aruntime) -> tuple[str, str, dict]:
    """Run one accepted recording through the whole production chain.

    Returns ``(recording_event_id, final_event_id, ctx)`` where ``ctx`` carries
    the final RAW dict, the enrichment result and the recording fixture.
    """
    # 1. Accepted durable recording observation (production composition path).
    rec_event_id, fixture = _persist_recording(env, runtime)

    # 2. Real production resolution path (operator observation store).
    artifact = op._recording_access.resolve(RECORDING_ID)
    assert artifact.recording_id == RECORDING_ID
    assert artifact.sha256 == fixture["sha256"]

    # 3. STT -> transcript evidence.
    emitted: list[dict] = []
    worker = RecordingSttWorker(
        _DeterministicTranscriber(),
        op._recording_access.resolve,
        source="radio",
        on_transcript=emitted.append,
    )
    result = worker.transcribe(RECORDING_ID)
    assert result.content_id == f"{RECORDING_ID}|transcript"
    assert len(emitted) == 1

    # 4. Enrichment -> enrichment evidence.
    enrichment = TranscriptEnrichmentEngine().enrich(result.raw)
    assert enrichment.content_id == f"{RECORDING_ID}|transcript|enrichment"
    assert enrichment.detected_callsigns == DETECTED_CALLSIGNS

    # 5. Final radio event -> canonical RAW -> sole RAW->Event boundary, using
    #    the composition-owned integrator + production AdapterRuntime.
    integrator = runtime.radio_event_integrator
    assert isinstance(integrator, RadioEventIntegrator), (
        "the production composition must provide the RadioEventIntegrator"
    )
    final_raw = integrator.build_raw(enrichment)
    assert "recording" in final_raw
    assert final_raw["enrichment_content_id"] == f"{RECORDING_ID}|transcript|enrichment"
    aruntime._process_raw(final_raw)

    final_event_id = integrator.resolve_event_id(enrichment)
    ctx = {"final_raw": final_raw, "enrichment": enrichment, "fixture": fixture}
    return rec_event_id, final_event_id, ctx


# --------------------------------------------------------------------------- #
# Test 1 — full chain produces a canonical Observation.
# --------------------------------------------------------------------------- #


def test_wo066_01_full_chain_produces_canonical_observation(env):
    runtime = _compose_runtime()
    op = _operator_service(env["mgr"])
    aruntime = _production_radio_runtime(runtime)
    rec_event_id, final_event_id, _ctx = _run_full_chain(env, runtime, op, aruntime)

    repo = ObservationRepository(get_session_manager().get_session())
    obs = repo.get_by_immutable_id(final_event_id)
    assert obs is not None, "final radio event must reach the Operational Observation"
    assert obs.source == "radio"
    assert obs.observation_type == "radio"
    raw_data = (obs.evidence_payload or {}).get("raw_data", {})
    assert raw_data.get("audio_recording_id") == RECORDING_ID
    assert "recording" in raw_data
    assert "transcript" in raw_data
    assert "enrichment" in raw_data

    # The recording observation is also present (accepted durable recording).
    rec_obs = repo.get_by_immutable_id(rec_event_id)
    assert rec_obs is not None
    assert rec_obs.observation_type == "radio"


# --------------------------------------------------------------------------- #
# Test 2 — chronological wall visibility (operator /observations endpoint).
# --------------------------------------------------------------------------- #


def test_wo066_02_observation_visible_on_chronological_wall(env):
    runtime = _compose_runtime()
    op = _operator_service(env["mgr"])
    aruntime = _production_radio_runtime(runtime)
    rec_event_id, final_event_id, _ctx = _run_full_chain(env, runtime, op, aruntime)

    client = _operator_client(env["mgr"])
    headers = {"Authorization": "Bearer wo066-secret"}
    resp = client.get("/api/v1/operator/observations", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    ids = [o["immutable_id"] for o in body.get("observations", [])]
    assert final_event_id in ids, f"final observation missing from wall: {ids}"
    assert rec_event_id in ids, f"recording observation missing from wall: {ids}"
    assert all(o["source"] == "radio" for o in body["observations"])


# --------------------------------------------------------------------------- #
# Test 3 — evidence / playback retrieval (operator /recordings/{id} endpoint).
# --------------------------------------------------------------------------- #


def test_wo066_03_evidence_playback_retrieval(env):
    runtime = _compose_runtime()
    op = _operator_service(env["mgr"])
    aruntime = _production_radio_runtime(runtime)
    _ctx_fixture = _run_full_chain(env, runtime, op, aruntime)[2]["fixture"]

    client = _operator_client(env["mgr"])
    headers = {"Authorization": "Bearer wo066-secret"}
    resp = client.get(
        f"/api/v1/operator/recordings/{RECORDING_ID}", headers=headers
    )
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("audio/wav")
    with open(
        os.path.join(env["archive_root"], "radio", f"{RECORDING_ID}.wav"), "rb"
    ) as fh:
        assert resp.content == fh.read(), "playback must return the exact WAV bytes"
    # SHA-256 verification of the returned media.
    assert hashlib.sha256(resp.content).hexdigest() == _ctx_fixture["sha256"]


# --------------------------------------------------------------------------- #
# Test 4 — identity chain is deterministic and idempotent (canonical identity).
# --------------------------------------------------------------------------- #


def test_wo066_04_identity_chain_deterministic(env):
    runtime = _compose_runtime()
    op = _operator_service(env["mgr"])
    aruntime = _production_radio_runtime(runtime)
    rec_event_id, final_event_id, ctx = _run_full_chain(env, runtime, op, aruntime)

    # Re-running the same logical recording yields the SAME canonical identity.
    wav_path, _pcm, sha = _write_recording_wav(env["archive_root"])
    raw = _recording_raw(wav_path, sha)
    event = runtime.event_factory.create_event(raw, "radio")
    assert event.event_id == rec_event_id, "recording identity must be deterministic"

    resolver = EventIdentityResolver()
    expected_final = resolver.resolve(
        {"content_id": f"{RECORDING_ID}|transcript|enrichment"}, "radio"
    )
    assert expected_final is not None
    assert final_event_id == expected_final, "final event identity must be deterministic"
    # Final event content identity == enrichment content_id.
    assert ctx["final_raw"]["content_id"] == f"{RECORDING_ID}|transcript|enrichment"


# --------------------------------------------------------------------------- #
# Test 5 — the recording is resolved only by identity, never by path.
# --------------------------------------------------------------------------- #


def test_wo066_05_recording_resolved_by_identity(env):
    runtime = _compose_runtime()
    op = _operator_service(env["mgr"])
    aruntime = _production_radio_runtime(runtime)
    _run_full_chain(env, runtime, op, aruntime)

    artifact = op._recording_access.resolve(RECORDING_ID)
    assert artifact.recording_id == RECORDING_ID
    assert len(artifact.sha256) == 64
    assert artifact.mime_type == "audio/wav"
    # Confinement: the resolved path stays inside the archive root.
    assert os.path.realpath(artifact.path).startswith(
        os.path.realpath(env["archive_root"])
    )


# --------------------------------------------------------------------------- #
# Test 6 — persistence-level idempotency (COUNT(immutable_id) == 1).
# --------------------------------------------------------------------------- #


def test_wo066_06_persistence_idempotency(env):
    runtime = _compose_runtime()
    op = _operator_service(env["mgr"])
    aruntime = _production_radio_runtime(runtime)
    _rec_event_id, final_event_id, ctx = _run_full_chain(env, runtime, op, aruntime)

    # Deliver the SAME logical final radio event again through the production
    # path (identical RAW -> identical canonical event_id -> idempotent persist).
    aruntime._process_raw(ctx["final_raw"])

    # Query durable Observation state through the production read path.
    session = get_session_manager().get_session()
    count = session.execute(
        select(func.count(Observation.id)).where(
            Observation.immutable_id == final_event_id
        )
    ).scalar_one()
    assert count == 1, (
        f"duplicate delivery must not create a second observation; got {count}"
    )

    # The observation is still exactly the one canonical Observation.
    repo = ObservationRepository(session)
    obs = repo.get_by_immutable_id(final_event_id)
    assert obs is not None
    assert obs.immutable_id == final_event_id


# --------------------------------------------------------------------------- #
# Test 7 — source immutability (recording / transcript / enrichment evidence).
# --------------------------------------------------------------------------- #


def test_wo066_07_source_immutability(env):
    runtime = _compose_runtime()
    op = _operator_service(env["mgr"])
    aruntime = _production_radio_runtime(runtime)

    # Capture the source evidence BEFORE processing.
    wav_path, _pcm, sha = _write_recording_wav(env["archive_root"])
    recording_raw = _recording_raw(wav_path, sha)
    recording_before = copy.deepcopy(recording_raw)

    # Persist the recording through the production composition.
    event = runtime.event_factory.create_event(recording_raw, "radio")
    assert runtime.pipeline.process(event) is True

    # STT -> transcript evidence.
    worker = RecordingSttWorker(
        _DeterministicTranscriber(),
        op._recording_access.resolve,
        source="radio",
    )
    result = worker.transcribe(RECORDING_ID)
    transcript_before = copy.deepcopy(result.raw)

    # Enrichment -> enrichment evidence.
    enrichment = TranscriptEnrichmentEngine().enrich(result.raw)
    enrichment_before = copy.deepcopy(enrichment.raw)

    # Integrate through the production composition (integrator + AdapterRuntime).
    integrator = runtime.radio_event_integrator
    final_raw = integrator.build_raw(enrichment)
    aruntime._process_raw(final_raw)

    # The production chain must NOT mutate any source evidence.
    assert recording_raw == recording_before, "recording evidence was mutated"
    assert result.raw == transcript_before, "transcript evidence was mutated"
    assert enrichment.raw == enrichment_before, "enrichment evidence was mutated"
    assert enrichment.transcript_text == TRANSCRIPT_TEXT


# --------------------------------------------------------------------------- #
# Test 8 — complete canonical identity chain.
# --------------------------------------------------------------------------- #


def test_wo066_08_identity_chain_full(env):
    runtime = _compose_runtime()
    op = _operator_service(env["mgr"])
    aruntime = _production_radio_runtime(runtime)
    rec_event_id, final_event_id, ctx = _run_full_chain(env, runtime, op, aruntime)

    enrichment = ctx["enrichment"]
    final_raw = ctx["final_raw"]

    # recording_id == recording.content_id.
    assert enrichment.audio_recording_id == RECORDING_ID
    # transcript.content_id == recording_id + "|transcript".
    assert enrichment.transcript_content_id == f"{RECORDING_ID}|transcript"
    # enrichment.content_id == recording_id + "|transcript|enrichment".
    assert enrichment.content_id == f"{RECORDING_ID}|transcript|enrichment"
    # final event content_id == enrichment content_id.
    assert final_raw["content_id"] == enrichment.content_id
    assert final_raw["enrichment_content_id"] == enrichment.content_id

    # Resolve canonical Event identity through EventIdentityResolver.
    resolver = EventIdentityResolver()
    canonical = resolver.resolve(final_raw, "radio")
    assert canonical is not None
    assert canonical == final_event_id

    # Observation immutable_id == canonical Event identity.
    repo = ObservationRepository(get_session_manager().get_session())
    obs = repo.get_by_immutable_id(final_event_id)
    assert obs is not None
    assert obs.immutable_id == canonical
