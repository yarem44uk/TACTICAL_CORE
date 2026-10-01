"""TACTICAL CORE — WhatsApp Cloud API Source Adapter
WO-080

A WO-013 Source Adapter that represents the WhatsApp Cloud API inbound webhook
source inside the canonical source registry and the production composition.

The adapter is a LEAF component:

    - It inherits lifecycle / thread-safety / health / idempotent start-stop
      from ``BaseEventSourceAdapter``.  It implements no thread, supervisor,
      restart loop, or lifecycle state machine of its own.
    - It consumes configuration exclusively through ``SourceDefinition``
      (config dict + ``credentials_ref`` reference).  No second configuration
      system, no hardcoded credentials, no secret store.
    - It NEVER constructs a canonical Event and NEVER touches the EventBus, the
      API layer, the database, or the event pipeline directly:

          Meta Cloud API
            -> WhatsApp Webhook Ingress process (HTTP, separate process)
            -> signature verification (X-Hub-Signature-256, raw body)
            -> WhatsAppPayloadNormalizer.normalize_webhook()
            -> AdapterRuntime.submit_raw()        <-- synchronous seam (WO-080)
            -> EventFactory.create_event()
            -> canonical app.event.Event
            -> EventPipeline.process()            <-- durable commit
            -> DurableCanonicalEventRepository -> Observation -> Operator Wall

WHY THIS ADAPTER HAS NO QUEUE (WO-080 / ADR-015 §7):

    Signal and Telegram are asynchronous sources: a transport enqueues payloads
    into the adapter and the ``AdapterRuntime`` polling loop drains them.  The
    WhatsApp ingress is SYNCHRONOUS and must honour **commit-before-ACK**: HTTP
    200 is returned only after the canonical event is durably committed.

    An in-memory adapter queue is therefore NOT an acceptable acknowledgement
    point (a crash between ACK and commit would lose the message silently).
    This adapter deliberately exposes NO buffer and NO ``ingest`` queue:
    ``read_events()`` always returns an empty list, and the ingress drives the
    canonical path through ``AdapterRuntime.submit_raw`` — the same factory/
    pipeline path, but with an explicit synchronous durable result.

    The adapter's remaining responsibilities are exactly the leaf ones shared
    with every other source: source identity (``source_name`` /
    ``adapter_type``), lifecycle, health, and configuration via
    ``SourceDefinition``.
"""

from __future__ import annotations

import logging
from typing import Any

from ..config.source_definition import SourceDefinition
from .base_adapter import BaseEventSourceAdapter

logger = logging.getLogger(__name__)


class WhatsAppSourceAdapter(BaseEventSourceAdapter):
    """WO-013 source adapter for the WhatsApp Cloud API inbound webhook source.

    Constructor dependencies:
        definition: A ``SourceDefinition`` for this WhatsApp source.  The
            adapter reads adapter-specific settings from ``definition.config``
            and treats ``definition.credentials_ref`` strictly as a reference
            (never a secret value).
        normalizer: Optional ``WhatsAppPayloadNormalizer``.  Reserved for an
            embedding application that wants to normalize payloads at the
            adapter; the ingress owns normalization by default.
    """

    def __init__(
        self,
        definition: SourceDefinition,
        normalizer: Any = None,
    ) -> None:
        super().__init__()
        self._definition = definition
        self._normalizer = normalizer
        self._credentials_ref = definition.credentials_ref

        # Adapter-specific settings (opaque to the config layer).  These are
        # logical, non-secret labels only.
        self._webhook_path: str | None = definition.config.get("webhook_path")
        self._business_account: str | None = definition.config.get("waba")

        logger.info(
            "WhatsAppSourceAdapter '%s' configured (webhook_path=%r, "
            "credentials_ref_present=%s)",
            definition.name,
            self._webhook_path,
            self._credentials_ref is not None,
        )

    # --- Interface: source identity ---

    def source_name(self) -> str:
        """Return the canonical source identifier for this adapter."""
        return "whatsapp"

    # --- Interface: read path ---

    def read_events(self) -> list[dict[str, Any]]:
        """Always return an empty list.

        WO-080: the WhatsApp ingress is synchronous (commit-before-ACK) and
        deliberately buffers nothing.  The canonical path is driven by
        ``AdapterRuntime.submit_raw``, so there is no polled queue to drain.
        Returning ``[]`` keeps the shared ``AdapterRuntime`` polling loop
        harmless and exposes no in-memory ACK boundary.
        """
        return []

    # --- Convenience accessors for tests / health ---

    @property
    def definition(self) -> SourceDefinition:
        """The ``SourceDefinition`` this adapter was built from."""
        return self._definition

    @property
    def webhook_path(self) -> str | None:
        """The configured webhook path label (or None)."""
        return self._webhook_path

    @property
    def adapter_type(self) -> str:
        """Adapter type identifier used for registration."""
        return "whatsapp"

    # --- Builder helper (for registration wiring) ---

    @staticmethod
    def build(definition: SourceDefinition) -> "WhatsAppSourceAdapter":
        """Builder contract: SourceDefinition -> WhatsAppSourceAdapter.

        Used with ``AdapterFactory.register_type("whatsapp", ...)``.  Constructs
        a configured (not started) adapter instance.
        """
        return WhatsAppSourceAdapter(definition=definition)


def make_whatsapp_adapter(definition: SourceDefinition) -> WhatsAppSourceAdapter:
    """Adapter builder compatible with ``AdapterFactory.register_type``.

    Returns a configured, unstarted ``WhatsAppSourceAdapter`` for the given
    source definition.  No transport is injected: the ingress drives the
    canonical path synchronously through ``AdapterRuntime.submit_raw``.
    """
    return WhatsAppSourceAdapter(definition=definition)
