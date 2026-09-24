"""WO-080 — WhatsApp ingress service (transport boundary -> canonical path).

The service is the ONLY place where an inbound webhook payload becomes a
canonical event.  It is a PRODUCER/TRANSPORT boundary: it normalizes the
webhook and drives the EXISTING canonical path through
``AdapterRuntime.submit_raw``.  It never constructs a canonical Event, never
touches ``EventFactory`` / ``EventPipeline`` / a repository directly, and never
implements a second event architecture (ADR-015 §5, WO-079 §11).

ACK / durability contract (ADR-015 §7, WO-080 §22-§24):

    HTTP 200            <- every inbound message durable (NEW or DUPLICATE)
    HTTP 400            <- authentic but unusable payload (nothing durable)
    HTTP 503            <- durable persistence NOT confirmed (Meta may retry)

``IngestResult.durable`` is the single source of truth for "may I ACK": the
service NEVER acknowledges a message whose durable persistence was not
positively confirmed.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional, Tuple

from app.event_sources.adapters.whatsapp_parser import (
    WhatsAppParseError,
    WhatsAppPayloadNormalizer,
)
from app.event_sources.runtime.adapter_runtime import IngestStatus

logger = logging.getLogger(__name__)

# HTTP outcome codes.
HTTP_OK = 200
HTTP_BAD_REQUEST = 400
HTTP_SERVICE_UNAVAILABLE = 503


@dataclass(frozen=True)
class IngressOutcome:
    """The result of handling one webhook payload (HTTP-facing).

    Attributes:
        status_code: 200 (durable), 400 (unusable), or 503 (not durably confirmed).
        event_ids: Canonical event ids durably materialized (or confirmed
            already durable) by this request.  Empty when nothing was inbound.
        duplicate: True when at least one message was an already-durable
            duplicate (all such messages are collapsed, never re-created).
        error: Non-secret error text for non-200 outcomes.
    """

    status_code: int
    event_ids: Tuple[str, ...] = ()
    duplicate: bool = False
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.status_code == HTTP_OK


class WhatsAppIngressService:
    """Handles a normalized-or-raw WhatsApp webhook against the canonical path.

    Args:
        adapter_runtime: The PRODUCTION ``AdapterRuntime`` for the ``whatsapp``
            source (built by the ingress composition; obtained from the
            production supervisor, never hand-built).  It MUST have a
            durability probe configured, otherwise commit-before-ACK cannot be
            honoured and every message would be reported unconfirmed.
        normalizer: Optional ``WhatsAppPayloadNormalizer`` (defaults to a
            shared instance).
    """

    def __init__(
        self,
        adapter_runtime: Any,
        normalizer: Optional[WhatsAppPayloadNormalizer] = None,
    ) -> None:
        self._runtime = adapter_runtime
        self._normalizer = normalizer or WhatsAppPayloadNormalizer()

    @property
    def runtime(self) -> Any:
        return self._runtime

    def handle_webhook(self, payload: dict[str, Any]) -> IngressOutcome:
        """Normalize a webhook payload and ingest every inbound message.

        Order of operations (commit-before-ACK):

            1. normalize the webhook -> one raw dict per message;
            2. per message: submit synchronously through the canonical path;
            3. ACK 200 ONLY when every message's durability is confirmed.

        A failure at any message fails the whole request (5xx), so Meta retries
        the batch; already-durable messages in the batch are idempotent no-ops
        on retry (deterministic identity + UNIQUE(event_id)).
        """
        try:
            raw_events = self._normalizer.normalize_webhook(payload)
        except WhatsAppParseError as exc:
            logger.info("whatsapp ingress rejected payload: %s", exc)
            return IngressOutcome(
                status_code=HTTP_BAD_REQUEST, error=str(exc)
            )

        if not raw_events:
            # Authentic webhook with no inbound message (e.g. statuses-only):
            # nothing to persist.  Acknowledge so Meta does not retry, and do
            # NOT fabricate a canonical event.
            return IngressOutcome(status_code=HTTP_OK)

        event_ids: list[str] = []
        duplicate = False

        for raw in raw_events:
            result = self._runtime.submit_raw(raw)
            status = getattr(result, "status", None)
            durable = bool(getattr(result, "durable", False))
            error = getattr(result, "error", None)

            if status == IngestStatus.INVALID:
                logger.info(
                    "whatsapp ingress invalid message: %s", error
                )
                return IngressOutcome(
                    status_code=HTTP_BAD_REQUEST,
                    error=error or "invalid WhatsApp message",
                )

            if status == IngestStatus.FAILURE or not durable:
                # Durable persistence was NOT confirmed: never acknowledge.
                logger.warning(
                    "whatsapp ingress durability not confirmed (status=%s): %s",
                    status,
                    error,
                )
                return IngressOutcome(
                    status_code=HTTP_SERVICE_UNAVAILABLE,
                    error=error or "durable persistence not confirmed",
                )

            if status == IngestStatus.DUPLICATE:
                duplicate = True
            event_id = getattr(result, "event_id", None)
            if event_id is not None:
                event_ids.append(event_id)

        return IngressOutcome(
            status_code=HTTP_OK,
            event_ids=tuple(event_ids),
            duplicate=duplicate,
        )

    def health(self) -> dict[str, Any]:
        """Read-only ingress health (never mutates lifecycle)."""
        try:
            return self._runtime.health()
        except Exception as exc:  # noqa: BLE001 - health must never raise
            return {"healthy": False, "error": str(exc)}
