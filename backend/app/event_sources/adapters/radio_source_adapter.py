"""
TACTICAL CORE — Radio Source Adapter
WO-013-007

A WO-013 Source Adapter that receives radio transmissions and exposes them
to the WO-013 AdapterRuntime as raw event dictionaries.

The adapter is a LEAF component:

    - It inherits lifecycle/thread-safety/health/idempotent start-stop
      from BaseEventSourceAdapter. It does NOT implement its own thread,
      supervisor, restart loop, or lifecycle state machine.
    - It returns RAW DATA dictionaries from read_events(); it does NOT
      construct canonical Event objects. Event construction is performed
      by EventFactory through AdapterRuntime.
    - It NEVER accesses EventBus, the API layer, the database, or the
      event pipeline directly. The intended data flow is:

          Radio
            -> RadioSourceAdapter
            -> IEventSourceAdapter
            -> AdapterRuntime
            -> EventFactory
            -> canonical Event
            -> EventPipeline
            -> EventBus / persistence / downstream

    - It consumes configuration exclusively through SourceDefinition
      (config dict + credentials_ref reference). No second configuration
      system, no hardcoded credentials, no secret store.

The adapter is PASSIVE / INGEST-FED. It does NOT own radio transport: it
does not open serial ports, sockets, SDR libraries, vendor SDKs, worker
threads, or event loops. An external radio feed calls ingest()/ingest_many()
and the AdapterRuntime polls read_events().
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from ..config.source_definition import SourceDefinition
from .base_adapter import BaseEventSourceAdapter
from .radio_parser import RadioPayloadNormalizer

logger = logging.getLogger(__name__)


class RadioSourceAdapter(BaseEventSourceAdapter):
    """WO-013 source adapter for radio transmissions.

    The adapter receives radio transmission payloads through an ingest
    callback registered by the embedding application (e.g. wiring that
    connects a radio transport to this adapter). The payloads are
    normalized into EventFactory-compatible raw dicts and queued for the
    AdapterRuntime to read via read_events().

    Constructor dependencies:
        definition: A SourceDefinition for this radio source. The adapter
            reads adapter-specific settings from `definition.config` and
            treats `definition.credentials_ref` strictly as a reference.
        normalizer: Optional RadioPayloadNormalizer. Defaults to a shared
            instance.
    """

    def __init__(
        self,
        definition: SourceDefinition,
        normalizer: RadioPayloadNormalizer | None = None,
    ) -> None:
        super().__init__()
        self._definition = definition
        self._normalizer = normalizer or RadioPayloadNormalizer()
        self._queue: list[dict[str, Any]] = []
        self._queue_lock = threading.Lock()
        self._credentials_ref = definition.credentials_ref

        # Adapter-specific settings (opaque to the config layer).
        self._channel: str | None = definition.config.get("channel")
        self._device: str | None = definition.config.get("device")

        logger.info(
            "RadioSourceAdapter '%s' configured (channel=%r, "
            "credentials_ref_present=%s)",
            definition.name,
            self._channel,
            self._credentials_ref is not None,
        )

    # --- Interface: source identity ---

    def source_name(self) -> str:
        """Return the canonical source identifier for this adapter."""
        return "radio"

    # --- Interface: read path ---

    def read_events(self) -> list[dict[str, Any]]:
        """Return queued radio transmissions as raw event dicts.

        Each returned dict is normalized so EventFactory can convert it
        into a canonical Event (timestamp normalization, payload mapping,
        optional correlation_id preservation). If the adapter is not
        running, this returns an empty list.
        """
        if not self._running:
            return []
        with self._queue_lock:
            pending = self._queue
            self._queue = []
        return pending

    # --- Ingest (embedding integration) ---

    def ingest(self, payload: dict[str, Any]) -> bool:
        """Accept one raw radio transmission into the adapter queue.

        This is the integration point an embedding application calls when
        a radio transmission arrives. The payload is normalized immediately
        so a malformed payload is isolated here (dropped) rather than
        surfacing during read_events().

        Args:
            payload: Raw radio transmission payload (dict).

        Returns:
            True if the payload was accepted, False if it was malformed
            and dropped.
        """
        try:
            raw = self._normalizer.normalize(payload)
        except Exception as exc:  # noqa: BLE001 - isolate parser failure
            logger.warning(
                "RadioSourceAdapter '%s' dropped malformed payload: %s",
                self._definition.name,
                exc,
            )
            return False

        with self._queue_lock:
            self._queue.append(raw)
        return True

    def ingest_many(self, payloads: list[dict[str, Any]]) -> int:
        """Accept a batch of raw radio transmissions.

        Returns the number of payloads accepted. Malformed payloads are
        isolated and dropped.
        """
        accepted = 0
        for payload in payloads:
            if self.ingest(payload):
                accepted += 1
        return accepted

    # --- Lifecycle (base contract) ---

    def start(self) -> None:
        """Start the adapter. Idempotent and thread-safe.

        Initialization is lightweight: resources are tracked so stop()
        can release them. No hardware/network connection is opened here;
        connection establishment and failure handling are owned by
        AdapterRuntime via the read path.
        """
        super().start()

    def stop(self) -> None:
        """Stop the adapter. Idempotent and thread-safe.

        Releases queued transmission references. The base implementation
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
        return "radio"

    # --- Builder helper (for registration wiring) ---

    @staticmethod
    def build(definition: SourceDefinition) -> "RadioSourceAdapter":
        """Builder contract: SourceDefinition -> RadioSourceAdapter.

        Used with AdapterFactory.register_type("radio", ...). Constructs
        a configured (not started) adapter instance.
        """
        return RadioSourceAdapter(definition=definition)


def make_radio_adapter(definition: SourceDefinition) -> RadioSourceAdapter:
    """Adapter builder compatible with AdapterFactory.register_type.

    Returns a configured, unstarted RadioSourceAdapter for the given
    source definition.
    """
    return RadioSourceAdapter(definition=definition)
