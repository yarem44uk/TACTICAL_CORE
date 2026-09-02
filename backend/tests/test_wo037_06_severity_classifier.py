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
import pathlib
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
    RULES,
    RULESET_PATH,
    RULESET_STATUS,
    RULESET_VERSION,
    BaselineRule,
    RulesetLoadError,
    Severity,
    SeverityConflictError,
    _resolve,
    classify,
    classify_facts,
    load_ruleset,
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
    # The rules are loaded from the authoritative machine-readable TOML
    # (WO-037-07); there is no independent hardcoded copy in Python.
    ids = {r.rule_id for r in RULES}
    assert ids == {"CAND-002", "CAND-004", "CAND-005", "CAND-006"}
    assert len(RULES) == 4


def test_source_wildcard_maps_to_none() -> None:
    # machine-readable source = "*" -> runtime BaselineRule.source = None.
    by_id = {r.rule_id: r for r in RULES}
    assert by_id["CAND-002"].source == "signal"
    assert by_id["CAND-004"].source is None
    assert by_id["CAND-005"].source is None
    assert by_id["CAND-006"].source is None


def test_non_executable_rules_not_executable() -> None:
    # CAND-001 / CAND-003 must never appear in the executable rule set.
    ids = {r.rule_id for r in RULES}
    assert "CAND-001" not in ids
    assert "CAND-003" not in ids
    assert set(severity_module.NON_EXECUTABLE_RULE_IDS) == {"CAND-001", "CAND-003"}


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


# ============================================================================
# WO-037-07 — Ruleset loader, integrity, version binding, fail-closed
# ============================================================================


_VALID_TOML = '''[ruleset]
version = "SEVERITY-RULES-v1.0.0"
status = "RATIFIED_FOR_CONSUMPTION"
governing_adr = "ADR-012"

[[rules]]
rule_id = "CAND-002"
event_type = "signal.failed"
source = "signal"
severity = "WARNING"
status = "RATIFIED"

[[rules]]
rule_id = "CAND-004"
event_type = "observation.verified"
source = "*"
severity = "INFO"
status = "RATIFIED_WITH_LIMITATION"
limitation = "Payload content is not classified."

[[rules]]
rule_id = "CAND-005"
event_type = "relation.severed"
source = "*"
severity = "INFO"
status = "RATIFIED"

[[rules]]
rule_id = "CAND-006"
event_type = "system.startup"
source = "*"
severity = "INFO"
status = "RATIFIED"

[[non_executable]]
rule_id = "CAND-001"
status = "NOT_EXECUTABLE"
reason = "No deterministic criticality fact."

[[non_executable]]
rule_id = "CAND-003"
status = "NOT_EXECUTABLE"
reason = "No deterministic correction discriminator."
'''


def _sha256_text(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _write_ruleset(tmp_path, toml_text: str, *, sidecar: str | None = None):
    """Write a TOML ruleset + (by default) a correct SHA-256 sidecar."""
    toml_path = tmp_path / "SEVERITY_RULES_v1.0.0.toml"
    toml_path.write_text(toml_text, encoding="utf-8")
    sidecar_path = tmp_path / "SEVERITY_RULES_v1.0.0.toml.sha256"
    if sidecar is None:
        sidecar = _sha256_text(toml_text)
    sidecar_path.write_text(sidecar + "\n", encoding="utf-8")
    return toml_path


def test_load_ruleset_success(tmp_path) -> None:
    rules, version, status, ne_ids = load_ruleset(_write_ruleset(tmp_path, _VALID_TOML))
    assert version == "SEVERITY-RULES-v1.0.0"
    assert status == "RATIFIED_FOR_CONSUMPTION"
    assert {r.rule_id for r in rules} == {"CAND-002", "CAND-004", "CAND-005", "CAND-006"}
    assert set(ne_ids) == {"CAND-001", "CAND-003"}
    assert len(rules) == 4


def test_load_ruleset_missing_artifact(tmp_path) -> None:
    with pytest.raises(RulesetLoadError):
        load_ruleset(tmp_path / "SEVERITY_RULES_v1.0.0.toml")


def test_load_ruleset_malformed_toml(tmp_path) -> None:
    bad = "this is not [valid toml"
    toml_path = tmp_path / "SEVERITY_RULES_v1.0.0.toml"
    toml_path.write_text(bad, encoding="utf-8")
    (tmp_path / "SEVERITY_RULES_v1.0.0.toml.sha256").write_text(
        _sha256_text(bad) + "\n", encoding="utf-8"
    )
    with pytest.raises(RulesetLoadError):
        load_ruleset(toml_path)


def test_load_ruleset_invalid_severity(tmp_path) -> None:
    toml_text = _VALID_TOML.replace('severity = "WARNING"', 'severity = "EXTREME"')
    with pytest.raises(RulesetLoadError):
        load_ruleset(_write_ruleset(tmp_path, toml_text))


def test_load_ruleset_duplicate_rule_id(tmp_path) -> None:
    toml_text = _VALID_TOML.replace(
        'rule_id = "CAND-006"', 'rule_id = "CAND-002"'
    )
    with pytest.raises(RulesetLoadError):
        load_ruleset(_write_ruleset(tmp_path, toml_text))


def test_load_ruleset_unknown_field(tmp_path) -> None:
    toml_text = _VALID_TOML.replace(
        'status = "RATIFIED"', 'status = "RATIFIED"\nextra_field = "bogus"'
    )
    with pytest.raises(RulesetLoadError):
        load_ruleset(_write_ruleset(tmp_path, toml_text))


def test_load_ruleset_missing_required_field(tmp_path) -> None:
    # Remove the required `source` field from CAND-002 -> schema-invalid.
    toml_text = _VALID_TOML.replace('source = "signal"', '')
    with pytest.raises(RulesetLoadError):
        load_ruleset(_write_ruleset(tmp_path, toml_text))


def test_load_ruleset_event_type_wildcard_rejected(tmp_path) -> None:
    toml_text = _VALID_TOML.replace(
        'event_type = "signal.failed"', 'event_type = "*"'
    )
    with pytest.raises(RulesetLoadError):
        load_ruleset(_write_ruleset(tmp_path, toml_text))


def test_load_ruleset_filename_version_mismatch(tmp_path) -> None:
    toml_text = _VALID_TOML.replace(
        'version = "SEVERITY-RULES-v1.0.0"', 'version = "SEVERITY-RULES-v1.0.1"'
    )
    with pytest.raises(RulesetLoadError):
        load_ruleset(_write_ruleset(tmp_path, toml_text))


def test_load_ruleset_invalid_version_format(tmp_path) -> None:
    toml_text = _VALID_TOML.replace(
        'version = "SEVERITY-RULES-v1.0.0"', 'version = "not-a-version"'
    )
    with pytest.raises(RulesetLoadError):
        load_ruleset(_write_ruleset(tmp_path, toml_text))


def test_load_ruleset_sha256_mismatch(tmp_path) -> None:
    toml_path = _write_ruleset(
        tmp_path, _VALID_TOML, sidecar="0" * 64
    )
    with pytest.raises(RulesetLoadError):
        load_ruleset(toml_path)


def test_load_ruleset_missing_sidecar(tmp_path) -> None:
    toml_path = tmp_path / "SEVERITY_RULES_v1.0.0.toml"
    toml_path.write_text(_VALID_TOML, encoding="utf-8")
    with pytest.raises(RulesetLoadError):
        load_ruleset(toml_path)


def test_load_ruleset_cand001_not_executable(tmp_path) -> None:
    # CAND-001 must only ever be a non-executable record.
    rules, _, _, ne_ids = load_ruleset(_write_ruleset(tmp_path, _VALID_TOML))
    assert "CAND-001" not in {r.rule_id for r in rules}
    assert "CAND-001" in set(ne_ids)


def test_load_ruleset_structural_conflict_rejected(tmp_path) -> None:
    # A rule id present in BOTH [[rules]] and [[non_executable]] is invalid.
    toml_text = _VALID_TOML.replace(
        'rule_id = "CAND-001"', 'rule_id = "CAND-002"'
    )
    with pytest.raises(RulesetLoadError):
        load_ruleset(_write_ruleset(tmp_path, toml_text))


def test_ruleset_version_binding_from_loaded_artifact() -> None:
    # RULESET_VERSION must come from the loaded artifact, not a hardcoded
    # constant that could diverge.
    assert RULESET_VERSION == "SEVERITY-RULES-v1.0.0"
    assert RULESET_STATUS == "RATIFIED_FOR_CONSUMPTION"
    assert RULESET_VERSION.startswith("SEVERITY-RULES-v")


def test_classifier_fails_closed_on_missing_ruleset() -> None:
    # The classifier must fail closed: with the authoritative ruleset
    # unavailable, initialization fails and NO severity is available. There is
    # NO hardcoded-Python fallback.
    with pytest.raises(RulesetLoadError):
        load_ruleset(RULESET_PATH.parent / "SEVERITY_RULES_missing_v1.0.0.toml")


# ============================================================================
# WO-037-07 — Mandatory no-hardcoded-fallback test (objective)
# ============================================================================


def test_no_hardcoded_fallback_ruleset_unavailable_fails() -> None:
    """Prove: ruleset unavailable + classifier initialization = FAIL.

    The authoritative TOML artifact is temporarily made unavailable to a clean
    interpreter, which then attempts to initialize the classifier by importing
    ``app.operator.severity``. Because there is no hardcoded-Python fallback,
    that import must FAIL — classification is unavailable. The artifact is
    restored afterwards.
    """
    import pathlib

    toml = pathlib.Path(severity_module.__file__).resolve().parents[3] / (
        "docs/governance/SEVERITY_RULES_v1.0.0.toml"
    )
    sidecar = toml.with_name(toml.name + ".sha256")
    assert toml.exists(), "authoritative ruleset artifact missing"
    assert sidecar.exists(), "authoritative ruleset sidecar missing"

    repo_root = pathlib.Path(severity_module.__file__).resolve().parents[3]
    backend = repo_root / "backend"
    env = dict(os.environ)
    env["PYTHONPATH"] = str(backend)

    bak_toml = toml.with_name(toml.name + ".bak")
    bak_sidecar = sidecar.with_name(sidecar.name + ".bak")

    try:
        os.rename(toml, bak_toml)
        os.rename(sidecar, bak_sidecar)
        # Clean interpreter: importing the classifier MUST fail (fail-closed).
        proc = subprocess.run(
            [sys.executable, "-c", "import app.operator.severity"],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(repo_root),
        )
        assert proc.returncode != 0, (
            "classifier initialized with NO ruleset — a hardcoded-Python "
            "fallback is present (ruleset unavailable + init = SUCCESS)"
        )
        assert "RulesetLoadError" in proc.stderr or "ruleset" in proc.stderr.lower()
    finally:
        os.rename(bak_toml, toml)
        os.rename(bak_sidecar, sidecar)

    # The artifact is restored and the classifier loads again (fail-safe).
    assert toml.exists() and sidecar.exists()
    assert classify_facts("signal.failed", "signal") == Severity.WARNING


def test_no_hardcoded_rule_literals_in_python() -> None:
    """Inspect the runtime module/source to prove the ratified rules are not
    duplicated in Python.

    The four executable rule definitions must NOT be materialized as
    ``BaselineRule(...)`` literals carrying rule content; they come only from
    the loader. Also ``RATIFIED_RULES`` must no longer exist.
    """
    import ast
    import pathlib

    src = pathlib.Path(severity_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)

    forbidden_content = {
        "CAND-002", "CAND-004", "CAND-005", "CAND-006",
        "signal.failed", "observation.verified", "relation.severed",
        "system.startup",
    }
    literal_values: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "BaselineRule"
        ):
            for kw in node.keywords:
                if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                    literal_values.add(kw.value.value)
    # No rule content may be hardcoded as a BaselineRule literal in Python.
    assert not (literal_values & forbidden_content), literal_values & forbidden_content
    # The hardcoded ruleset constant must be gone.
    assert not hasattr(severity_module, "RATIFIED_RULES")
    # Rules are loaded from the machine-readable artifact.
    assert RULES and len(RULES) == 4


# ============================================================================
# WO-037-07 — Markdown generation + drift detection
# ============================================================================


def test_markdown_generation_from_ruleset() -> None:
    """The generated Markdown is a deterministic representation of the TOML."""
    import subprocess
    import sys

    script = pathlib.Path(
        os.path.dirname(severity_module.__file__)
    ).resolve().parents[2] / "scripts" / "generate_severity_markdown.py"
    proc = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        cwd=str(pathlib.Path(severity_module.__file__).resolve().parents[3]),
    )
    assert proc.returncode == 0, proc.stderr
    md = pathlib.Path(
        pathlib.Path(severity_module.__file__).resolve().parents[3]
        / "docs/governance/SEVERITY_RULES_v1.0.0.md"
    ).read_text(encoding="utf-8")
    # Rule-bearing sections must be present and driven by the ruleset.
    assert "### CAND-002" in md
    assert "### CAND-004" in md
    assert "### CAND-005" in md
    assert "### CAND-006" in md
    assert "RULESET_VERSION | SEVERITY-RULES-v1.0.0" in md
    assert "RATIFIED_FOR_CONSUMPTION" in md
    # Non-executable records appear, but not as executable rules.
    assert "NOT_EXECUTABLE" in md


def test_markdown_drift_detection_pass_and_fail() -> None:
    """The regenerate-and-compare drift check passes on a clean tree and
    detects manual divergence."""
    import pathlib
    import subprocess

    repo_root = pathlib.Path(severity_module.__file__).resolve().parents[3]
    validator = repo_root / "scripts" / "validate_severity_drift.py"
    proc = subprocess.run(
        [sys.executable, str(validator)],
        capture_output=True,
        text=True,
        cwd=str(repo_root),
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr

    # Force drift by appending to the committed Markdown; must FAIL, then restore.
    md = repo_root / "docs/governance/SEVERITY_RULES_v1.0.0.md"
    original = md.read_text(encoding="utf-8")
    try:
        md.write_text(original + "\n# DRIFT\n", encoding="utf-8")
        proc2 = subprocess.run(
            [sys.executable, str(validator)],
            capture_output=True,
            text=True,
            cwd=str(repo_root),
        )
        assert proc2.returncode != 0, "drift was not detected"
        assert "DRIFT CHECK: FAIL" in proc2.stdout
    finally:
        md.write_text(original, encoding="utf-8")
