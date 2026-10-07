"""WO-083 — Telegram inbound webhook ingress (acceptance tests).

Proves the WO-083 Telegram ingress across the focused and integration surfaces
the WO requires (§27 matrix, §28 restart, §29 retry, §35-§41 boundary):

    UNIT
        * X-Telegram-Bot-Api-Secret-Token verification (constant time)
        * Update-envelope normalization (text / media reference / unsupported /
          malformed / missing identity)
        * deterministic identity (same/different chat_id+message_id)
        * synchronous ingress seam (AdapterRuntime.submit_raw) semantics
        * source registration through the existing AdapterFactory mechanism
        * observation event-type derivation through the ACTUAL
          CanonicalEventToObservationAdapter path

    INTEGRATION
        * HTTP webhook -> normalization -> AdapterRuntime -> EventFactory ->
          EventPipeline -> durable repository -> Observation -> operator
          read-model (REAL production composition, not mocks)
        * commit-before-ACK: HTTP 200 implies a durable canonical event
        * duplicate delivery -> exactly ONE durable canonical event
        * restart: a fresh runtime instance over the same durable store does
          not create a second event for the same logical message
        * durability failure -> HTTP != 200

No live Telegram API call, no bot token, no webhook registration, no media
download, and no network connection is exercised (§30).  Test credentials are
obviously synthetic placeholders.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import pytest
from fastapi.testclient import TestClient

import app.database.session as session_mod
from app.database.base import Base
from app.database.session import configure_session_manager, get_session_manager
from app.event.event import Event
from app.event.event_types import EventType
from app.event_pipeline.event_pipeline import EventPipeline
from app.event_repository.durable.sqlalchemy_event_repository import (
    SQLAlchemyEventRepository,
)
from app.event_sources.config.adapter_factory import AdapterFactory
from app.event_sources.config.production_source_config import (
    PRODUCTION_SOURCE_CATALOG,
    build_production_adapter_factory,
    build_telegram_source_definition,
)
from app.event_sources.factory.event_factory import EventFactory
from app.event_sources.identity.event_identity import EventIdentityResolver
from app.event_sources.runtime.adapter_runtime import AdapterRuntime, IngestStatus
from app.intelligence.observation.repository import ObservationRepository
from app.observation.canonical_adapter import CanonicalEventToObservationAdapter
from app.observation.models import EVENT_TYPE_MAPPINGS
from app.operator.app import create_operator_app
from app.operator.auth import OperatorAuthGate
from app.telegram_ingress.app import create_telegram_ingress_app
from app.telegram_ingress.composition import build_telegram_ingress_runtime
from app.telegram_ingress.config import (
    TelegramIngressConfig,
    TelegramIngressConfigError,
)
from app.telegram_ingress.normalizer import (
    TelegramUpdateError,
    TelegramUpdateNormalizer,
)
from app.telegram_ingress.secret import SECRET_HEADER, verify_secret_token
from app.telegram_ingress.service import TelegramIngressService

# Synthetic, non-secret test credentials (never a real Telegram value).
WEBHOOK_SECRET = "test-webhook-secret-not-a-real-telegram-secret"
CHAT_ID = -100200300
SENDER_ID = 777001
MESSAGE_ID = 42

_TELEGRAM_INGRESS_DIR = Path(sys.modules["app.telegram_ingress"].__file__).parent


# --------------------------------------------------------------------------- #
# payload builders
# --------------------------------------------------------------------------- #
def _text_update(
    message_id: int = MESSAGE_ID,
    chat_id: int = CHAT_ID,
    text: str = "Burevii-2 na zviazku",
    update_id: int = 100000001,
) -> dict:
    return {
        "update_id": update_id,
        "message": {
            "message_id": message_id,
            "from": {
                "id": SENDER_ID,
                "is_bot": False,
                "first_name": "Alpha",
                "username": "alpha_op",
            },
            "chat": {"id": chat_id, "type": "group", "title": "Sector-2"},
            "date": 1735689600,
            "text": text,
        },
    }


def _photo_update(message_id: int = 500, caption: str | None = "shema") -> dict:
    message = {
        "message_id": message_id,
        "from": {"id": SENDER_ID, "is_bot": False, "first_name": "Alpha"},
        "chat": {"id": CHAT_ID, "type": "group"},
        "date": 1735689700,
        "photo": [
            {"file_id": "SMALL", "file_unique_id": "U1", "file_size": 100},
            {"file_id": "LARGE", "file_unique_id": "U2", "file_size": 9000},
        ],
    }
    if caption is not None:
        message["caption"] = caption
    return {"update_id": 100000002, "message": message}


def _document_update(message_id: int = 501) -> dict:
    return {
        "update_id": 100000003,
        "message": {
            "message_id": message_id,
            "from": {"id": SENDER_ID, "is_bot": False},
            "chat": {"id": CHAT_ID, "type": "private"},
            "date": 1735689800,
            "document": {
                "file_id": "DOC-1",
                "file_unique_id": "UD1",
                "mime_type": "application/pdf",
                "file_size": 4242,
                "file_name": "report.pdf",
            },
        },
    }


def _callback_update() -> dict:
    """A well-formed Update that is OUT OF SCOPE for the first slice."""
    return {
        "update_id": 100000009,
        "callback_query": {
            "id": "CB-1",
            "from": {"id": SENDER_ID},
            "chat_instance": "x",
            "data": "pressed",
        },
    }


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture()
def env(tmp_path):
    """Isolated file database + canonical session manager, reset afterwards."""
    session_mod._session_manager = None
    db_path = str(tmp_path / "wo083.db")
    mgr = configure_session_manager(f"sqlite:///{db_path}")
    Base.metadata.create_all(mgr.engine)
    yield {"db_path": db_path, "mgr": mgr}
    session_mod._session_manager = None


@pytest.fixture()
def wired(env):
    """A REAL production-composition Telegram ingress runtime on the test DB."""
    runtime = build_telegram_ingress_runtime()
    yield runtime
    runtime.stop()


@pytest.fixture()
def client(wired):
    """A webhook client bound to the real ingress runtime."""
    service = TelegramIngressService(adapter_runtime=wired.adapter_runtime)
    app = create_telegram_ingress_app(
        service=service,
        secret_token=WEBHOOK_SECRET,
        webhook_path="/telegram/webhook",
    )
    return TestClient(app)


def _repo() -> SQLAlchemyEventRepository:
    return SQLAlchemyEventRepository(session_manager=get_session_manager())


def _telegram_events():
    return [e for e in _repo().list_all() if e.source == "telegram"]


def _post(client: TestClient, payload: dict, secret: str | None = WEBHOOK_SECRET):
    body = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if secret is not None:
        headers[SECRET_HEADER] = secret
    return client.post("/telegram/webhook", content=body, headers=headers)


def _normalized(payload: dict) -> dict:
    return TelegramUpdateNormalizer().normalize_update(payload)


def _expected_event_id(payload: dict) -> str:
    raw = _normalized(payload)
    resolved = EventIdentityResolver().resolve(raw, "telegram")
    assert resolved is not None, "telegram identity policy must be deduplicable"
    return resolved


def _independent_uuid5(chat_id, message_id) -> str:
    """Recompute the canonical id from first principles (no project helper)."""
    namespace = uuid5(NAMESPACE_URL, "https://tacticalcore.dev/event")
    parts = [
        json.dumps(v, sort_keys=True, default=str, ensure_ascii=False)
        for v in (chat_id, message_id)
    ]
    return str(uuid5(namespace, "|".join(parts)))


# --------------------------------------------------------------------------- #
# §27 (1,2,3) — authentication
# --------------------------------------------------------------------------- #
def test_wo083_01_missing_secret_401(client) -> None:
    body = json.dumps(_text_update()).encode("utf-8")
    r = client.post(
        "/telegram/webhook", content=body, headers={"Content-Type": "application/json"}
    )
    assert r.status_code == 401, r.text
    assert r.json()["detail"] == "invalid secret token"
    assert _telegram_events() == [], "unauthenticated request must not reach the pipeline"


def test_wo083_02_invalid_secret_401(client) -> None:
    r = _post(client, _text_update(), secret="wrong-secret")
    assert r.status_code == 401
    assert _telegram_events() == []


def test_wo083_03_valid_secret_accepted(client) -> None:
    r = _post(client, _text_update())
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "accepted"
    assert r.json()["event_ids"] == [_expected_event_id(_text_update())]


def test_wo083_03b_empty_secret_header_rejected(client) -> None:
    r = _post(client, _text_update(), secret="   ")
    assert r.status_code == 401
    assert _telegram_events() == []


# --------------------------------------------------------------------------- #
# §27 (4) — constant-time comparison
# --------------------------------------------------------------------------- #
def test_wo083_04_constant_time_comparison(monkeypatch) -> None:
    import app.telegram_ingress.secret as secret_mod

    calls: list[tuple] = []
    original = secret_mod.hmac.compare_digest

    def spy(a, b):  # noqa: ANN001
        calls.append((a, b))
        return original(a, b)

    monkeypatch.setattr(secret_mod.hmac, "compare_digest", spy)
    assert verify_secret_token("s3cret", "s3cret") is True
    assert verify_secret_token("s3cret", "other!") is False
    assert len(calls) == 2, "the secret comparison must go through compare_digest"
    # Fail-closed short-circuits never call the comparator at all.
    assert verify_secret_token("s3cret", None) is False
    assert verify_secret_token("", "s3cret") is False
    assert len(calls) == 2


def test_wo083_04b_secret_token_unit_matrix() -> None:
    assert verify_secret_token("abc", "abc") is True
    assert verify_secret_token("abc", " abc ") is True  # trimmed whitespace
    assert verify_secret_token("abc", "abd") is False
    assert verify_secret_token("abc", "") is False
    assert verify_secret_token("abc", None) is False
    assert verify_secret_token("", "abc") is False


# --------------------------------------------------------------------------- #
# §27 (5,6,7,8,9) — parsing / identity material
# --------------------------------------------------------------------------- #
def test_wo083_05_malformed_json_400(client) -> None:
    body = b"{not-json"
    r = client.post(
        "/telegram/webhook",
        content=body,
        headers={
            SECRET_HEADER: WEBHOOK_SECRET,
            "Content-Type": "application/json",
        },
    )
    assert r.status_code == 400
    assert _telegram_events() == []


def test_wo083_06_valid_update_accepted(client) -> None:
    r = _post(client, _text_update())
    assert r.status_code == 200
    event = _repo().get(_expected_event_id(_text_update()))
    assert event.source == "telegram"
    assert event.payload["message_id"] == str(MESSAGE_ID)
    assert event.payload["chat_id"] == str(CHAT_ID)
    assert event.payload["text"] == "Burevii-2 na zviazku"
    assert event.payload["sender_id"] == str(SENDER_ID)
    assert event.payload["sender_username"] == "alpha_op"
    assert event.payload["chat_title"] == "Sector-2"


def test_wo083_07_unsupported_update_type_deterministic_400(client) -> None:
    # No 'message' key: an out-of-scope update type must be handled
    # deterministically and must NEVER create a canonical event.
    r = _post(client, _callback_update())
    assert r.status_code == 400, r.text
    assert "unsupported Telegram update type" in r.json()["detail"]
    assert _telegram_events() == []

    # update_id-only envelope (nothing inbound) is also deterministic.
    r2 = _post(client, {"update_id": 7})
    assert r2.status_code == 400
    assert _telegram_events() == []


def test_wo083_07b_message_not_an_object_400(client) -> None:
    r = _post(client, {"update_id": 1, "message": "not-an-object"})
    assert r.status_code == 400
    assert _telegram_events() == []


def test_wo083_08_missing_chat_id_400(client) -> None:
    update = _text_update()
    del update["message"]["chat"]
    r = _post(client, update)
    assert r.status_code == 400
    assert "chat.id" in r.json()["detail"]
    assert _telegram_events() == []

    update2 = _text_update()
    update2["message"]["chat"] = {"type": "group"}  # no 'id'
    r2 = _post(client, update2)
    assert r2.status_code == 400
    assert _telegram_events() == []


def test_wo083_09_missing_message_id_400(client) -> None:
    update = _text_update()
    del update["message"]["message_id"]
    r = _post(client, update)
    assert r.status_code == 400
    assert "message_id" in r.json()["detail"]
    assert _telegram_events() == []

    with pytest.raises(TelegramUpdateError):
        _normalized({"update_id": 5, "message": {"chat": {"id": CHAT_ID}}})


# --------------------------------------------------------------------------- #
# §27 (10,11,12,13,14) — deterministic identity, no UUID4 fallback
# --------------------------------------------------------------------------- #
def test_wo083_10_deterministic_uuid5_with_existing_namespace() -> None:
    raw = _normalized(_text_update())
    resolved = EventIdentityResolver().resolve(raw, "telegram")
    assert resolved is not None
    # Independent recomputation from the DOCUMENTED namespace and material.
    assert resolved == _independent_uuid5(str(CHAT_ID), str(MESSAGE_ID))
    # Determinism: repeated resolution of an equal payload is identical.
    assert resolved == _expected_event_id(copy.deepcopy(_text_update()))


def test_wo083_11_same_chat_same_message_same_id() -> None:
    assert _expected_event_id(_text_update()) == _expected_event_id(
        _text_update(update_id=999)  # update_id changes; identity must not
    )


def test_wo083_12_different_chat_same_message_different_id() -> None:
    assert _expected_event_id(_text_update()) != _expected_event_id(
        _text_update(chat_id=-100999888)
    )


def test_wo083_13_same_chat_different_message_different_id() -> None:
    assert _expected_event_id(_text_update()) != _expected_event_id(
        _text_update(message_id=43)
    )


def test_wo083_14_no_uuid4_fallback() -> None:
    resolver = EventIdentityResolver()
    # Missing identity material -> non-deduplicable (None), never a UUID.
    assert resolver.resolve({"chat_id": "1"}, "telegram") is None
    assert resolver.resolve({"message_id": "1"}, "telegram") is None
    # The normalizer refuses to invent identity material.
    with pytest.raises(TelegramUpdateError):
        _normalized({"update_id": 1, "message": {"message_id": 1}})
    # update_id / timestamp / text / username are NOT identity material.
    raw = _normalized(_text_update())
    assert "update_id" in raw  # preserved for observability ...
    only_update_id = dict(raw)
    only_update_id.pop("chat_id")
    assert resolver.resolve(only_update_id, "telegram") is None


def test_wo083_14b_normalizer_never_emits_random_identity() -> None:
    raw = _normalized(_text_update())
    resolver = EventIdentityResolver()
    ids = {resolver.resolve(dict(raw), "telegram") for _ in range(5)}
    assert len(ids) == 1 and None not in ids


# --------------------------------------------------------------------------- #
# §27 (15,16,17,18) — durability before ACK
# --------------------------------------------------------------------------- #
def test_wo083_15_successful_message_is_durable(client) -> None:
    r = _post(client, _text_update())
    assert r.status_code == 200
    event_id = _expected_event_id(_text_update())
    assert _repo().exists(event_id)
    assert len(_telegram_events()) == 1


def test_wo083_16_http_200_implies_durable(client) -> None:
    r = _post(client, _text_update())
    assert r.status_code == 200
    for event_id in r.json()["event_ids"]:
        assert _repo().exists(event_id), "HTTP 200 must imply durability"


def test_wo083_17_durability_failure_is_503(env) -> None:
    class _FakeAdapter:
        def source_name(self) -> str:
            return "telegram"

    class _RaisingPipeline:
        def process(self, event):  # noqa: ANN001
            raise RuntimeError("simulated durable commit failure")

    runtime = AdapterRuntime(
        adapter=_FakeAdapter(),
        factory=EventFactory(identity_resolver=EventIdentityResolver()),
        pipeline=_RaisingPipeline(),
        name="telegram",
    )
    runtime.set_ingest_durability_probe(lambda event_id: False)

    result = runtime.submit_raw(_normalized(_text_update()))
    assert result.status == IngestStatus.FAILURE
    assert result.durable is False

    outcome = TelegramIngressService(adapter_runtime=runtime).handle_update(
        _text_update()
    )
    assert outcome.status_code == 503
    assert outcome.ok is False


def test_wo083_18_unconfirmed_durability_is_not_acked(env) -> None:
    class _FakeAdapter:
        def source_name(self) -> str:
            return "telegram"

    class _OkPipeline:
        def process(self, event):  # noqa: ANN001
            return True

    runtime = AdapterRuntime(
        adapter=_FakeAdapter(),
        factory=EventFactory(identity_resolver=EventIdentityResolver()),
        pipeline=_OkPipeline(),
        name="telegram",
    )
    runtime.set_ingest_durability_probe(lambda event_id: False)
    outcome = TelegramIngressService(adapter_runtime=runtime).handle_update(
        _text_update()
    )
    assert outcome.status_code == 503
    assert outcome.event_ids == ()


# --------------------------------------------------------------------------- #
# §27 (19,20,21,22) / §28 — duplicate delivery and restart
# --------------------------------------------------------------------------- #
def test_wo083_19_and_20_21_duplicate_delivery_one_durable_event(client) -> None:
    first = _post(client, _text_update())
    second = _post(client, copy.deepcopy(_text_update()))
    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["duplicate"] is False
    assert second.json()["duplicate"] is True

    events = _telegram_events()
    assert len(events) == 1, "a Telegram retry must not create a second event"
    assert events[0].event_id == _expected_event_id(_text_update())


def test_wo083_22_restart_does_not_duplicate(env) -> None:
    first_runtime = build_telegram_ingress_runtime()
    try:
        service = TelegramIngressService(
            adapter_runtime=first_runtime.adapter_runtime
        )
        assert service.handle_update(_text_update()).status_code == 200
    finally:
        first_runtime.stop()

    assert len(_telegram_events()) == 1

    # Fresh runtime instance over the SAME durable store (simulated restart).
    second_runtime = build_telegram_ingress_runtime()
    try:
        service2 = TelegramIngressService(
            adapter_runtime=second_runtime.adapter_runtime
        )
        outcome = service2.handle_update(_text_update())
        assert outcome.status_code == 200
        assert outcome.duplicate is True
    finally:
        second_runtime.stop()

    assert len(_telegram_events()) == 1, "restart must not create a second event"


# --------------------------------------------------------------------------- #
# §27 (23,24,25,26) — canonical path components
# --------------------------------------------------------------------------- #
def test_wo083_23_adapter_runtime_used(wired) -> None:
    assert isinstance(wired.adapter_runtime, AdapterRuntime)
    service = TelegramIngressService(adapter_runtime=wired.adapter_runtime)
    assert service.runtime is wired.adapter_runtime
    # The service drives the canonical path exclusively through submit_raw.
    assert hasattr(wired.adapter_runtime, "submit_raw")


def test_wo083_24_event_factory_used(wired) -> None:
    assert isinstance(wired.adapter_runtime._factory, EventFactory)
    # The factory is configured with the canonical identity resolver.
    assert wired.adapter_runtime._factory._identity_resolver is not None


def test_wo083_25_event_pipeline_used(wired) -> None:
    assert isinstance(wired.adapter_runtime._pipeline, EventPipeline)


def test_wo083_26_real_sqlalchemy_repository_used(wired) -> None:
    probe = wired.adapter_runtime._ingest_durability_probe
    assert getattr(probe, "__self__", None).__class__ is SQLAlchemyEventRepository
    assert probe.__name__ == "exists"
    # The canonical durable store is the one the test reads back from.
    assert isinstance(_repo(), SQLAlchemyEventRepository)


# --------------------------------------------------------------------------- #
# §27 (27) / §22 — Observation + operator read-model
# --------------------------------------------------------------------------- #
def test_wo083_27_derive_event_type_through_canonical_adapter() -> None:
    adapter = CanonicalEventToObservationAdapter()
    event = Event(
        event_type=EventType.CUSTOM,
        source="telegram",
        payload={"chat_id": str(CHAT_ID), "message_id": str(MESSAGE_ID), "text": "x"},
    )
    assert adapter.derive_event_type(event) == "telegram.message"
    mapped = adapter.to_observation_dict(event)
    assert mapped["event_type"] == "telegram.message"


def test_wo083_27b_telegram_observation_mapping_is_pre_existing() -> None:
    mapping = EVENT_TYPE_MAPPINGS["telegram.message"]
    assert mapping.observation_type == "other"
    # Unchanged by WO-083: chat_id + text are the pre-existing contract, and the
    # normalizer always emits both (text may be "").
    assert set(mapping.required_fields) == {"chat_id", "text"}


def test_wo083_27c_webhook_to_observation_integration(client) -> None:
    r = _post(client, _text_update())
    assert r.status_code == 200
    event_id = _expected_event_id(_text_update())

    assert _repo().exists(event_id)

    obs = ObservationRepository(
        get_session_manager().get_session()
    ).get_by_immutable_id(event_id)
    assert obs is not None
    assert obs.source == "telegram"
    assert obs.observation_type == "other"
    evidence = obs.evidence_payload or {}
    assert evidence.get("event_type") == "telegram.message"
    assert evidence.get("raw_data", {}).get("message_id") == str(MESSAGE_ID)
    assert evidence.get("raw_data", {}).get("chat_id") == str(CHAT_ID)


def test_wo083_27d_operator_read_model_visibility(client) -> None:
    r = _post(client, _text_update())
    assert r.status_code == 200
    event_id = _expected_event_id(_text_update())

    operator_app = create_operator_app(auth_gate=OperatorAuthGate(token=None))
    with TestClient(operator_app) as op:
        resp = op.get("/api/v1/operator/observations", params={"source": "telegram"})
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["total"] >= 1
    ids = [o["immutable_id"] for o in payload["observations"]]
    assert event_id in ids, "the telegram event must be visible on the operator wall"


# --------------------------------------------------------------------------- #
# §27 (28,29) / §24 — media reference-only
# --------------------------------------------------------------------------- #
def test_wo083_28_media_metadata_preserved_reference_only(client) -> None:
    r = _post(client, _photo_update())
    assert r.status_code == 200
    event = _repo().get(_expected_event_id(_photo_update()))
    media = event.payload["media"]
    assert len(media) == 1
    # Largest photo size selected (existing canonical Telegram media semantics).
    assert media[0]["media_type"] == "photo"
    assert media[0]["file_id"] == "LARGE"
    assert media[0]["file_unique_id"] == "U2"
    assert media[0]["file_size"] == 9000
    assert media[0]["caption"] == "shema"
    # The caption is also the message text (existing convention).
    assert event.payload["text"] == "shema"
    assert event.payload["has_media"] is True


def test_wo083_28b_document_metadata_preserved(client) -> None:
    r = _post(client, _document_update())
    assert r.status_code == 200
    event = _repo().get(_expected_event_id(_document_update()))
    media = event.payload["media"][0]
    assert media["media_type"] == "document"
    assert media["file_id"] == "DOC-1"
    assert media["mime_type"] == "application/pdf"
    assert media["file_name"] == "report.pdf"
    assert event.payload["text"] == ""  # no caption -> still observable


def test_wo083_29_media_bytes_never_downloaded_or_stored(client) -> None:
    _post(client, _photo_update())
    event = _repo().get(_expected_event_id(_photo_update()))
    blob = json.dumps(event.payload)
    for forbidden in ("bytes", "file_path", "getFile", "base64", "data_url"):
        assert forbidden not in blob

    # No HTTP/TG client is imported anywhere in the ingress package.
    for path in sorted(_TELEGRAM_INGRESS_DIR.glob("*.py")):
        source = path.read_text(encoding="utf-8")
        for forbidden in ("requests", "httpx", "urllib.request", "telebot", "aiogram", "aiohttp"):
            assert forbidden not in source, f"{path.name} must not import {forbidden}"


# --------------------------------------------------------------------------- #
# §27 (30,31,32,33,34) / §16 / §17 — security & architecture
# --------------------------------------------------------------------------- #
def _ingress_sources() -> dict[str, str]:
    return {
        p.name: p.read_text(encoding="utf-8")
        for p in sorted(_TELEGRAM_INGRESS_DIR.glob("*.py"))
    }


def _ingress_import_lines() -> list[str]:
    """Return only the import STATEMENTS of the ingress package (no docstrings)."""
    lines: list[str] = []
    for name, source in _ingress_sources().items():
        for raw in source.splitlines():
            stripped = raw.strip()
            if stripped.startswith(("import ", "from ")):
                lines.append(f"{name}: {stripped}")
    return lines


def _leaked_modules(code: str) -> set[str]:
    """Import ``code`` in a FRESH interpreter; return legacy modules loaded.

    Reports both the legacy EventBus (``app.core.event_bus``) and the legacy
    connectors (``app.connectors.*``).  A fresh interpreter is used so the
    answer is a property of the import graph, not of test-execution order.
    """
    import os
    import subprocess

    probe = (
        "import sys\n"
        f"{code}\n"
        "print('LEAKED=' + '|'.join(sorted(\n"
        "    m for m in sys.modules\n"
        "    if m.startswith('app.core.event_bus')\n"
        "    or m.startswith('app.connectors'))))\n"
    )
    backend_dir = _TELEGRAM_INGRESS_DIR.parent.parent
    repo_root = backend_dir.parent
    env = dict(os.environ)
    # Mirrors the documented run recipe: both ``.`` and ``..`` are needed
    # (some canonical modules import via ``backend.app...``).
    env["PYTHONPATH"] = f"{repo_root}:{backend_dir}"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    proc = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        cwd=str(backend_dir),
        env=env,
    )
    assert proc.returncode == 0, proc.stderr
    marker = "LEAKED="
    line = [ln for ln in proc.stdout.splitlines() if ln.startswith(marker)][0]
    return {m for m in line[len(marker):].split("|") if m}


_TELEGRAM_CHAIN = (
    "import app.telegram_ingress.app\n"
    "import app.telegram_ingress.composition\n"
    "import app.telegram_ingress.service\n"
    "import app.telegram_ingress.normalizer\n"
    "import app.telegram_ingress.secret\n"
    "import app.telegram_ingress.config\n"
)


def test_wo083_30_no_legacy_event_bus_import() -> None:
    # 1. No ingress module imports the legacy EventBus directly.
    for line in _ingress_import_lines():
        assert "app.core.event_bus" not in line, line
        assert "event_bus" not in line, line

    # 2. In a FRESH interpreter the ingress chain loads no legacy connector, and
    #    adds NOTHING to the legacy-EventBus set that the pre-existing canonical
    #    composition (``app.bootstrap``) already loads.  ``app.core.event_bus``
    #    is reachable ONLY transitively through the shared canonical
    #    ``app.observation.service`` — exactly as it is for the accepted WO-080
    #    WhatsApp ingress (control experiment below).  WO-083 therefore adds no
    #    legacy-EventBus dependency of its own.
    baseline = _leaked_modules("import app.bootstrap")
    whatsapp = _leaked_modules(
        "import app.whatsapp_ingress.app\nimport app.whatsapp_ingress.composition\n"
    )
    telegram = _leaked_modules(_TELEGRAM_CHAIN)

    assert not {m for m in telegram if m.startswith("app.connectors")}, telegram
    assert telegram == baseline == whatsapp, (telegram, baseline, whatsapp)


def test_wo083_31_no_direct_db_write_in_ingress() -> None:
    for name in ("app.py", "service.py", "normalizer.py", "secret.py", "config.py"):
        source = _ingress_sources()[name]
        for forbidden in (
            "SessionLocal",
            "get_session_manager",
            "save_with_deliveries",
            ".commit(",
            ".add(",
            "session_manager",
        ):
            assert forbidden not in source, f"{name} must not write to the DB ({forbidden})"


def test_wo083_31b_no_direct_observation_write() -> None:
    for name, source in _ingress_sources().items():
        assert "Observation(" not in source, name
        assert "ObservationRepository" not in source, name


def test_wo083_31c_composition_uses_read_only_probe_only() -> None:
    source = _ingress_sources()["composition.py"]
    assert "set_ingest_durability_probe" in source
    assert "probe_repository.exists" in source
    assert "save_with_deliveries" not in source
    assert "SessionLocal" not in source


def test_wo083_32_no_second_event_architecture() -> None:
    import app.telegram_ingress.service as service_mod

    assert hasattr(service_mod, "TelegramIngressService")
    for forbidden in ("EventFactory", "EventPipeline", "DurableCanonicalEventRepository"):
        assert not hasattr(service_mod, forbidden)


def test_wo083_33_no_secret_leakage(client, capsys) -> None:
    # Normal response body carries no secret.
    ok = _post(client, _text_update())
    assert WEBHOOK_SECRET not in ok.text

    # Rejection response carries no secret, and no stack trace.
    bad = _post(client, _text_update(), secret="wrong")
    assert WEBHOOK_SECRET not in bad.text
    assert "Traceback" not in bad.text

    # Configuration repr masks the secret.
    cfg = TelegramIngressConfig.from_env(
        {
            "TELEGRAM_WEBHOOK_SECRET": "super-secret-value",
            "DATABASE_URL": "sqlite:///x.db",
        }
    )
    assert "super-secret-value" not in repr(cfg)

    # Health endpoint does not expose the secret.
    health = client.get("/healthz")
    assert health.status_code == 200
    assert WEBHOOK_SECRET not in health.text


def test_wo083_33b_config_fails_closed() -> None:
    with pytest.raises(TelegramIngressConfigError):
        TelegramIngressConfig.from_env({})
    with pytest.raises(TelegramIngressConfigError):
        TelegramIngressConfig.from_env({"TELEGRAM_WEBHOOK_SECRET": "s"})  # no DATABASE_URL
    with pytest.raises(TelegramIngressConfigError):
        TelegramIngressConfig.from_env(
            {"TELEGRAM_WEBHOOK_SECRET": "s", "DATABASE_URL": "sqlite:///x", "TELEGRAM_PORT": "nan"}
        )
    cfg = TelegramIngressConfig.from_env(
        {"TELEGRAM_WEBHOOK_SECRET": "s", "DATABASE_URL": "sqlite:///x"}
    )
    assert cfg.webhook_path == "/telegram/webhook"
    assert cfg.port == 8030
    assert cfg.host == "127.0.0.1"


def test_wo083_34_legacy_telegram_connector_not_used() -> None:
    for line in _ingress_import_lines():
        assert "connectors.telegram" not in line, line
        assert "connectors" not in line, line

    leaked = _leaked_modules(_TELEGRAM_CHAIN)
    assert not {m for m in leaked if m.startswith("app.connectors")}, leaked


# --------------------------------------------------------------------------- #
# §27 (35-41) / §32 / §18 — boundary
# --------------------------------------------------------------------------- #
def test_wo083_35_production_catalog_unchanged(wired) -> None:
    names = [d.name for d in PRODUCTION_SOURCE_CATALOG]
    assert names == ["radio", "signal"], "PRODUCTION_SOURCE_CATALOG must be unchanged"
    assert "telegram" not in names
    # The ingress uses a single-source catalog, not the production catalog.
    assert wired.registered == ["telegram"]


def test_wo083_36_telegram_adapter_type_was_already_registered() -> None:
    default_factory = build_production_adapter_factory()
    # WO-013-008 already registers telegram in the production factory; WO-083
    # added no registration and no factory change.
    assert "telegram" in default_factory.registered_types()
    assert "whatsapp" not in default_factory.registered_types()


def test_wo083_37_telegram_source_definition_is_additive() -> None:
    definition = build_telegram_source_definition()
    assert definition.name == "telegram"
    assert definition.adapter_type == "telegram"
    assert definition.credentials_ref == "telegram/production"
    for secret_key in ("password", "token", "app_secret", "secret", "api_key"):
        assert secret_key not in definition.config

    factory = AdapterFactory()
    from app.event_sources.adapters.telegram_adapter_registration import (
        register_telegram_adapter,
    )

    register_telegram_adapter(factory)
    built = factory.create(definition)
    assert built.source_name() == "telegram"
    # The canonical Telegram leaf exposes no in-memory ACK buffer.
    assert built.read_events() == []


def test_wo083_38_shared_components_still_operational() -> None:
    """A structural sanity check that WO-083 did not fork shared components."""
    from app.event_sources.adapters.whatsapp_parser import WhatsAppPayloadNormalizer

    # Existing WhatsApp ingress normalizer untouched and still functional.
    assert WhatsAppPayloadNormalizer is not None
    # Canonical EventPipeline / EventFactory / AdapterRuntime APIs intact.
    assert hasattr(EventPipeline, "process")
    assert hasattr(EventFactory, "create_event")
    assert hasattr(AdapterRuntime, "submit_raw")

    # main.py (backend/main.py) must not reference the telegram ingress.
    main_py = _TELEGRAM_INGRESS_DIR.parent.parent / "main.py"
    assert main_py.is_file(), main_py
    assert "telegram_ingress" not in main_py.read_text(encoding="utf-8")
