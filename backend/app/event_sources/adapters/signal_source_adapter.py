"""
TACTICAL CORE — Signal Source Adapter
WO-013-005

A WO-013 Source Adapter that receives Signal messages and exposes them to
the WO-013 AdapterRuntime as raw event dictionaries.

The adapter is a LEAF component:

    - It inherits lifecycle/thread-safety/health/idempotent start-stop
      from BaseEventSourceAdapter. It does NOT implement its own thread,
      supervisor, restart loop, or lifecycle state machine.
    - It returns RAW DATA dictionaries from read_events(); it does NOT
      construct canonical Event objects. Event construction is performed
      by EventFactory through AdapterRuntime.
    - It NEVER accesses EventBus, the API layer, the database, or the
      event pipeline directly. The intended data flow is:

          Signal
            -> SignalSourceAdapter
            -> IEventSourceAdapter
            -> AdapterRuntime
            -> EventFactory
            -> canonical Event
            -> EventPipeline
            -> EventBus / persistence / downstream

    - It consumes configuration exclusively through SourceDefinition
      (config dict + credentials_ref reference). No second configuration
      system, no hardcoded credentials, no secret store.

WO-075 — injectable transport seam:

    - The adapter optionally receives a ``SignalTransport`` (default: None).
      When present, ``start()`` hands the adapter's own ``ingest`` callable to
      the transport (``transport.start(self.ingest)``) and ``stop()`` stops the
      transport.  The transport is therefore the ONLY producer that feeds
      Signal payloads into the canonical path, and it remains a leaf: it is
      injected by the production composition (through the existing
      ``AdapterFactory`` registration mechanism) and never reaches the
      EventBus / pipeline / database directly.
    - When no transport is injected the adapter is a purely passive queue,
      exactly as before WO-075 (full backward compatibility).
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from ..config.source_definition import SourceDefinition
from .base_adapter import BaseEventSourceAdapter
from .signal_parser import SignalPayloadNormalizer
from .signal_transport import SignalTransport

logger = logging.getLogger(__name__)


class SignalSourceAdapter(BaseEventSourceAdapter):
    """WO-013 source adapter for Signal messages.

    The adapter receives Signal message payloads through an ingest
    callback registered by the embedding application (e.g. wiring that
    connects a Signal transport to this adapter). The payloads are
    normalized into EventFactory-compatible raw dicts and queued for the
    AdapterRuntime to read via read_events().

    Constructor dependencies:
        definition: A SourceDefinition for this signal source. The adapter
            reads adapter-specific settings from `definition.config` and
            treats `definition.credentials_ref` strictly as a reference.
        normalizer: Optional SignalPayloadNormalizer. Defaults to a shared
            instance.
        transport: Optional SignalTransport (WO-075). When provided, the
            adapter drives its lifecycle: ``start()`` calls
            ``transport.start(self.ingest)`` and ``stop()`` calls
            ``transport.stop()``. When None (default), the adapter is a
            passive queue and behaves exactly as it did before WO-075.
    """

    def __init__(
        self,
        definition: SourceDefinition,
        normalizer: SignalPayloadNormalizer | None = None,
        transport: SignalTransport | None = None,
    ) -> None:
        super().__init__()
        self._definition = definition
        self._normalizer = normalizer or SignalPayloadNormalizer()
        self._queue: list[dict[str, Any]] = []
        self._queue_lock = threading.Lock()
        self._credentials_ref = definition.credentials_ref
        self._transport = transport
        self._transport_started = False
        self._transport_lock = threading.Lock()

        # Adapter-specific settings (opaque to the config layer).
        self._channel: str | None = definition.config.get("channel")
        self._account: str | None = definition.config.get("account")

        logger.info(
            "SignalSourceAdapter '%s' configured (channel=%r, "
            "credentials_ref_present=%s, transport=%s)",
            definition.name,
            self._channel,
            self._credentials_ref is not None,
            type(transport).__name__ if transport is not None else None,
        )

    # --- Interface: source identity ---

    def source_name(self) -> str:
        """Return the canonical source identifier for this adapter."""
        return "signal"

    # --- Interface: read path ---

    def read_events(self) -> list[dict[str, Any]]:
        """Return queued Signal messages as raw event dicts.

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
        """Accept one raw Signal payload into the adapter queue.

        This is the integration point an embedding application calls when
        a Signal message arrives. The payload is normalized immediately so
        a malformed payload is isolated here (dropped) rather than
        surfacing during read_events().

        Args:
            payload: Raw Signal message payload (dict).

        Returns:
            True if the payload was accepted, False if it was malformed
            and dropped.
        """
        try:
            raw = self._normalizer.normalize(payload)
        except Exception as exc:  # noqa: BLE001 - isolate parser failure
            logger.warning(
                "SignalSourceAdapter '%s' dropped malformed payload: %s",
                self._definition.name,
                exc,
            )
            return False

        with self._queue_lock:
            self._queue.append(raw)
        return True

    def ingest_many(self, payloads: list[dict[str, Any]]) -> int:
        """Accept a batch of raw Signal payloads.

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
        can release them. No network connection is opened here; connection
        establishment and failure handling are owned by AdapterRuntime via
        the read path.

        WO-075: when an injectable transport was supplied, the adapter hands
        its own ``ingest`` callable to the transport here (exactly once per
        start).  A transport ``start()`` failure propagates to the caller —
        i.e. into the canonical ``AdapterRuntime`` runtime-level failure path —
        rather than being silently ignored.
        """
        super().start()
        self._start_transport()

    def stop(self) -> None:
        """Stop the adapter. Idempotent and thread-safe.

        WO-075: the injected transport is stopped FIRST (so no new payload can
        be fed while the adapter is shutting down), then queued message
        references are released. The base implementation guarantees
        idempotency and thread safety; transport stop failures are isolated
        and never prevent the adapter from stopping.
        """
        self._stop_transport()
        super().stop()
        with self._queue_lock:
            self._queue = []

    # --- WO-075 transport lifecycle (idempotent) ---

    def _start_transport(self) -> None:
        """Start the injected transport once (no-op when none is injected)."""
        transport = self._transport
        if transport is None:
            return
        with self._transport_lock:
            if self._transport_started:
                return
            transport.start(self.ingest)
            self._transport_started = True

    def _stop_transport(self) -> None:
        """Stop the injected transport once (best-effort, isolated)."""
        transport = self._transport
        if transport is None:
            return
        with self._transport_lock:
            if not self._transport_started:
                return
            try:
                transport.stop()
            except Exception as exc:  # noqa: BLE001 - isolate transport stop
                logger.warning(
                    "SignalSourceAdapter '%s' transport stop error: %s",
                    self._definition.name,
                    exc,
                )
            finally:
                self._transport_started = False

    @property
    def transport(self) -> SignalTransport | None:
        """The injected transport (or None for a passive queue adapter)."""
        return self._transport

    @property
    def transport_started(self) -> bool:
        """True while the injected transport has been started and not stopped."""
        with self._transport_lock:
            return self._transport_started

    # --- Convenience accessors for tests / health ---

    def pending_count(self) -> int:
        """Number of queued, not-yet-read raw events."""
        with self._queue_lock:
            return len(self._queue)

    @property
    def adapter_type(self) -> str:
        """Adapter type identifier used for registration."""
        return "signal"

    # --- Builder helper (for registration wiring) ---

    @staticmethod
    def build(definition: SourceDefinition) -> "SignalSourceAdapter":
        """Builder contract: SourceDefinition -> SignalSourceAdapter.

        Used with AdapterFactory.register_type("signal", ...). Constructs
        a configured (not started) adapter instance.
        """
        return SignalSourceAdapter(definition=definition)


def make_signal_adapter(definition: SourceDefinition) -> SignalSourceAdapter:
    """Adapter builder compatible with AdapterFactory.register_type.

    Returns a configured, unstarted SignalSourceAdapter for the given
    source definition.  No transport is injected: the adapter is a passive
    queue (pre-WO-075 behaviour).
    """
    return SignalSourceAdapter(definition=definition)


def make_signal_adapter_with_transport(
    transport: SignalTransport,
):
    """Return an AdapterFactory builder that injects ``transport``.

    The returned callable has the same contract as ``make_signal_adapter``
    (``SourceDefinition -> SignalSourceAdapter``) but binds the supplied
    injectable ``SignalTransport`` to the adapter it builds.  This is the
    WO-075 injection seam used by ``register_signal_adapter`` /
    ``build_production_adapter_factory``.
    """

    def _build(definition: SourceDefinition) -> SignalSourceAdapter:
        return SignalSourceAdapter(definition=definition, transport=transport)

    return _build
