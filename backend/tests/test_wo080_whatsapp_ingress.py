"""WO-080 — WhatsApp inbound webhook ingress (acceptance tests).

Proves the WhatsApp ingress implemented by WO-080 across the focused and
integration surfaces the WO requires:

    UNIT
        * Meta GET verification challenge (success / failure)
        * X-Hub-Signature-256 verification over the RAW body
        * payload normalization (text / media reference / statuses-only /
          malformed)
        * deterministic identity (same/different phone_number_id+message_id)
        * synchronous ingress seam (AdapterRuntime.submit_raw) semantics
        * source registration through the existing AdapterFactory mechanism
        * observation event-type derivation through the ACTUAL
          CanonicalEventToObservationAdapter.derive_event_type path

    INTEGRATION
        * HTTP webhook -> normalization -> AdapterRuntime -> EventFactory ->
          EventPipeline -> durable repository -> Observation (REAL production
          composition, not mocks)
        * commit-before-ACK: HTTP 200 implies a durable canonical event
        * duplicate delivery -> exactly ONE durable canonical event
        * restart: a fresh runtime instance over the same durable store does
          not create a second event for the same logical message
        * durability failure -> HTTP != 200

No live Meta API call, no credentials, no media download, and no network
connection is exercised.  Test credentials are obviously synthetic placeholders.
"""

from __future__ import annotations

import copy
import json

import pytest
from fastapi.testclient import TestClient

import app.database.session as session_mod
from app.database.base import Base
from app.database.session import configure_session_manager, get_session_manager
from app.event.event import Event
from app.event.event_types import EventType
from app.event_repository.durable.sqlalchemy_event_repository import (
    SQLAlchemyEventRepository,
)
from app.event_sources.adapters.whatsapp_adapter_registration import (
    WHATSAPP_ADAPTER_TYPE,
    register_whatsapp_adapter,
)
from app.event_sources.adapters.whatsapp_parser import (
    WhatsAppParseError,
    WhatsAppPayloadNormalizer,
)
from app.event_sources.adapters.whatsapp_source_adapter import (
    WhatsAppSourceAdapter,
)
from app.event_sources.config.adapter_factory import AdapterFactory
from app.event_sources.config.production_source_config import (
    build_production_adapter_factory,
    build_production_source_provider,
    build_whatsapp_source_definition,
)
from app.event_sources.factory.event_factory import EventFactory
from app.event_sources.identity.event_identity import EventIdentityResolver
from app.event_sources.runtime.adapter_runtime import AdapterRuntime, IngestStatus
from app.intelligence.observation.repository import ObservationRepository
from app.observation.canonical_adapter import CanonicalEventToObservationAdapter
from app.observation.models import EVENT_TYPE_MAPPINGS
from app.whatsapp_ingress.app import create_whatsapp_ingress_app
from app.whatsapp_ingress.composition import build_whatsapp_ingress_runtime
from app.whatsapp_ingress.config import (
    WhatsAppIngressConfig,
    WhatsAppIngressConfigError,
)
from app.whatsapp_ingress.service import WhatsAppIngressService
from app.whatsapp_ingress.signature import compute_signature, verify_signature

# Synthetic, non-secret test credentials (never real Meta values).
APP_SECRET = "test-app-secret-not-a-real-meta-secret"
VERIFY_TOKEN = "test-verify-token"
PHONE_NUMBER_ID = "PNID-TEST-1"
WA_SENDER = "15550002222"


def _text_webhook(
    message_id: str = "wamid.TEST-TEXT-1",
    body: str = "Burevii-2 na zviazku",
    phone_number_id: str = PHONE_NUMBER_ID,
) -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "WABA-TEST",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "15550001111",
                                "phone_number_id": phone_number_id,
                            },
                            "contacts": [
                                {"profile": {"name": "test"}, "wa_id": WA_SENDER}
                            ],
                            "messages": [
                                {
                                    "from": WA_SENDER,
                                    "id": message_id,
                                    "timestamp": "1735689600",
                                    "type": "text",
                                    "text": {"body": body},
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }


def _image_webhook(message_id: str = "wamid.TEST-IMG-1") -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "WABA-TEST",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "metadata": {"phone_number_id": PHONE_NUMBER_ID},
                            "messages": [
                                {
                                    "from": WA_SENDER,
                                    "id": message_id,
                                    "timestamp": "1735689700",
                                    "type": "image",
                                    "image": {
                                        "id": "MEDIA-REF-1",
                                        "mime_type": "image/jpeg",
                                        "sha256": "deadbeef",
                                        "caption": "shema",
                                    },
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }


def _statuses_webhook() -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "WABA-TEST",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "metadata": {"phone_number_id": PHONE_NUMBER_ID},
                            "statuses": [
                                {
                                    "id": "wamid.TEST-TEXT-1",
                                    "status": "delivered",
                                    "recipient_id": WA_SENDER,
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }


@pytest.fixture()
def env(tmp_path):
    """Isolated file database + canonical session manager, reset afterwards."""
    session_mod._session_manager = None
    db_path = str(tmp_path / "wo080.db")
    mgr = configure_session_manager(f"sqlite:///{db_path}")
    Base.metadata.create_all(mgr.engine)
    yield {"db_path": db_path, "mgr": mgr}
    session_mod._session_manager = None


@pytest.fixture()
def wired(env):
    """A REAL production-composition WhatsApp ingress runtime on the test DB."""
    runtime = build_whatsapp_ingress_runtime()
    yield runtime
    runtime.stop()


@pytest.fixture()
def client(wired):
    """A FastAPI webhook client bound to the real ingress runtime."""
    service = WhatsAppIngressService(adapter_runtime=wired.adapter_runtime)
    app = create_whatsapp_ingress_app(
        service=service,
        app_secret=APP_SECRET,
        verify_token=VERIFY_TOKEN,
        webhook_path="/webhook",
    )
    return TestClient(app)


def _repo():
    return SQLAlchemyEventRepository(session_manager=get_session_manager())


def _whatsapp_events():
    return [e for e in _repo().list_all() if e.source == "whatsapp"]


def _post(client: TestClient, payload: dict, secret: str = APP_SECRET):
    body = json.dumps(payload).encode("utf-8")
    headers = {
        "X-Hub-Signature-256": compute_signature(secret, body),
        "Content-Type": "application/json",
    }
    return client.post("/webhook", content=body, headers=headers)


def _expected_event_id(payload: dict) -> str:
    raw = WhatsAppPayloadNormalizer().normalize_webhook(payload)[0]
    resolved = EventIdentityResolver().resolve(raw, "whatsapp")
    assert resolved is not None, "whatsapp identity policy must be deduplicable"
    return resolved


# --------------------------------------------------------------------------- #
# §28 (1,2) — Meta GET verification
# --------------------------------------------------------------------------- #
def test_wo080_01_get_verification_success(client) -> None:
    r = client.get(
        "/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": VERIFY_TOKEN,
            "hub.challenge": "CHALLENGE-42",
        },
    )
    assert r.status_code == 200
    assert r.text == "CHALLENGE-42"


def test_wo080_02_get_verification_failure(client) -> None:
    bad_token = client.get(
        "/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "wrong-token",
            "hub.challenge": "CHALLENGE-42",
        },
    )
    assert bad_token.status_code == 403
    assert "CHALLENGE-42" not in bad_token.text

    bad_mode = client.get(
        "/webhook",
        params={
            "hub.mode": "unsubscribe",
            "hub.verify_token": VERIFY_TOKEN,
            "hub.challenge": "CHALLENGE-42",
        },
    )
    assert bad_mode.status_code == 403


# --------------------------------------------------------------------------- #
# §28 (3,4) — signature verification over the raw body
# --------------------------------------------------------------------------- #
def test_wo080_03_signature_unit_valid_and_invalid() -> None:
    body = b'{"hello":"world"}'
    good = compute_signature(APP_SECRET, body)
    assert verify_signature(APP_SECRET, body, good) is True
    assert verify_signature(APP_SECRET, body, "sha256=deadbeef") is False
    assert verify_signature(APP_SECRET, body, None) is False
    assert verify_signature(APP_SECRET, body, "not-a-signature") is False
    # A different body (even same JSON semantics) must not verify.
    assert verify_signature(APP_SECRET, b'{"hello": "world"}', good) is False
    # A different secret must not verify.
    assert verify_signature("other-secret", body, good) is False


def test_wo080_04_post_valid_signature_ingests(client) -> None:
    r = _post(client, _text_webhook())
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "accepted"
    assert r.json()["event_ids"] == [_expected_event_id(_text_webhook())]


def test_wo080_04b_post_invalid_signature_rejected_without_ingest(client) -> None:
    body = json.dumps(_text_webhook()).encode("utf-8")
    r = client.post(
        "/webhook",
        content=body,
        headers={
            "X-Hub-Signature-256": compute_signature("wrong-secret", body),
            "Content-Type": "application/json",
        },
    )
    assert r.status_code == 401
    assert _whatsapp_events() == [], "invalid signature must not reach the pipeline"


# --------------------------------------------------------------------------- #
# §28 (5) — malformed JSON ; §28 (6) — unsupported payload
# --------------------------------------------------------------------------- #
def test_wo080_05_malformed_json_rejected(client) -> None:
    body = b"{not-json"
    r = client.post(
        "/webhook",
        content=body,
        headers={
            "X-Hub-Signature-256": compute_signature(APP_SECRET, body),
            "Content-Type": "application/json",
        },
    )
    assert r.status_code == 400
    assert _whatsapp_events() == []


def test_wo080_06_unsupported_payload_rejected(client) -> None:
    r = _post(client, {"foo": "bar"})  # authentic, but no 'entry'
    assert r.status_code == 400
    assert _whatsapp_events() == []


# --------------------------------------------------------------------------- #
# §28 (7) — valid text message ; §28 (8) — valid media descriptor
# --------------------------------------------------------------------------- #
def test_wo080_07_valid_text_message_persisted(client) -> None:
    r = _post(client, _text_webhook())
    assert r.status_code == 200
    event_id = _expected_event_id(_text_webhook())
    assert _repo().exists(event_id)
    event = _repo().get(event_id)
    assert event.source == "whatsapp"
    assert event.payload["message_id"] == "wamid.TEST-TEXT-1"
    assert event.payload["phone_number_id"] == PHONE_NUMBER_ID
    assert event.payload["sender"] == WA_SENDER
    assert event.payload["message_type"] == "text"
    assert event.payload["text"] == "Burevii-2 na zviazku"


def test_wo080_08_valid_media_descriptor_reference_only(client) -> None:
    r = _post(client, _image_webhook())
    assert r.status_code == 200
    event = _repo().get(_expected_event_id(_image_webhook()))
    media = event.payload["media"]
    # Reference only: no bytes, no download, hash only when Meta supplied it.
    assert media["media_id"] == "MEDIA-REF-1"
    assert media["mime_type"] == "image/jpeg"
    assert media["sha256"] == "deadbeef"
    assert "bytes" not in media and "data" not in media


# --------------------------------------------------------------------------- #
# §28 (9) — missing required identity material
# --------------------------------------------------------------------------- #
def test_wo080_09_missing_identity_material_rejected(client) -> None:
    no_id = _text_webhook()
    del no_id["entry"][0]["changes"][0]["value"]["messages"][0]["id"]
    r = _post(client, no_id)
    assert r.status_code == 400
    assert _whatsapp_events() == []

    # Missing phone_number_id: normalizer rejects deterministically.
    normalizer = WhatsAppPayloadNormalizer()
    missing_pn = _text_webhook()
    del missing_pn["entry"][0]["changes"][0]["value"]["metadata"]["phone_number_id"]
    with pytest.raises(WhatsAppParseError):
        normalizer.normalize_webhook(missing_pn)


def test_wo080_09b_statuses_only_webhook_acknowledged_without_event(client) -> None:
    r = _post(client, _statuses_webhook())
    assert r.status_code == 200
    assert r.json()["event_ids"] == []
    assert _whatsapp_events() == []


# --------------------------------------------------------------------------- #
# §28 (10) / §31 — duplicate delivery collapses to ONE durable event
# --------------------------------------------------------------------------- #
def test_wo080_10_duplicate_delivery_one_durable_event(client) -> None:
    first = _post(client, _text_webhook())
    second = _post(client, copy.deepcopy(_text_webhook()))
    assert first.status_code == 200 and second.status_code == 200
    assert second.json()["duplicate"] is True

    events = _whatsapp_events()
    assert len(events) == 1, "Meta retry must not create a second canonical event"
    assert events[0].event_id == _expected_event_id(_text_webhook())


# --------------------------------------------------------------------------- #
# §18 / §13 — deterministic identity
# --------------------------------------------------------------------------- #
def test_wo080_11_deterministic_identity_matrix() -> None:
    resolver = EventIdentityResolver()
    normalizer = WhatsAppPayloadNormalizer()

    raw = normalizer.normalize_webhook(_text_webhook())[0]

    def _raw(payload):
        return normalizer.normalize_webhook(payload)[0]

    # Test 1: same phone_number_id + message_id -> same identity.
    same_a = resolver.resolve(raw, "whatsapp")
    same_b = resolver.resolve(_raw(_text_webhook()), "whatsapp")
    assert same_a is not None and same_a == same_b

    # Test 2: same phone_number_id, different message_id -> different identity.
    diff_msg = resolver.resolve(
        _raw(_text_webhook(message_id="wamid.TEST-TEXT-2")), "whatsapp"
    )
    assert diff_msg is not None and diff_msg != same_a

    # Test 3: different phone_number_id, same message_id -> different identity.
    diff_pn = resolver.resolve(
        _raw(_text_webhook(phone_number_id="PNID-TEST-2")), "whatsapp"
    )
    assert diff_pn is not None and diff_pn != same_a

    # No silent UUID4 fallback for a valid WhatsApp message: the resolver
    # returns the SAME value on repeat, which a fresh UUID4 never would.
    assert resolver.resolve(raw, "whatsapp") == same_a

    # Missing identity material -> non-deduplicable (None), never a UUID5.
    assert resolver.resolve({"message_id": "x"}, "whatsapp") is None
    assert resolver.resolve({"phone_number_id": "x"}, "whatsapp") is None


# --------------------------------------------------------------------------- #
# §19 / §33 — observation derivation through the ACTUAL path
# --------------------------------------------------------------------------- #
def test_wo080_12_derive_event_type_through_canonical_adapter() -> None:
    adapter = CanonicalEventToObservationAdapter()
    event = Event(
        event_type=EventType.CUSTOM,
        source="whatsapp",
        payload={"message_id": "wamid.TEST-TEXT-1", "phone_number_id": PHONE_NUMBER_ID},
    )
    assert adapter.derive_event_type(event) == "whatsapp.message"
    mapped = adapter.to_observation_dict(event)
    assert mapped["event_type"] == "whatsapp.message"


def test_wo080_12b_observation_mapping_registered() -> None:
    mapping = EVENT_TYPE_MAPPINGS["whatsapp.message"]
    assert mapping.observation_type == "other"
    assert "chat_id" not in mapping.required_fields
    assert set(mapping.required_fields) == {"message_id", "phone_number_id"}


# --------------------------------------------------------------------------- #
# §29 — INTEGRATION: webhook -> durable repository -> Observation
# --------------------------------------------------------------------------- #
def test_wo080_13_webhook_to_observation_integration(client) -> None:
    r = _post(client, _text_webhook())
    assert r.status_code == 200
    event_id = _expected_event_id(_text_webhook())

    # durable canonical event
    assert _repo().exists(event_id)

    # canonical Observation (whatsapp.message) via the real delivery path
    obs = ObservationRepository(
        get_session_manager().get_session()
    ).get_by_immutable_id(event_id)
    assert obs is not None
    assert obs.source == "whatsapp"
    assert obs.observation_type == "other"
    evidence = obs.evidence_payload or {}
    assert evidence.get("event_type") == "whatsapp.message"
    assert evidence.get("raw_data", {}).get("message_id") == "wamid.TEST-TEXT-1"
    assert evidence.get("source") == WA_SENDER
    assert evidence.get("content") == "Burevii-2 na zviazku"
    assert evidence.get("channel") == PHONE_NUMBER_ID


# --------------------------------------------------------------------------- #
# §30 — commit before ACK
# --------------------------------------------------------------------------- #
def test_wo080_14_success_200_implies_durable_event(client) -> None:
    r = _post(client, _text_webhook())
    assert r.status_code == 200
    for event_id in r.json()["event_ids"]:
        assert _repo().exists(event_id), "HTTP 200 must imply durability"


def test_wo080_15_persistence_failure_is_not_200(env) -> None:
    """Durable persistence failure must NOT be acknowledged with HTTP 200."""

    class _FakeAdapter:
        def source_name(self) -> str:
            return "whatsapp"

    class _RaisingPipeline:
        def process(self, event):  # noqa: ANN001
            raise RuntimeError("simulated durable commit failure")

    runtime = AdapterRuntime(
        adapter=_FakeAdapter(),
        factory=EventFactory(identity_resolver=EventIdentityResolver()),
        pipeline=_RaisingPipeline(),
        name="whatsapp",
    )
    runtime.set_ingest_durability_probe(lambda event_id: False)

    # Seam-level: the failure is reported, never swallowed.
    result = runtime.submit_raw(
        WhatsAppPayloadNormalizer().normalize_webhook(_text_webhook())[0]
    )
    assert result.status == IngestStatus.FAILURE
    assert result.durable is False

    # HTTP-level: the ingress translates it to a non-200 status.
    service = WhatsAppIngressService(adapter_runtime=runtime)
    outcome = service.handle_webhook(_text_webhook())
    assert outcome.status_code == 503


def test_wo080_15b_unconfirmed_durability_is_not_acked(env) -> None:
    """A successful pipeline run whose durability cannot be confirmed -> 5xx."""

    class _FakeAdapter:
        def source_name(self) -> str:
            return "whatsapp"

    class _OkPipeline:
        def process(self, event):  # noqa: ANN001
            return True

    runtime = AdapterRuntime(
        adapter=_FakeAdapter(),
        factory=EventFactory(identity_resolver=EventIdentityResolver()),
        pipeline=_OkPipeline(),
        name="whatsapp",
    )
    # Probe says the event is NOT durable -> must not be acknowledged.
    runtime.set_ingest_durability_probe(lambda event_id: False)
    outcome = WhatsAppIngressService(adapter_runtime=runtime).handle_webhook(
        _text_webhook()
    )
    assert outcome.status_code == 503


# --------------------------------------------------------------------------- #
# §32 — restart / recovery: deterministic identity survives a fresh runtime
# --------------------------------------------------------------------------- #
def test_wo080_16_restart_does_not_duplicate(env) -> None:
    first_runtime = build_whatsapp_ingress_runtime()
    try:
        service = WhatsAppIngressService(adapter_runtime=first_runtime.adapter_runtime)
        assert service.handle_webhook(_text_webhook()).status_code == 200
    finally:
        first_runtime.stop()

    assert len(_whatsapp_events()) == 1

    # Fresh runtime instance over the SAME durable store (simulates a restart).
    second_runtime = build_whatsapp_ingress_runtime()
    try:
        service2 = WhatsAppIngressService(adapter_runtime=second_runtime.adapter_runtime)
        outcome = service2.handle_webhook(_text_webhook())
        assert outcome.status_code == 200
        assert outcome.duplicate is True
    finally:
        second_runtime.stop()

    assert len(_whatsapp_events()) == 1, "restart must not create a second event"


# --------------------------------------------------------------------------- #
# §26 / §27 — source registration through the existing composition mechanism
# --------------------------------------------------------------------------- #
def test_wo080_17_adapter_registration_and_composition(wired) -> None:
    # The ingress runtime registered the whatsapp source through the EXISTING
    # mechanism (SourceDefinition -> AdapterFactory -> ProductionSourceRegistrar
    # -> AdapterSupervisor).
    assert wired.registered == ["whatsapp"]
    assert wired.adapter_runtime.name == "whatsapp"
    adapter = wired.adapter_runtime._adapter
    assert isinstance(adapter, WhatsAppSourceAdapter)
    assert adapter.source_name() == "whatsapp"
    assert adapter.adapter_type == "whatsapp"
    # No in-memory ACK buffer (WO-080 / ADR-015 §7.2).
    assert adapter.read_events() == []

    # The production factory does NOT gain whatsapp by default; the ingress
    # composition adds it explicitly via the existing register_type mechanism.
    default_factory = build_production_adapter_factory()
    assert "whatsapp" not in default_factory.registered_types()
    register_whatsapp_adapter(default_factory)
    assert WHATSAPP_ADAPTER_TYPE in default_factory.registered_types()

    # The whatsapp definition is resolvable by an AdapterFactory.
    definition = build_whatsapp_source_definition()
    assert definition.adapter_type == "whatsapp"
    assert definition.credentials_ref == "whatsapp/production"
    for secret_key in ("password", "token", "app_secret", "secret", "api_key"):
        assert secret_key not in definition.config
    factory = AdapterFactory()
    register_whatsapp_adapter(factory)
    built = factory.create(definition)
    assert isinstance(built, WhatsAppSourceAdapter)


def test_wo080_17b_no_second_event_architecture() -> None:
    """The ingress must reuse the canonical path, not a duplicate one."""
    import app.whatsapp_ingress.service as service_mod

    # The service drives the canonical path exclusively through the runtime.
    assert hasattr(service_mod, "WhatsAppIngressService")
    for forbidden in ("EventFactory", "EventPipeline", "DurableCanonicalEventRepository"):
        assert not hasattr(service_mod, forbidden)


# --------------------------------------------------------------------------- #
# §15 — credential / configuration boundary
# --------------------------------------------------------------------------- #
def test_wo080_18_config_fails_closed_and_masks_secrets() -> None:
    with pytest.raises(WhatsAppIngressConfigError):
        WhatsAppIngressConfig.from_env({})  # nothing configured

    with pytest.raises(WhatsAppIngressConfigError):
        WhatsAppIngressConfig.from_env(
            {"WHATSAPP_APP_SECRET": "s", "WHATSAPP_VERIFY_TOKEN": "t"}
        )  # missing DATABASE_URL

    cfg = WhatsAppIngressConfig.from_env(
        {
            "WHATSAPP_APP_SECRET": "secret-value",
            "WHATSAPP_VERIFY_TOKEN": "token-value",
            "DATABASE_URL": "sqlite:///x.db",
        }
    )
    assert cfg.webhook_path == "/webhook"
    assert cfg.port == 8020
    # Secrets are never rendered.
    assert "secret-value" not in repr(cfg)
    assert "token-value" not in repr(cfg)


def test_wo080_18b_normalizer_unit_cases() -> None:
    normalizer = WhatsAppPayloadNormalizer()
    with pytest.raises(WhatsAppParseError):
        normalizer.normalize_webhook({})
    with pytest.raises(WhatsAppParseError):
        normalizer.normalize_webhook({"entry": "not-a-list"})

    # A webhook with two messages normalizes to two raw dicts, same PN scope.
    two = _text_webhook()
    two["entry"][0]["changes"][0]["value"]["messages"].append(
        {
            "from": WA_SENDER,
            "id": "wamid.TEST-TEXT-2",
            "timestamp": "1735689601",
            "type": "text",
            "text": {"body": "druhe"},
        }
    )
    raws = normalizer.normalize_webhook(two)
    assert [r["message_id"] for r in raws] == [
        "wamid.TEST-TEXT-1",
        "wamid.TEST-TEXT-2",
    ]
    assert all(r["phone_number_id"] == PHONE_NUMBER_ID for r in raws)

    # An unknown category is ingested metadata-only (never rejected: rejecting
    # an authentic message would make Meta retry it indefinitely).
    unknown = _text_webhook()
    msg = unknown["entry"][0]["changes"][0]["value"]["messages"][0]
    msg.pop("text")
    msg["type"] = "reaction"
    raw = normalizer.normalize_webhook(unknown)[0]
    assert raw["message_type"] == "reaction"
    assert raw["text"] == ""
