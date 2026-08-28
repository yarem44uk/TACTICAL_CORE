"""WO-037-03 tests: Offline Operator UI.

Exercises the operator FastAPI application serving the self-contained offline
operator UI (ADR-011 §13):

  * the operator index is served at ``/`` and contains the application shell;
  * the local CSS and JS assets are served (no external/CDN references);
  * the UI JavaScript issues only GET requests to ``/api/v1/operator/*``;
  * health data is represented, and degraded/unavailable is handled honestly;
  * event / entity / relation / detail endpoints are represented in the UI;
  * no mutation endpoint is exposed by the operator app.

Same file-based SQLite test harness as WO-037-02 (thread-safe for TestClient).
"""

from __future__ import annotations

import os
import re
import tempfile

import pytest
from fastapi.testclient import TestClient

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
from app.operator.app import STATIC_DIR, create_operator_app

INDEX = STATIC_DIR / "index.html"
CSS = STATIC_DIR / "operator.css"
JS = STATIC_DIR / "operator.js"


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
def client(repos) -> TestClient:
    event_repo, entity_repo, relation_repo = repos
    app = create_operator_app(
        event_repository=event_repo,
        entity_repository=entity_repo,
        relation_repository=relation_repo,
    )
    return TestClient(app)


def seed_event(event_repo: SQLAlchemyEventRepository) -> None:
    event_repo.save(
        Event(
            event_id="evt-ui-0001",
            event_type=EventType.ENTITY_CREATED,
            timestamp=__import__("datetime").datetime(2026, 8, 1, 12, 0, 0),
            source="ui-source",
            payload={"k": "v"},
        )
    )


# -- Application shell & static serving --------------------------------------


def test_operator_index_returns_200(client) -> None:
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


def test_operator_index_contains_application_shell(client) -> None:
    resp = client.get("/")
    html = resp.text
    assert "Tactical Core" in html
    assert "Offline Operator UI" in html
    assert "operator.css" in html
    assert "operator.js" in html


def test_css_asset_is_served(client) -> None:
    resp = client.get("/static/operator.css")
    assert resp.status_code == 200
    assert "text/css" in resp.headers["content-type"]


def test_js_asset_is_served(client) -> None:
    resp = client.get("/static/operator.js")
    assert resp.status_code == 200
    assert "javascript" in resp.headers["content-type"]


# -- Offline / zero-external-dependency --------------------------------------


def test_index_has_no_external_references(client) -> None:
    """No http(s)://, //, CDN, external fonts/images/scripts/stylesheets."""
    html = client.get("/").text
    css = client.get("/static/operator.css").text
    js = client.get("/static/operator.js").text
    blob = html + "\n" + css + "\n" + js
    assert "http://" not in blob
    assert "https://" not in blob
    # No protocol-relative external references.
    assert re.search(r'(?<![\w:"\'/])//[A-Za-z]', blob) is None
    # Local references only.
    assert "operator.css" in html
    assert "operator.js" in html
    assert "src=\"operator.js\"" in html
    assert "href=\"operator.css\"" in html


def test_no_external_fonts(client) -> None:
    css = client.get("/static/operator.css").text
    assert "@import" not in css
    assert "url(" not in css
    assert "fonts.googleapis" not in css
    assert "fonts.gstatic" not in css


# -- UI JavaScript GET-only / read-only --------------------------------------


def test_js_uses_only_get_requests(client) -> None:
    js = client.get("/static/operator.js").text
    # Every fetch call uses method GET.
    fetches = re.findall(r"fetch\([^)]*\)", js)
    assert fetches, "expected at least one fetch() in operator.js"
    for f in fetches:
        if "method:" in f:
            assert "GET" in f, f"non-GET fetch found: {f}"
    # No forbidden mutation method names anywhere in the UI JS.
    for method in ["POST", "PUT", "PATCH", "DELETE"]:
        assert f"\"{method}\"" not in js
        assert f"'{method}'" not in js


def test_js_references_only_operator_api(client) -> None:
    js = client.get("/static/operator.js").text
    api_refs = set(re.findall(r'/api/v1/operator/[a-z_/\{\}]*', js))
    assert api_refs, "expected operator API references in operator.js"
    for ref in api_refs:
        assert ref.startswith("/api/v1/operator/")
    # API base is the operator prefix only.
    assert 'var API = "/api/v1/operator";' in js


def test_no_mutation_endpoints_represented(client) -> None:
    js = client.get("/static/operator.js").text
    # The UI only ever reads; it must not construct mutation calls.
    assert "POST" not in js
    assert "PUT" not in js
    assert "PATCH" not in js
    assert "DELETE" not in js
    assert "acknowledge" not in js
    assert "tasking" not in js


# -- Health representation ----------------------------------------------------


def test_health_endpoint_represented_in_ui(client) -> None:
    js = client.get("/static/operator.js").text
    assert '"/health"' in js or "API + \"/health\"" in js
    # Health view surfaces durable counts and honest last_ingestion handling.
    assert "durable_events" in js
    assert "durable_entities" in js
    assert "last_ingestion" in js


def test_health_served_by_operator_app(client, repos) -> None:
    event_repo, _, _ = repos
    seed_event(event_repo)
    resp = client.get("/api/v1/operator/health")
    assert resp.status_code == 200
    body = resp.json()
    assert "durable_events" in body
    assert body["durable_events"] >= 1
    assert "last_ingestion" in body


def test_health_degraded_handled_in_ui(client) -> None:
    js = client.get("/static/operator.js").text
    assert "Unavailable" in js
    assert "Degraded" in js


# -- Event / entity / relation representation ---------------------------------


def test_event_feed_represented(client) -> None:
    js = client.get("/static/operator.js").text
    assert '"/events"' in js or '"/events?"' in js
    assert "event_type" in js
    assert "event_status" in js
    assert "cursor" in js
    assert "next_cursor" in js


def test_event_detail_represented(client) -> None:
    js = client.get("/static/operator.js").text
    assert '"/events/"' in js
    assert "Not found: event does not exist" in js


def test_entity_list_represented(client) -> None:
    js = client.get("/static/operator.js").text
    assert '"/entities"' in js
    assert "entity_type" in js


def test_entity_detail_represented(client) -> None:
    js = client.get("/static/operator.js").text
    assert '"/entities/"' in js
    assert "Relations" in js


def test_relations_represented(client) -> None:
    js = client.get("/static/operator.js").text
    assert '"/relations"' in js
    assert "relation_type" in js
    assert "source_event_id" in js
    assert "confidence" in js


# -- App still exposes the operator API and rejects mutation ------------------


def test_operator_api_still_registered(client) -> None:
    for path in [
        "/api/v1/operator/health",
        "/api/v1/operator/events",
        "/api/v1/operator/entities",
    ]:
        resp = client.get(path)
        assert resp.status_code == 200


def test_mutation_methods_rejected_on_api(client) -> None:
    for method, path in [
        ("post", "/api/v1/operator/events"),
        ("put", "/api/v1/operator/events/evt-1"),
        ("patch", "/api/v1/operator/entities/ent-1"),
        ("delete", "/api/v1/operator/entities/ent-1"),
    ]:
        resp = getattr(client, method)(path)
        assert resp.status_code == 405, f"{method.upper()} {path} -> {resp.status_code}"
