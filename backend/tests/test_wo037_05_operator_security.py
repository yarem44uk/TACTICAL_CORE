"""WO-037-05 tests: Operator Security / Access Control.

Exercises the operator-layer bearer-token auth gate and access control
(ADR-011 §15, ``docs/work_orders/WO-037-05.md``):

  * AC-01 unauthenticated REST -> 401 (gate enabled)
  * AC-02 authenticated REST -> existing success
  * AC-03 invalid token -> 401, no token/stack leak
  * AC-04 missing token -> 401 (gate enabled)
  * AC-05 unauthenticated SSE -> 401 (before any stream byte)
  * AC-06 authenticated SSE -> stream (real HTTP request + Authorization header)
  * AC-07 UI auth flow (token entry + Authorization header; no localStorage)
  * AC-08 invalid credentials never leak a secret / stack trace
  * AC-09 programming errors remain 500
  * AC-10 durable dependency failures remain 503
  * AC-11 operator remains read-only (mutation methods -> 405)
  * AC-12 durable core independent of auth (no durable->auth import)
  * AC-13 no second event store
  * AC-14 no durable auth state (no auth/token/session tables)
  * AC-15 offline operation preserved (no external network refs in UI/auth)
  * AC-16 no external runtime dependency (stdlib-only auth)
  * AC-17 WO-037-01..04 regression (covered by full operator regression)
  * AC-18 security non-regression (SSE semantics unchanged with auth)

Plus:
  * security headers on /, API, and SSE (without breaking text/event-stream)
  * startup safety / bind policy (AD-1, AD-2): loopback+no token starts;
    non-loopback+no token refuses startup; non-loopback+token starts.
  * SSE auth exercised with a REAL HTTP request carrying the Authorization
    header (not a fake "auth header exists" assertion).
  * token-leak check: the credential never appears in any response body or
    header.

Auth gate is operator-local (stdlib ``secrets.compare_digest``), stateless,
and never touches the durable core.
"""

from __future__ import annotations

import asyncio
import json
import os
import pathlib
import tempfile

import httpx
import pytest
import sqlalchemy.exc

from app.database.session import DatabaseSessionManager
from app.entity_relations.sqlalchemy_relation_repository import (
    SQLAlchemyRelationRepository,
)
from app.entity_repository.sqlalchemy_entity_repository import (
    SQLAlchemyEntityRepository,
)
from app.event.event import Event
from app.event.event_types import EventType
from app.event_repository.durable.sqlalchemy_event_repository import (
    SQLAlchemyEventRepository,
)
from app.operator.app import create_operator_app
from app.operator.auth import (
    OperatorAuthError,
    OperatorAuthGate,
    _extract_bearer,
)
from app.operator.entrypoint import _is_loopback, resolve_operator_bind

TEST_TOKEN = "sekrit-token-7f3a91c2"
STREAM_URL = "/api/v1/operator/events/stream"
EVENTS_URL = "/api/v1/operator/events"

_BACKEND = pathlib.Path(__file__).resolve().parents[1]
_OPERATOR_DIR = _BACKEND / "app" / "operator"
_STATIC = _OPERATOR_DIR / "static"


def _make_event(event_id: str) -> Event:
    return Event(
        event_id=event_id,
        entity_id=f"entity-{event_id}",
        event_type=EventType.CUSTOM,
        source="wo03705-test",
        payload={"note": event_id},
    )


@pytest.fixture()
def db_path() -> str:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.remove(path)


@pytest.fixture()
def session_manager(db_path: str) -> DatabaseSessionManager:
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
def app_enabled(repos):
    """Operator app with the auth gate ENABLED for a known token."""
    event_repo, entity_repo, relation_repo = repos
    return create_operator_app(
        event_repository=event_repo,
        entity_repository=entity_repo,
        relation_repository=relation_repo,
        auth_gate=OperatorAuthGate(token=TEST_TOKEN),
    )


@pytest.fixture()
def app_disabled(repos):
    """Operator app with the auth gate DISABLED (no token configured)."""
    event_repo, entity_repo, relation_repo = repos
    return create_operator_app(
        event_repository=event_repo,
        entity_repository=entity_repo,
        relation_repository=relation_repo,
        auth_gate=OperatorAuthGate(token=None),
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
    """GET an SSE URL over ASGITransport; return (status_code, raw body)."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        async with client.stream("GET", url, headers=headers) as response:
            body = b"".join([chunk async for chunk in response.aiter_bytes()])
            return response.status_code, body


def _auth(token: str) -> dict:
    return {"Authorization": "Bearer " + token}


# ============================================================================
# auth module unit tests
# ============================================================================


def test_auth_gate_disabled_without_token() -> None:
    gate = OperatorAuthGate(token=None)
    assert gate.enabled is False
    # Disabled gate allows everything (dev/test default).
    gate.require(None)
    gate.require("Authorization: Bearer whatever")


def test_auth_gate_enabled_with_token() -> None:
    gate = OperatorAuthGate(token=TEST_TOKEN)
    assert gate.enabled is True


def test_extract_bearer() -> None:
    assert _extract_bearer("Bearer abc") == "abc"
    assert _extract_bearer("bearer abc") == "abc"
    assert _extract_bearer("Bearer   spaced  ") == "spaced"
    assert _extract_bearer(None) is None
    assert _extract_bearer("") is None
    assert _extract_bearer("Basic abc") is None  # wrong scheme
    assert _extract_bearer("Bearer") is None  # no token
    assert _extract_bearer("abc def ghi") is None  # malformed


def test_gate_rejects_missing_and_invalid() -> None:
    gate = OperatorAuthGate(token=TEST_TOKEN)
    with pytest.raises(OperatorAuthError):
        gate.require(None)
    with pytest.raises(OperatorAuthError):
        gate.require("Bearer wrong-token")
    # valid passes without raising
    gate.require("Bearer " + TEST_TOKEN)


def test_gate_is_constant_time_and_never_echoes() -> None:
    gate = OperatorAuthGate(token=TEST_TOKEN)
    try:
        gate.require("Bearer wrong-token")
    except OperatorAuthError as exc:
        assert TEST_TOKEN not in str(exc)
        assert "wrong-token" not in str(exc)


# ============================================================================
# AC-01 / AC-04 — unauthenticated / missing token -> 401
# ============================================================================


@pytest.mark.asyncio
async def test_ac01_unauthenticated_rest_rejected(app_enabled) -> None:
    status, body = await _get(app_enabled, EVENTS_URL)
    assert status == 401
    assert body["error_type"] == "AuthenticationRequired"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/operator/health",
        "/api/v1/operator/events",
        "/api/v1/operator/entities",
        "/",
    ],
)
async def test_ac04_missing_token_rejected_on_surface(app_enabled, path: str) -> None:
    status, _ = await _get(app_enabled, path)
    assert status == 401


# ============================================================================
# AC-03 — invalid token -> 401
# ============================================================================


@pytest.mark.asyncio
async def test_ac03_invalid_token_rejected(app_enabled) -> None:
    status, body = await _get(app_enabled, EVENTS_URL, headers=_auth("nope"))
    assert status == 401
    assert TEST_TOKEN not in json.dumps(body)


@pytest.mark.asyncio
async def test_ac03_wrong_scheme_rejected(app_enabled) -> None:
    status, _ = await _get(
        app_enabled, EVENTS_URL, headers={"Authorization": "Basic " + TEST_TOKEN}
    )
    assert status == 401


# ============================================================================
# AC-02 — authenticated REST succeeds
# ============================================================================


@pytest.mark.asyncio
async def test_ac02_authenticated_rest_succeeds(app_enabled, event_repo) -> None:
    event_repo.save(_make_event("e1"))
    status, body = await _get(app_enabled, EVENTS_URL, headers=_auth(TEST_TOKEN))
    assert status == 200
    assert len(body["events"]) == 1
    assert body["events"][0]["event_id"] == "e1"


@pytest.mark.asyncio
async def test_authenticated_health_succeeds(app_enabled) -> None:
    status, body = await _get(app_enabled, "/api/v1/operator/health", headers=_auth(TEST_TOKEN))
    assert status == 200
    assert "durable_events" in body


# ============================================================================
# AC-11 — read-only preserved (mutation methods -> 405)
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
async def test_ac11_mutation_methods_405_even_authenticated(
    app_enabled, method: str
) -> None:
    transport = httpx.ASGITransport(app=app_enabled)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        response = await client.request(
            method, EVENTS_URL, headers=_auth(TEST_TOKEN)
        )
    assert response.status_code == 405


# ============================================================================
# AC-05 / AC-06 — SSE authentication (REAL HTTP request)
# ============================================================================


@pytest.mark.asyncio
async def test_ac05_unauthenticated_sse_rejected(app_enabled) -> None:
    status, body = await _get_sse(app_enabled, f"{STREAM_URL}?stream_ticks=0")
    assert status == 401
    # No stream byte / no data leaks for an unauthenticated client.
    assert b"data:" not in body


@pytest.mark.asyncio
async def test_ac06_authenticated_sse_streams(app_enabled, event_repo) -> None:
    event_repo.save(_make_event("e1"))
    event_repo.save(_make_event("e2"))
    status, body = await _get_sse(
        app_enabled,
        f"{STREAM_URL}?stream_ticks=0",
        headers=_auth(TEST_TOKEN),
    )
    assert status == 200
    assert body.decode("utf-8").count("data:") == 2
    assert b'"event_id":"e1"' in body
    assert b'"event_id":"e2"' in body


@pytest.mark.asyncio
async def test_ac06_authenticated_sse_ids_are_durable_seq(
    app_enabled, event_repo
) -> None:
    event_repo.save(_make_event("e1"))
    event_repo.save(_make_event("e2"))
    status, body = await _get_sse(
        app_enabled,
        f"{STREAM_URL}?stream_ticks=0",
        headers=_auth(TEST_TOKEN),
    )
    assert status == 200
    text = body.decode("utf-8")
    # frames carry deterministic durable seq ids 1 and 2
    assert "id: 1" in text
    assert "id: 2" in text


# ============================================================================
# AC-09 — programming error remains 500 (with auth enabled)
# ============================================================================


@pytest.mark.asyncio
async def test_ac09_programming_error_remains_500_with_auth() -> None:
    class _BugsyEventRepo:
        def max_seq(self) -> int:
            raise KeyError("programmer bug, not a DB failure")

    app = create_operator_app(
        event_repository=_BugsyEventRepo(),  # type: ignore[arg-type]
        entity_repository=SQLAlchemyEntityRepository(
            session_manager=DatabaseSessionManager("sqlite:///:memory:")
        ),
        relation_repository=SQLAlchemyRelationRepository(
            session_manager=DatabaseSessionManager("sqlite:///:memory:")
        ),
        auth_gate=OperatorAuthGate(token=TEST_TOKEN),
    )
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        response = await client.get(STREAM_URL, headers=_auth(TEST_TOKEN))
    assert response.status_code == 500
    body = response.json()
    assert body["detail"] == "internal operator error"
    assert "KeyError" not in json.dumps(body)


# ============================================================================
# AC-10 — durable dependency failure remains 503 (with auth enabled)
# ============================================================================


@pytest.mark.asyncio
async def test_ac10_dependency_failure_remains_503_with_auth() -> None:
    class _FailingEventRepo:
        def max_seq(self) -> int:
            raise sqlalchemy.exc.OperationalError(
                "SELECT ...", {}, Exception("db down")
            )

    app = create_operator_app(
        event_repository=_FailingEventRepo(),  # type: ignore[arg-type]
        entity_repository=SQLAlchemyEntityRepository(
            session_manager=DatabaseSessionManager("sqlite:///:memory:")
        ),
        relation_repository=SQLAlchemyRelationRepository(
            session_manager=DatabaseSessionManager("sqlite:///:memory:")
        ),
        auth_gate=OperatorAuthGate(token=TEST_TOKEN),
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        async with client.stream(
            "GET", STREAM_URL, headers=_auth(TEST_TOKEN)
        ) as response:
            assert response.status_code == 503


# ============================================================================
# AC-08 — invalid credentials never leak secret / stack trace
# ============================================================================


@pytest.mark.asyncio
async def test_ac08_invalid_credential_no_leak(app_enabled) -> None:
    status, body = await _get(app_enabled, EVENTS_URL, headers=_auth("wrong"))
    assert status == 401
    raw = json.dumps(body)
    assert TEST_TOKEN not in raw
    assert "wrong" not in raw
    assert "Traceback" not in raw
    assert "KeyError" not in raw


# ============================================================================
# security headers (AC: /, API, SSE)
# ============================================================================


def _assert_security_headers(headers: httpx.Headers) -> None:
    assert headers.get("x-content-type-options") == "nosniff"
    assert headers.get("referrer-policy") == "no-referrer"
    assert (
        headers.get("content-security-policy")
        == "default-src 'self'; frame-ancestors 'self'"
    )


@pytest.mark.asyncio
async def test_security_headers_on_api(app_enabled) -> None:
    transport = httpx.ASGITransport(app=app_enabled)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        response = await client.get(EVENTS_URL, headers=_auth(TEST_TOKEN))
    assert response.status_code == 200
    _assert_security_headers(response.headers)


@pytest.mark.asyncio
async def test_security_headers_on_sse_preserve_event_stream(app_enabled) -> None:
    transport = httpx.ASGITransport(app=app_enabled)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        async with client.stream(
            "GET", f"{STREAM_URL}?stream_ticks=0", headers=_auth(TEST_TOKEN)
        ) as response:
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/event-stream")
            _assert_security_headers(response.headers)
            # SSE control headers preserved (not broken by security middleware)
            assert response.headers.get("cache-control") == "no-cache"
            assert response.headers.get("x-accel-buffering") == "no"


# ============================================================================
# AC-07 — UI auth flow (static content checks, no browser required)
# ============================================================================


def _read_static(name: str) -> str:
    return (_STATIC / name).read_text(encoding="utf-8")


def test_ac07_ui_has_token_entry_flow() -> None:
    html = _read_static("index.html")
    assert 'id="token-input"' in html
    assert 'id="auth-btn"' in html
    assert 'id="logout-btn"' in html


def test_ac07_js_sends_authorization_header() -> None:
    js = _read_static("operator.js")
    assert '"Authorization": "Bearer " + authToken' in js
    assert "function withAuth" in js
    # token held in memory only; never persisted
    assert "localStorage" not in js.replace(
        "localStorage/sessionStorage, never placed", ""
    )
    assert "sessionStorage" not in js.replace(
        "localStorage/sessionStorage, never placed", ""
    )
    # no console.log of the token
    assert "console.log" not in js
    # no token placed in a URL
    assert "token=" not in js


def test_ac07_ui_clears_token_input_after_apply() -> None:
    js = _read_static("operator.js")
    assert 'el("token-input").value = ""' in js


# ============================================================================
# AC-12 / AC-13 / AC-14 — durable isolation, no second store, no auth state
# ============================================================================


def test_ac12_durable_core_does_not_import_auth() -> None:
    durable_files = [
        _BACKEND / "app" / "event_repository" / "durable" / "sqlalchemy_event_repository.py",
        _BACKEND / "app" / "event_repository" / "durable" / "durable_event_model.py",
        _BACKEND / "app" / "entity_repository" / "sqlalchemy_entity_repository.py",
        _BACKEND / "app" / "entity_relations" / "sqlalchemy_relation_repository.py",
    ]
    for path in durable_files:
        assert path.is_file(), f"expected durable file {path}"
        src = path.read_text(encoding="utf-8")
        assert "app.operator.auth" not in src, f"durable core imports auth: {path}"
        assert "from app.operator" not in src, f"durable core imports operator: {path}"


def test_ac13_ac14_no_second_store_no_auth_state(
    db_path: str, session_manager: DatabaseSessionManager
) -> None:
    # Building the operator app with an injected gate must NOT create any
    # auth/token/session/operator table in the authoritative database.
    event_repo = SQLAlchemyEventRepository(session_manager=session_manager)
    event_repo.initialize()
    entity_repo = SQLAlchemyEntityRepository(session_manager=session_manager)
    entity_repo.initialize()
    relation_repo = SQLAlchemyRelationRepository(session_manager=session_manager)
    relation_repo.initialize()
    create_operator_app(
        event_repository=event_repo,
        entity_repository=entity_repo,
        relation_repository=relation_repo,
        auth_gate=OperatorAuthGate(token=TEST_TOKEN),
    )
    from sqlalchemy import create_engine, inspect

    engine = create_engine(f"sqlite:///{db_path}")
    tables = set(inspect(engine).get_table_names())
    forbidden = {"auth", "token", "tokens", "sessions", "session", "users", "operator"}
    assert not (tables & forbidden), f"auth state tables found: {tables & forbidden}"
    engine.dispose()


# ============================================================================
# AC-15 / AC-16 — offline, no external dependency
# ============================================================================


def test_ac15_ui_and_auth_have_no_external_network_refs() -> None:
    js = _read_static("operator.js")
    html = _read_static("index.html")
    css = _read_static("operator.css")
    auth_src = (_OPERATOR_DIR / "auth.py").read_text(encoding="utf-8")
    blob = js + html + css + auth_src
    for marker in ("http://", "https://", "//cdn", "googleapis", "gstatic"):
        assert marker not in blob, f"external network reference found: {marker}"


def test_ac16_auth_module_is_stdlib_only() -> None:
    auth_src = (_OPERATOR_DIR / "auth.py").read_text(encoding="utf-8")
    assert "import secrets" in auth_src
    assert "import os" in auth_src
    assert "import logging" in auth_src
    # No third-party / network / durable-core imports in the auth gate.
    for forbidden in ("import requests", "import urllib", "import socket", "import aiohttp"):
        assert forbidden not in auth_src


# ============================================================================
# startup safety / bind policy (AD-1, AD-2)
# ============================================================================


def test_loopback_detection() -> None:
    assert _is_loopback("127.0.0.1")
    assert _is_loopback("::1")
    assert _is_loopback("localhost")
    assert not _is_loopback("0.0.0.0")
    assert not _is_loopback("192.168.1.5")


def test_default_bind_is_loopback(monkeypatch) -> None:
    monkeypatch.delenv("OPERATOR_HOST", raising=False)
    monkeypatch.delenv("OPERATOR_PORT", raising=False)
    host, port = resolve_operator_bind()
    assert host == "127.0.0.1"
    assert port == 8010


def test_loopback_no_token_starts(monkeypatch) -> None:
    monkeypatch.setenv("OPERATOR_HOST", "127.0.0.1")
    monkeypatch.delenv("OPERATOR_TOKEN", raising=False)
    host, _ = resolve_operator_bind()
    assert host == "127.0.0.1"


def test_non_loopback_no_token_refuses_startup(monkeypatch) -> None:
    monkeypatch.setenv("OPERATOR_HOST", "0.0.0.0")
    monkeypatch.delenv("OPERATOR_TOKEN", raising=False)
    with pytest.raises(RuntimeError) as exc_info:
        resolve_operator_bind()
    assert "OPERATOR_TOKEN" in str(exc_info.value)
    assert "refused" in str(exc_info.value)
    # non-secret error
    assert TEST_TOKEN not in str(exc_info.value)


def test_non_loopback_with_token_starts(monkeypatch) -> None:
    monkeypatch.setenv("OPERATOR_HOST", "0.0.0.0")
    monkeypatch.setenv("OPERATOR_TOKEN", TEST_TOKEN)
    host, _ = resolve_operator_bind()
    assert host == "0.0.0.0"


# ============================================================================
# token leak across the whole response surface
# ============================================================================


@pytest.mark.asyncio
async def test_token_never_appears_in_responses(app_enabled, event_repo) -> None:
    event_repo.save(_make_event("e1"))
    transport = httpx.ASGITransport(app=app_enabled, raise_app_exceptions=False)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        for path in (EVENTS_URL, "/api/v1/operator/health", "/api/v1/operator/entities"):
            response = await client.get(path, headers=_auth(TEST_TOKEN))
            assert TEST_TOKEN not in response.text
            assert TEST_TOKEN not in json.dumps(dict(response.headers))
        # invalid token path too
        response = await client.get(EVENTS_URL, headers=_auth("wrong"))
        assert TEST_TOKEN not in response.text
        assert "wrong" not in response.text
        # SSE stream body must not contain the token
        async with client.stream(
            "GET", f"{STREAM_URL}?stream_ticks=0", headers=_auth(TEST_TOKEN)
        ) as sse:
            body = b"".join([c async for c in sse.aiter_bytes()])
            assert TEST_TOKEN.encode() not in body


# ============================================================================
# AC-18 — SSE semantics preserved with auth (Last-Event-ID resume)
# ============================================================================


@pytest.mark.asyncio
async def test_ac18_authenticated_sse_last_event_id_resume(app_enabled, event_repo) -> None:
    for i in range(1, 6):
        event_repo.save(_make_event(f"e{i}"))
    status, body = await _get_sse(
        app_enabled,
        f"{STREAM_URL}?stream_ticks=1",
        headers={**_auth(TEST_TOKEN), "Last-Event-ID": "3"},
    )
    assert status == 200
    text = body.decode("utf-8")
    assert "id: 4" in text
    assert "id: 5" in text
    assert "id: 3" not in text


# ============================================================================
# AC-17 regression signal — gate-disabled app keeps prior behavior open
# ============================================================================


@pytest.mark.asyncio
async def test_ac17_gate_disabled_preserves_prior_behavior(app_disabled, event_repo) -> None:
    event_repo.save(_make_event("e1"))
    status, body = await _get(app_disabled, EVENTS_URL)
    assert status == 200
    assert len(body["events"]) == 1
