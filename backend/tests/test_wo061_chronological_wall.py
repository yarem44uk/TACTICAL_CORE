"""WO-061 — Chronological Operational Wall.

Proves the real architectural seam:

    persisted observation -> WO-060 read model -> operator /observations
    endpoint -> Wall-consumable response.

The Wall is a pure frontend consumer of the verified WO-060 observation read
model.  It must NOT consume ``/events`` or ``/events/stream``, must NOT reorder
the server's deterministic chronology (occurred_at DESC, timestamp DESC,
id DESC), must stay GET-only and operator-prefixed, and must preserve
``radio.recording`` evidence (WO-062 contract).

No browser harness exists in the repository, so frontend invariants are
verified statically against the served static assets.  The core integration
assertions use the real production composition (no mocks of the observation
repository).
"""

from __future__ import annotations

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
from app.intelligence.observation.repository import (
    SessionManagerObservationRepository,
)
from app.operator.app import STATIC_DIR


# ---------------------------------------------------------------------------
# Helpers (mirror the WO-060 production-composition seam; no mocks).
# ---------------------------------------------------------------------------


def _reset() -> None:
    session_mod._session_manager = None


def _url(db_path: str) -> str:
    return f"sqlite:///{db_path}"


def _make_event(
    event_id: str,
    occurred_at: datetime,
    *,
    source: str = "radio",
    payload: dict | None = None,
) -> Event:
    """Build a canonical Event with a deterministic occurred_at (event time)."""
    return Event(
        event_id=event_id,
        event_type=EventType.CUSTOM,
        timestamp=occurred_at,
        source=source,
        payload=payload or {"frequency": 100.5, "callsign": "BRAVO"},
        metadata=EventMetadata(),
    )


def _recording_payload(rid: str) -> dict:
    """A WO-058 radio recording payload (no frequency/callsign)."""
    return {
        "occurred_at": "2026-09-03T12:00:00Z",
        "audio_recording_id": rid,
        "content_id": "content-" + rid,
        "recording": {
            "wav_path": f"/tmp/{rid}.wav",
            "mp3_path": f"/tmp/{rid}.mp3",
            "format": "wav",
            "duration_ms": 30000,
            "duration": 30.0,
            "source": "radio",
            "sha256": "a" * 64,
            "complete": False,
            "finalize_reason": "source_shutdown",
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


def _operator_client(mgr):
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


# ---------------------------------------------------------------------------
# Test 1 — Observation API chronology (newest-first, server order authoritative).
# ---------------------------------------------------------------------------


def test_observation_api_chronology_newest_first(file_db):
    mgr = configure_session_manager(_url(file_db))
    Base.metadata.create_all(mgr.engine)
    rt = _compose(_url(file_db))

    # Arrival order is reverse of event-time order, proving the read model
    # orders by occurred_at DESC, not by insertion order.
    assert _process(
        rt,
        _make_event(
            "e-early",
            datetime(2026, 8, 17, 11, 0, 0, tzinfo=timezone.utc),
            payload=_recording_payload("rec-early"),
        ),
    ) is True
    assert _process(
        rt,
        _make_event(
            "e-late",
            datetime(2026, 8, 17, 12, 0, 0, tzinfo=timezone.utc),
            payload=_recording_payload("rec-late"),
        ),
    ) is True

    client = _operator_client(mgr)
    resp = client.get("/api/v1/operator/observations")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 2
    # The backend chronology is authoritative and must be preserved verbatim.
    assert [o["immutable_id"] for o in body["observations"]] == ["e-late", "e-early"]
    assert [o["occurred_at"] for o in body["observations"]] == [
        "2026-08-17T12:00:00",
        "2026-08-17T11:00:00",
    ]
    _reset()


# ---------------------------------------------------------------------------
# Test 2 — radio.recording survives to the Wall data (real composition).
# ---------------------------------------------------------------------------


def test_radio_recording_survives_to_wall_data(file_db):
    mgr = configure_session_manager(_url(file_db))
    Base.metadata.create_all(mgr.engine)
    rt = _compose(_url(file_db))

    assert _process(
        rt,
        _make_event(
            "e-rec",
            datetime(2026, 8, 17, 12, 0, 0, tzinfo=timezone.utc),
            payload=_recording_payload("rec-1"),
        ),
    ) is True

    client = _operator_client(mgr)
    resp = client.get("/api/v1/operator/observations")
    assert resp.status_code == 200, resp.text
    obs = resp.json()["observations"][0]
    assert obs["immutable_id"] == "e-rec"
    assert obs["source"] == "radio"
    assert obs["observation_type"] == "radio"
    assert obs["occurred_at"] == "2026-08-17T12:00:00"
    assert obs["timestamp"] != obs["occurred_at"]
    # WO-062 contract: recording evidence + identity survive the read model.
    rec = obs["evidence_payload"]["raw_data"]["recording"]
    assert rec["wav_path"] == "/tmp/rec-1.wav"
    assert rec["mp3_path"] == "/tmp/rec-1.mp3"
    assert rec["sha256"] == "a" * 64
    assert rec["duration"] == 30.0
    assert rec["duration_ms"] == 30000
    assert rec["complete"] is False
    assert obs["evidence_payload"]["raw_data"]["audio_recording_id"] == "rec-1"
    assert obs["evidence_payload"]["raw_data"]["content_id"] == "content-rec-1"
    _reset()


# ---------------------------------------------------------------------------
# Test 3 — Static Wall integration (shell + JS wiring).
# ---------------------------------------------------------------------------


def test_static_wall_integration():
    html = (STATIC_DIR / "index.html").read_text()
    js = (STATIC_DIR / "operator.js").read_text()

    # Wall view / tab / container present in the shell.
    assert 'id="tab-wall"' in html
    assert "Wall" in html
    assert 'id="view-wall"' in html
    assert 'id="wall-feed"' in html
    assert 'id="wl-load-more"' in html

    # Wall consumes the observation API via GET + the existing withAuth().
    assert "/observations" in js
    assert "method: \"GET\"" in js
    assert "withAuth(" in js
    # Operator-prefix only, via the shared base.
    assert 'var API = "/api/v1/operator";' in js
    # The wall must not reorder the server's chronology client-side.
    assert ".sort(" not in js


# ---------------------------------------------------------------------------
# Test 4 — No forbidden live-stream dependency.
# ---------------------------------------------------------------------------


def test_wall_no_forbidden_live_stream_dependency():
    js = (STATIC_DIR / "operator.js").read_text()
    # The wall must NOT depend on the canonical event stream.
    assert "EventSource" not in js
    assert "/events/stream" not in js
    assert "text/event-stream" not in js
    # The wall's only observation data source is /observations.
    assert "/observations" in js


# ---------------------------------------------------------------------------
# Test 5 — Existing UI invariants preserved by the additive Wall.
# ---------------------------------------------------------------------------


def test_wall_preserves_ui_invariants():
    html = (STATIC_DIR / "index.html").read_text()
    js = (STATIC_DIR / "operator.js").read_text()
    css = (STATIC_DIR / "operator.css").read_text()
    blob = html + "\n" + css + "\n" + js

    # No external network resources.
    assert "http://" not in blob
    assert "https://" not in blob
    assert re.search(r'(?<![\w:"\']/)//[A-Za-z]', blob) is None

    # GET-only: every fetch carries method GET.
    fetches = re.findall(r"fetch\([^)]*\)", js)
    assert fetches, "expected at least one fetch() in operator.js"
    for f in fetches:
        if "method:" in f:
            assert "GET" in f, f"non-GET fetch found: {f}"

    # No mutation methods.
    for method in ["POST", "PUT", "PATCH", "DELETE"]:
        assert f'"{method}"' not in js
        assert f"'{method}'" not in js

    # Operator-prefix only.
    api_refs = set(re.findall(r"/api/v1/operator/[a-z_/\{\}]*", js))
    assert api_refs, "expected operator API references in operator.js"
    for ref in api_refs:
        assert ref.startswith("/api/v1/operator/")

    # No external CSS/fonts.
    assert "@import" not in css
    assert "url(" not in css
