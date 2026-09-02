"""WO-037-06 tests: Baseline operational severity classifier.

Covers the ratified SEVERITY-RULES-v1.0.0 ruleset (ADR-012, Accepted):

  * the four executable rules (CAND-002 / CAND-004 / CAND-005 / CAND-006);
  * CAND-004 limitation (payload content is NOT classified);
  * unmapped events -> UNCLASSIFIED, and UNCLASSIFIED != INFO;
  * CAND-001 / CAND-003 are NOT_IMPLEMENTED;
  * determinism / replayability / offline / read-only;
  * no Event / DurableCanonicalEvent schema change;
  * no priority / urgency / confidence -> severity conversion;
  * precedence (EVENT-SPECIFIC > SOURCE-SPECIFIC > GENERIC) and the
    NO SILENT RESOLUTION invariant;
  * operator (REST) severity exposure + filtering;
  * SSE severity-in-frame and severity filtering, with the auth boundary
    preserved (WO-037-05 non-regression);
  * core isolation (the classifier is consumer-side, never imports the
    durable engine).
"""

from __future__ import annotations

import dataclasses
import json
import os
import subprocess
import sys
import tempfile

import httpx
import pytest

from app.database.session import DatabaseSessionManager
from app.entity_relations.sqlalchemy_relation_repository import (
    SQLAlchemyRelationRepository,
)
from app.entity_repository.sqlalchemy_entity_repository import (
    SQLAlchemyEntityRepository,
)
from app.event.event import Event
from app.event.event_metadata import EventMetadata
from app.event.event_types import EventType
from app.event_repository.durable.durable_event_model import (
    DurableCanonicalEvent,
)
from app.event_repository.durable.sqlalchemy_event_repository import (
    SQLAlchemyEventRepository,
)
from app.operator.app import create_operator_app
import app.operator.severity as severity_module
from app.operator.severity import (
    RATIFIED_RULES,
    RULESET_VERSION,
    BaselineRule,
    Severity,
    SeverityConflictError,
    _resolve,
    classify,
    classify_facts,
)
from app.operator.service import OperatorService

EVENTS_URL = "/api/v1/operator/events"
STREAM_URL = "/api/v1/operator/events/stream"


def _make_event(
    *,
    event_id: str,
    event_type: EventType = EventType.CUSTOM,
    source: str = "test",
    payload: dict | None = None,
) -> Event:
    return Event(
        event_id=event_id,
        entity_id=f"entity-{event_id}",
        event_type=event_type,
        source=source,
        payload=payload if payload is not None else {"k": "v"},
        metadata=EventMetadata(),
    )


# ============================================================================
# Classifier — the four ratified executable rules
# ============================================================================


def test_cand002_exact_match() -> None:
    assert classify_facts("signal.failed", "signal") == Severity.WARNING


def test_cand002_wrong_source_does_not_match() -> None:
    # The condition requires source == "signal"; any other source is NOT a
    # match, and no other rule covers signal.failed -> UNCLASSIFIED.
    assert classify_facts("signal.failed", "telegram") == Severity.UNCLASSIFIED
    assert classify_facts("signal.failed", "radio") == Severity.UNCLASSIFIED


def test_cand004_exact_match() -> None:
    # CAND-004 is source-agnostic: event_type == observation.verified -> INFO.
    assert classify_facts("observation.verified", "any-source") == Severity.INFO
    assert classify_facts("observation.verified", "") == Severity.INFO


def test_cand005_exact_match() -> None:
    assert classify_facts("relation.severed", "x") == Severity.INFO


def test_cand006_exact_match() -> None:
    assert classify_facts("system.startup", "x") == Severity.INFO


def test_ruleset_has_exactly_four_ratified_rules() -> None:
    ids = {r.rule_id for r in RATIFIED_RULES}
    assert ids == {"CAND-002", "CAND-004", "CAND-005", "CAND-006"}
    assert len(RATIFIED_RULES) == 4


# ============================================================================
# CAND-004 limitation — payload content is NOT classified
# ============================================================================


def test_cand004_payload_content_does_not_affect_baseline() -> None:
    """A verified observation is INFO regardless of its payload content.

    The baseline classifier must not inspect message_text / MQTT body /
    Telegram text / ATAK free-form / radio free text. Content-based
    threat/criticality analysis is out of scope (CAND-004 limitation).
    """
    benign = _make_event(
        event_id="e-obs-benign",
        event_type=EventType.OBSERVATION_VERIFIED,
        source="signal",
        payload={"message_text": "all clear, no movement"},
    )
    hostile = _make_event(
        event_id="e-obs-hostile",
        event_type=EventType.OBSERVATION_VERIFIED,
        source="signal",
        payload={
            "message_text": "CRITICAL: inbound strike imminent",
            "mqtt_body": "alert red alarm 90",
            "atak_metadata": {"freeform": "threat critical"},
        },
    )
    # Both classify as INFO purely from event_type — payload never inspected.
    assert classify(benign) == Severity.INFO
    assert classify(hostile) == Severity.INFO
    assert classify_facts("observation.verified", "signal") == Severity.INFO


def test_cand004_limitation_no_content_scoring() -> None:
    # The classifier only consumes (event_type, source) facts; it cannot
    # produce a different severity from a more alarming payload.
    for payload in (
        {"text": "quiet"},
        {"text": "RED ALERT CRITICAL URGENT 90"},
        {"freeform": "attack imminent"},
    ):
        ev = _make_event(
            event_id=f"e-{abs(hash(str(payload)))}",
            event_type=EventType.OBSERVATION_VERIFIED,
            source="atak",
            payload=payload,
        )
        assert classify(ev) == Severity.INFO


# ============================================================================
# Unmapped -> UNCLASSIFIED, and UNCLASSIFIED != INFO
# ============================================================================


@pytest.mark.parametrize(
    "event_type",
    [
        "system.error",
        "observation.retracted",
        "signal.received",
        "signal.processed",
        "entity.created",
        "entity.updated",
        "entity.removed",
        "observation.created",
        "system.shutdown",
        "custom",
        "mqtt",
        "radio",
        "telegram",
        "atak",
        "unknown.type",
    ],
)
def test_unmapped_event_is_unclassified(event_type: str) -> None:
    assert classify_facts(event_type, "signal") == Severity.UNCLASSIFIED


def test_unclassified_is_not_info() -> None:
    assert Severity.UNCLASSIFIED != Severity.INFO
    assert classify_facts("entity.created", "x") == Severity.UNCLASSIFIED
    assert classify_facts("entity.created", "x") != Severity.INFO


def test_no_silent_unclassified_to_info_conversion() -> None:
    # An unmapped event must NOT be silently upgraded to INFO.
    ev = _make_event(
        event_id="e-unmapped",
        event_type=EventType.ENTITY_CREATED,
        source="radio",
    )
    assert classify(ev) == Severity.UNCLASSIFIED
    assert classify(ev).value == "UNCLASSIFIED"


# ============================================================================
# Non-executable rules (CAND-001 / CAND-003) are NOT implemented
# ============================================================================


def test_cand001_system_error_is_not_critical() -> None:
    # CAND-001 (system.error -> CRITICAL) is NOT_EXECUTABLE: the event type
    # name alone must not be interpreted as CRITICAL.
    assert classify_facts("system.error", "system") == Severity.UNCLASSIFIED
    assert classify_facts("system.error", "system") != Severity.CRITICAL


def test_cand003_observation_retracted_is_not_warning() -> None:
    # CAND-003 (observation.retracted -> WARNING) is NOT_EXECUTABLE.
    assert classify_facts("observation.retracted", "x") == Severity.UNCLASSIFIED
    assert classify_facts("observation.retracted", "x") != Severity.WARNING


# ============================================================================
# Determinism / replayability
# ============================================================================


def test_deterministic_repeated_evaluation() -> None:
    facts = [
        ("signal.failed", "signal", Severity.WARNING),
        ("observation.verified", "signal", Severity.INFO),
        ("relation.severed", "x", Severity.INFO),
        ("system.startup", "x", Severity.INFO),
        ("entity.created", "x", Severity.UNCLASSIFIED),
    ]
    for event_type, source, expected in facts:
        results = {classify_facts(event_type, source) for _ in range(50)}
        assert results == {expected}


def test_replay_invariant_same_facts_same_severity() -> None:
    # SEVERITY-RULES-v1.0.0 §12: same facts + same ruleset version =>
    # same severity, independent of operator state / time / network.
    a = classify_facts("signal.failed", "signal")
    b = classify_facts("signal.failed", "signal")
    assert a == b == Severity.WARNING


def test_ruleset_version_consumed() -> None:
    # The classifier is versioned by a Git-controlled constant.
    assert RULESET_VERSION == "SEVERITY-RULES-v1.0.0"
    assert RULESET_VERSION.startswith("SEVERITY-RULES-v")


# ============================================================================
# No schema change (Event / DurableCanonicalEvent)
# ============================================================================


def test_no_event_schema_change() -> None:
    field_names = {f.name for f in dataclasses.fields(Event)}
    assert "severity" not in field_names


def test_no_durable_canonical_event_schema_change() -> None:
    column_names = {c.name for c in DurableCanonicalEvent.__table__.columns}
    assert "severity" not in column_names
    assert "severity" not in DurableCanonicalEvent.__table__.columns.keys()


def test_classify_is_read_only_no_mutation() -> None:
    ev = _make_event(
        event_id="e-ro", event_type=EventType.SIGNAL_FAILED, source="signal"
    )
    before = ev.to_dict()
    classify(ev)
    assert ev.to_dict() == before  # event unchanged
    assert "severity" not in before  # severity is not persisted onto the event


# ============================================================================
# No priority / urgency / confidence -> severity conversion
# ============================================================================


def test_no_priority_urgency_confidence_conversion() -> None:
    # These are independent dimensions (SEVERITY-RULES-v1.0.0 §13). Their
    # presence in the payload must never change the derived severity.
    ev = _make_event(
        event_id="e-dim",
        event_type=EventType.ENTITY_CREATED,
        source="signal",
        payload={
            "priority": "high",
            "urgency": "urgent",
            "confidence": 0.99,
            "vendor_severity": "critical",
        },
    )
    assert classify(ev) == Severity.UNCLASSIFIED
    # And for a mapped event, the payload dimensions do not change severity.
    ev2 = _make_event(
        event_id="e-dim2",
        event_type=EventType.SIGNAL_FAILED,
        source="signal",
        payload={"priority": "low", "urgency": "low", "confidence": 0.1},
    )
    assert classify(ev2) == Severity.WARNING


# ============================================================================
# Precedence + NO SILENT RESOLUTION
# ============================================================================


def test_precedence_event_specific_beats_generic() -> None:
    rules = [
        BaselineRule("GEN", None, None, Severity.INFO),  # GENERIC
        BaselineRule("SPEC", "x", "y", Severity.WARNING),  # EVENT+SOURCE
    ]
    assert _resolve(rules, "x", "y") == Severity.WARNING


def test_precedence_event_specific_beats_source_specific() -> None:
    rules = [
        BaselineRule("SRC", None, "y", Severity.INFO),  # SOURCE-SPECIFIC
        BaselineRule("EVT", "x", None, Severity.WARNING),  # EVENT-SPECIFIC
    ]
    assert _resolve(rules, "x", "y") == Severity.WARNING


def test_precedence_source_specific_beats_generic() -> None:
    rules = [
        BaselineRule("GEN", None, None, Severity.INFO),  # GENERIC
        BaselineRule("SRC", None, "y", Severity.WARNING),  # SOURCE-SPECIFIC
    ]
    assert _resolve(rules, "x", "y") == Severity.WARNING


def test_equal_specificity_conflict_raises_no_silent_resolution() -> None:
    # Two rules of equal specificity (both EVENT+SOURCE) matching the same
    # event => NO SILENT RESOLUTION => SeverityConflictError.
    rules = [
        BaselineRule("R1", "x", "y", Severity.WARNING),
        BaselineRule("R2", "x", "y", Severity.INFO),
    ]
    with pytest.raises(SeverityConflictError):
        _resolve(rules, "x", "y")


def test_equal_event_specific_conflict_raises() -> None:
    rules = [
        BaselineRule("R1", "x", None, Severity.WARNING),
        BaselineRule("R2", "x", None, Severity.INFO),
    ]
    with pytest.raises(SeverityConflictError):
        _resolve(rules, "x", "y")


def test_ratified_ruleset_produces_no_conflict() -> None:
    # The four ratified rules have distinct event_types, so no event can
    # trigger a same-specificity conflict. Verify this invariant directly.
    for event_type in {"signal.failed", "observation.verified",
                       "relation.severed", "system.startup"}:
        # classify_facts must not raise for any mapped event.
        classify_facts(event_type, "signal")


# ============================================================================
# Offline operation + core isolation
# ============================================================================


def _run_subprocess_check(script: str) -> str:
    """Run a Python snippet in a clean interpreter and return its stdout."""
    env = dict(os.environ)
    env["PYTHONPATH"] = os.path.join(
        os.path.dirname(__file__), "..", "..", "backend"
    )
    proc = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        env=env,
        cwd=os.path.join(os.path.dirname(__file__), "..", ".."),
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


def test_core_isolation_no_durable_engine_import() -> None:
    # The consumer-side classifier must never import the durable engine.
    out = _run_subprocess_check(
        "import sys; "
        "import app.operator.severity; "
        "import app.operator.service; "
        "core = [m for m in sys.modules if m.startswith('app.event_pipeline')"
        " or m.startswith('app.event_delivery.delivery_dispatcher')"
        " or m.startswith('app.event_service')"
        " or m.startswith('app.projection')]; "
        "print('CORE_LOADED:' + ','.join(sorted(core)))"
    )
    assert out.strip() == "CORE_LOADED:"


def test_offline_operation_no_network_dependency() -> None:
    # The classifier is a pure, deterministic function of the event's facts
    # and the Git-versioned ruleset. It must not depend on any network, cloud
    # service or external API. Verify the severity module's own import
    # statements contain no network/cloud client, and that classification
    # works offline.
    import ast
    import pathlib

    src = pathlib.Path(str(severity_module.__file__)).read_text(encoding="utf-8")
    tree = ast.parse(src)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[0])
    forbidden = {
        "requests",
        "httpx",
        "aiohttp",
        "boto3",
        "urllib",
        "socket",
        "http.client",
        "ssl",
    }
    assert not (imported & forbidden), imported & forbidden
    # The classifier runs offline and deterministically.
    assert classify_facts("signal.failed", "signal") == Severity.WARNING
    assert classify_facts("entity.created", "x") == Severity.UNCLASSIFIED


# ============================================================================
# Operator (REST) integration — expose + filter derived severity
# ============================================================================


@pytest.fixture()
def db_path() -> str:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.remove(path)


@pytest.fixture()
def session_manager(db_path: str) -> DatabaseSessionManager:
    # File-based SQLite (not in-memory) so the same DB is safely usable from
    # the asyncio event-loop thread as well as the test thread.
    manager = DatabaseSessionManager(database_url=f"sqlite:///{db_path}", echo=False)
    manager.initialize()
    yield manager
    manager.close()


@pytest.fixture()
def repos(session_manager: DatabaseSessionManager):
    event_repo = SQLAlchemyEventRepository(session_manager=session_manager)
    event_repo.initialize()
    entity_repo = SQLAlchemyEntityRepository(session_manager=session_manager)
    entity_repo.initialize()
    relation_repo = SQLAlchemyRelationRepository(session_manager=session_manager)
    relation_repo.initialize()
    return event_repo, entity_repo, relation_repo


@pytest.fixture()
def event_repo(repos) -> SQLAlchemyEventRepository:
    return repos[0]


@pytest.fixture()
def service(repos) -> OperatorService:
    event_repo, entity_repo, relation_repo = repos
    return OperatorService(
        event_repository=event_repo,
        entity_repository=entity_repo,
        relation_repository=relation_repo,
    )


def test_service_exposes_derived_severity(service: OperatorService) -> None:
    service._events.save(
        _make_event(
            event_id="e1",
            event_type=EventType.SIGNAL_FAILED,
            source="signal",
        )
    )
    result = service.list_events()
    assert result["events"][0]["severity"] == "WARNING"


def test_service_severity_filter(service: OperatorService) -> None:
    service._events.save(
        _make_event(
            event_id="e-warn",
            event_type=EventType.SIGNAL_FAILED,
            source="signal",
        )
    )
    service._events.save(
        _make_event(
            event_id="e-info",
            event_type=EventType.SYSTEM_STARTUP,
            source="system",
        )
    )
    service._events.save(
        _make_event(
            event_id="e-unclass",
            event_type=EventType.ENTITY_CREATED,
            source="radio",
        )
    )
    warn = service.list_events(severity="WARNING")
    assert [e["event_id"] for e in warn["events"]] == ["e-warn"]
    info = service.list_events(severity="info")  # case-insensitive
    assert [e["event_id"] for e in info["events"]] == ["e-info"]
    unclass = service.list_events(severity="UNCLASSIFIED")
    assert [e["event_id"] for e in unclass["events"]] == ["e-unclass"]


def test_service_severity_filter_does_not_mutate_events(
    service: OperatorService,
) -> None:
    service._events.save(
        _make_event(
            event_id="e1",
            event_type=EventType.SIGNAL_FAILED,
            source="signal",
            payload={"priority": "high"},
        )
    )
    before = service._events.count()
    result = service.list_events(severity="WARNING")
    assert result["events"][0]["severity"] == "WARNING"
    assert service._events.count() == before


def test_service_invalid_severity_rejected(service: OperatorService) -> None:
    from app.operator.service import InvalidRequestError

    with pytest.raises(InvalidRequestError):
        service.list_events(severity="not-a-severity")


def test_service_unclassified_not_info_on_operator_view(
    service: OperatorService,
) -> None:
    service._events.save(
        _make_event(
            event_id="e-unclass",
            event_type=EventType.ENTITY_CREATED,
            source="radio",
        )
    )
    result = service.list_events()
    assert result["events"][0]["severity"] == "UNCLASSIFIED"


def test_get_event_includes_derived_severity(service: OperatorService) -> None:
    service._events.save(
        _make_event(
            event_id="e1",
            event_type=EventType.OBSERVATION_VERIFIED,
            source="signal",
        )
    )
    data = service.get_event("e1")
    assert data["severity"] == "INFO"


# ============================================================================
# Operator HTTP / auth non-regression
# ============================================================================


@pytest.fixture()
def app(repos):
    event_repo, entity_repo, relation_repo = repos
    return create_operator_app(
        event_repository=event_repo,
        entity_repository=entity_repo,
        relation_repository=relation_repo,
    )


async def _get(app, url: str, headers=None) -> tuple[int, dict]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        response = await client.get(url, headers=headers)
        try:
            body = response.json()
        except ValueError:
            body = {}
        return response.status_code, body


async def _get_sse(app, url: str, headers=None) -> tuple[int, bytes]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        async with client.stream("GET", url, headers=headers) as response:
            body = b"".join([chunk async for chunk in response.aiter_bytes()])
            return response.status_code, body


def _parse_sse_frames(body: bytes) -> list:
    frames = []
    for block in body.decode("utf-8").split("\n\n"):
        block = block.strip()
        if not block or block.startswith(":"):
            continue
        data = None
        for line in block.split("\n"):
            if line.startswith("data:"):
                raw = line.split(":", 1)[1].strip()
                if raw:
                    data = json.loads(raw)
        if data is not None:
            frames.append(data)
    return frames


@pytest.mark.asyncio
async def test_http_events_include_severity(app, event_repo) -> None:
    event_repo.save(
        _make_event(
            event_id="e1",
            event_type=EventType.SIGNAL_FAILED,
            source="signal",
        )
    )
    status, body = await _get(app, EVENTS_URL)
    assert status == 200
    assert body["events"][0]["severity"] == "WARNING"


@pytest.mark.asyncio
async def test_http_events_severity_filter(app, event_repo) -> None:
    event_repo.save(
        _make_event(
            event_id="e-warn",
            event_type=EventType.SIGNAL_FAILED,
            source="signal",
        )
    )
    event_repo.save(
        _make_event(
            event_id="e-info",
            event_type=EventType.SYSTEM_STARTUP,
            source="system",
        )
    )
    status, body = await _get(app, f"{EVENTS_URL}?severity=WARNING")
    assert status == 200
    assert [e["event_id"] for e in body["events"]] == ["e-warn"]


@pytest.mark.asyncio
async def test_http_events_invalid_severity_returns_400(app) -> None:
    status, body = await _get(app, f"{EVENTS_URL}?severity=bogus")
    assert status == 400
    assert body["error_type"] == "InvalidRequestError"


@pytest.mark.asyncio
async def test_http_get_event_has_severity(app, event_repo) -> None:
    event_repo.save(
        _make_event(
            event_id="e1",
            event_type=EventType.OBSERVATION_VERIFIED,
            source="signal",
        )
    )
    status, body = await _get(app, f"{EVENTS_URL}/e1")
    assert status == 200
    assert body["severity"] == "INFO"


@pytest.mark.asyncio
async def test_auth_boundary_preserved_with_severity(app_enabled) -> None:
    # The derived-severity addition must NOT weaken WO-037-05 auth.
    status, body = await _get(app_enabled, EVENTS_URL)
    assert status == 401
    status2, body2 = await _get(app_enabled, f"{EVENTS_URL}?severity=WARNING")
    assert status2 == 401


@pytest.fixture()
def app_enabled(repos):
    from app.operator.auth import OperatorAuthGate

    event_repo, entity_repo, relation_repo = repos
    return create_operator_app(
        event_repository=event_repo,
        entity_repository=entity_repo,
        relation_repository=relation_repo,
        auth_gate=OperatorAuthGate(token="test-token"),
    )


# ============================================================================
# SSE integration — severity in frames + filtering, boundary preserved
# ============================================================================


@pytest.mark.asyncio
async def test_sse_frames_include_severity(app, event_repo) -> None:
    event_repo.save(
        _make_event(
            event_id="e1",
            event_type=EventType.SIGNAL_FAILED,
            source="signal",
        )
    )
    status, body = await _get_sse(app, f"{STREAM_URL}?stream_ticks=0")
    assert status == 200
    frames = _parse_sse_frames(body)
    assert len(frames) == 1
    assert frames[0]["event"]["severity"] == "WARNING"


@pytest.mark.asyncio
async def test_sse_severity_filter(app, event_repo) -> None:
    event_repo.save(
        _make_event(
            event_id="e-warn",
            event_type=EventType.SIGNAL_FAILED,
            source="signal",
        )
    )
    event_repo.save(
        _make_event(
            event_id="e-info",
            event_type=EventType.SYSTEM_STARTUP,
            source="system",
        )
    )
    status, body = await _get_sse(
        app, f"{STREAM_URL}?severity=WARNING&stream_ticks=0"
    )
    assert status == 200
    frames = _parse_sse_frames(body)
    assert len(frames) == 1
    assert frames[0]["event"]["event_id"] == "e-warn"


@pytest.mark.asyncio
async def test_sse_severity_filter_omitted_emits_all(app, event_repo) -> None:
    # Backwards compatibility: no severity param emits every event.
    event_repo.save(
        _make_event(
            event_id="e-warn",
            event_type=EventType.SIGNAL_FAILED,
            source="signal",
        )
    )
    event_repo.save(
        _make_event(
            event_id="e-info",
            event_type=EventType.SYSTEM_STARTUP,
            source="system",
        )
    )
    status, body = await _get_sse(app, f"{STREAM_URL}?stream_ticks=0")
    assert status == 200
    frames = _parse_sse_frames(body)
    assert len(frames) == 2


@pytest.mark.asyncio
async def test_sse_invalid_severity_returns_400(app) -> None:
    status, body = await _get_sse(
        app, f"{STREAM_URL}?severity=bogus&stream_ticks=0"
    )
    assert status == 400


@pytest.mark.asyncio
async def test_sse_filtering_does_not_mutate_authoritative_state(
    app, event_repo
) -> None:
    event_repo.save(
        _make_event(
            event_id="e-warn",
            event_type=EventType.SIGNAL_FAILED,
            source="signal",
        )
    )
    before = event_repo.count()
    await _get_sse(app, f"{STREAM_URL}?severity=WARNING&stream_ticks=0")
    assert event_repo.count() == before
