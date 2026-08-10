"""
TACTICAL CORE — MQTT Source Adapter
WO-013-006

A WO-013 Source Adapter that receives MQTT messages and exposes them to
the WO-013 AdapterRuntime as raw event dictionaries.

APPROVED ARCHITECTURE: PASSIVE / INGEST-FED.

The adapter is a LEAF component:

    - It inherits lifecycle/thread-safety/health/idempotent start-stop
      from BaseEventSourceAdapter. It does NOT implement its own thread,
      supervisor, restart loop, reconnect loop, scheduler, background
      worker, event loop, or lifecycle state machine.
    - It is NOT an MQTT broker client. It does NOT connect to a broker,
      does NOT use paho-mqtt or asyncio, does NOT run loop_start()/
      loop_forever(). MQTT transport/input is fed in externally via
      ingest()/ingest_many().
    - It returns RAW DATA dictionaries from read_events(); it does NOT
      construct canonical Event objects. Event construction is performed
      by EventFactory through AdapterRuntime.
    - It NEVER accesses EventBus, the API layer, the database, or the
      event pipeline directly. The intended data flow is:

          MQTT transport/input
            -> MQTTSourceAdapter.ingest()
            -> internal transient hand-off queue
            -> AdapterRuntime.read_events()
            -> EventFactory.create_event()
            -> canonical Event
            -> EventPipeline

    - The internal queue is a transient hand-off queue, drained on every
      read_events() call. It is NOT a backpressure subsystem (no
      persistent queue, disk queue, retry queue, rate limiter, or
      unbounded buffer). Backpressure is a separate future Work Order.
    - It consumes configuration exclusively through SourceDefinition
      (config dict + credentials_ref reference). No second configuration
      system, no hardcoded credentials, no secret store. credentials_ref
      is treated strictly as a reference and is never read or resolved.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from ..config.source_definition import SourceDefinition
from .base_adapter import BaseEventSourceAdapter
from .mqtt_parser import MQTTPayloadNormalizer

logger = logging.getLogger(__name__)


class MQTTSourceAdapter(BaseEventSourceAdapter):
    """WO-013 source adapter for MQTT messages (passive / ingest-fed).

    The adapter receives MQTT message data through an ingest callback
    registered by the embedding application (e.g. wiring that connects an
    external MQTT transport to this adapter). The payloads are normalized
    into EventFactory-compatible raw dicts and queued for the
    AdapterRuntime to read via read_events().

    Constructor dependencies:
        definition: A SourceDefinition for this MQTT source. The adapter
            reads adapter-specific settings from `definition.config` and
            treats `definition.credentials_ref` strictly as a reference.
        normalizer: Optional MQTTPayloadNormalizer. Defaults to a shared
            instance.
    """

    def __init__(
        self,
        definition: SourceDefinition,
        normalizer: MQTTPayloadNormalizer | None = None,
    ) -> None:
        super().__init__()
        self._definition = definition
        self._normalizer = normalizer or MQTTPayloadNormalizer()
        self._queue: list[dict[str, Any]] = []
        self._queue_lock = threading.Lock()
        self._credentials_ref = definition.credentials_ref

        # Adapter-specific settings (opaque to the config layer).
        self._topics: Any = definition.config.get("topics")
        self._client_id: str | None = definition.config.get("client_id")

        logger.info(
            "MQTTSourceAdapter '%s' configured (topics=%r, "
            "credentials_ref_present=%s)",
            definition.name,
            self._topics,
            self._credentials_ref is not None,
        )

    # --- Interface: source identity ---

    def source_name(self) -> str:
        """Return the canonical source identifier for this adapter."""
        return "mqtt"

    # --- Interface: read path ---

    def read_events(self) -> list[dict[str, Any]]:
        """Return queued MQTT messages as raw event dicts.

        Each returned dict is normalized so EventFactory can convert it
        into a canonical Event. The queue is drained on every call. If
        the adapter is not running, this returns an empty list.
        """
        if not self._running:
            return []
        with self._queue_lock:
            pending = self._queue
            self._queue = []
        return pending

    # --- Ingest (embedding integration) ---

    def ingest(self, topic: str, payload: Any, **kwargs: Any) -> bool:
        """Accept one raw MQTT message into the adapter queue.

        This is the integration point an embedding application calls when
        an MQTT message arrives from the (external) transport. The message
        is normalized immediately so a malformed message is isolated here
        (dropped) rather than surfacing during read_events().

        Args:
            topic: MQTT topic the message arrived on.
            payload: MQTT message payload (str, bytes, or dict).
            **kwargs: Optional MQTT metadata: qos, retain, client_id,
                timestamp, correlation_id.

        Returns:
            True if the message was accepted, False if it was malformed
            and dropped.
        """
        raw_payload = payload
        if isinstance(payload, (bytes, bytearray)):
            try:
                raw_payload = payload.decode("utf-8", errors="strict")
            except UnicodeDecodeError as exc:
                logger.warning(
                    "MQTTSourceAdapter '%s' dropped non-UTF-8 payload on "
                    "topic %r: %s",
                    self._definition.name,
                    topic,
                    exc,
                )
                return False

        message: dict[str, Any] = {"topic": topic, "payload": raw_payload}
        for key in ("qos", "retain", "client_id", "timestamp", "correlation_id"):
            if key in kwargs and kwargs[key] is not None:
                message[key] = kwargs[key]

        try:
            raw = self._normalizer.normalize(message)
        except Exception as exc:  # noqa: BLE001 - isolate parser failure
            logger.warning(
                "MQTTSourceAdapter '%s' dropped malformed message on "
                "topic %r: %s",
                self._definition.name,
                topic,
                exc,
            )
            return False

        with self._queue_lock:
            self._queue.append(raw)
        return True

    def ingest_many(self, messages: list[dict[str, Any]]) -> int:
        """Accept a batch of raw MQTT messages.

        Each item is a dict with keys: topic, payload, and optionally
        qos/retain/client_id/timestamp/correlation_id. Returns the number
        of messages accepted. Malformed messages are isolated and dropped.
        """
        accepted = 0
        for message in messages:
            if not isinstance(message, dict):
                logger.warning(
                    "MQTTSourceAdapter '%s' dropped non-dict message in "
                    "batch",
                    self._definition.name,
                )
                continue
            topic = message.get("topic")
            payload = message.get("payload")
            if topic is None or payload is None:
                logger.warning(
                    "MQTTSourceAdapter '%s' dropped batch item missing "
                    "topic/payload",
                    self._definition.name,
                )
                continue
            kwargs = {
                k: message[k]
                for k in ("qos", "retain", "client_id", "timestamp",
                          "correlation_id")
                if k in message
            }
            if self.ingest(topic, payload, **kwargs):
                accepted += 1
        return accepted

    # --- Lifecycle (base contract) ---

    def start(self) -> None:
        """Start the adapter. Idempotent and thread-safe.

        Initialization is lightweight: no network connection is opened
        here (the adapter is passive / ingest-fed). Connection
        establishment and failure handling are owned by the external
        transport and AdapterRuntime via the read path.
        """
        super().start()

    def stop(self) -> None:
        """Stop the adapter. Idempotent and thread-safe.

        Releases queued message references. The base implementation
        guarantees idempotency and thread safety.
        """
        super().stop()
        with self._queue_lock:
            self._queue = []

    # --- Convenience accessors for tests / health ---

    def pending_count(self) -> int:
        """Number of queued, not-yet-read raw events."""
        with self._queue_lock:
            return len(self._queue)

    @property
    def adapter_type(self) -> str:
        """Adapter type identifier used for registration."""
        return "mqtt"

    # --- Builder helper (for registration wiring) ---

    @staticmethod
    def build(definition: SourceDefinition) -> "MQTTSourceAdapter":
        """Builder contract: SourceDefinition -> MQTTSourceAdapter.

        Used with AdapterFactory.register_type("mqtt", ...). Constructs
        a configured (not started) adapter instance.
        """
        return MQTTSourceAdapter(definition=definition)


def make_mqtt_adapter(definition: SourceDefinition) -> MQTTSourceAdapter:
    """Adapter builder compatible with AdapterFactory.register_type.

    Returns a configured, unstarted MQTTSourceAdapter for the given
    source definition.
    """
    return MQTTSourceAdapter(definition=definition)
