"""WO-083 — Telegram ingress service (transport boundary -> canonical path).

The service is the ONLY place where an inbound Telegram ``Update`` becomes a
canonical event.  It is a PRODUCER/TRANSPORT boundary: it normalizes the Update
envelope and drives the EXISTING canonical path through
``AdapterRuntime.submit_raw``.  It never constructs a canonical Event, never
touches ``EventFactory`` / ``EventPipeline`` / a repository directly, and never
implements a second event architecture (WO-083 §15-§16).

ACK / durability contract (WO-083 §20-§21):

    HTTP 200            <- the inbound message is durable (NEW or DUPLICATE)
    HTTP 400            <- authentic but unusable / unsupported payload
                           (nothing durable)
    HTTP 503            <- durable persistence NOT confirmed (Telegram retries)

``IngestResult.durable`` is the single source of truth for "may I ACK": the
service NEVER acknowledges a message whose durable persistence was not
positively confirmed.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional, Tuple

from app.event_sources.runtime.adapter_runtime import IngestStatus

from .normalizer import TelegramUpdateError, TelegramUpdateNormalizer

logger = logging.getLogger(__name__)

# HTTP outcome codes.
HTTP_OK = 200
HTTP_BAD_REQUEST = 400
HTTP_SERVICE_UNAVAILABLE = 503


@dataclass(frozen=True)
class IngressOutcome:
    """The result of handling one Telegram Update (HTTP-facing).

    Attributes:
        status_code: 200 (durable), 400 (unusable), or 503 (not durably
            confirmed).
        event_ids: Canonical event ids durably materialized (or confirmed
            already durable) by this request.  Empty when nothing was inbound.
        duplicate: True when the message was an already-durable duplicate.
        error: Non-secret error text for non-200 outcomes.
    """

    status_code: int
    event_ids: Tuple[str, ...] = ()
    duplicate: bool = False
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.status_code == HTTP_OK


class TelegramIngressService:
    """Handles one Telegram Update against the canonical ingestion path.

    Args:
        adapter_runtime: The PRODUCTION ``AdapterRuntime`` for the ``telegram``
            source (built by the ingress composition; obtained from the
            production supervisor, never hand-built).  It MUST have a durability
            probe configured, otherwise commit-before-ACK cannot be honoured and
            every message would be reported unconfirmed.
        normalizer: Optional ``TelegramUpdateNormalizer`` (defaults to a shared
            instance).
    """

    def __init__(
        self,
        adapter_runtime: Any,
        normalizer: Optional[TelegramUpdateNormalizer] = None,
    ) -> None:
        self._runtime = adapter_runtime
        self._normalizer = normalizer or TelegramUpdateNormalizer()

    @property
    def runtime(self) -> Any:
        return self._runtime

    def handle_update(self, payload: dict[str, Any]) -> IngressOutcome:
        """Normalize one Telegram Update and ingest it (commit-before-ACK).

        Order of operations:

            1. normalize the Update envelope -> one raw dict;
            2. submit synchronously through the canonical path
               (AdapterRuntime -> EventFactory -> EventPipeline -> durable);
            3. ACK 200 ONLY when durability is positively confirmed.
        """
        try:
            raw = self._normalizer.normalize_update(payload)
        except TelegramUpdateError as exc:
            logger.info("telegram ingress rejected update: %s", exc)
            return IngressOutcome(status_code=HTTP_BAD_REQUEST, error=str(exc))

        result = self._runtime.submit_raw(raw)
        status = getattr(result, "status", None)
        durable = bool(getattr(result, "durable", False))
        error = getattr(result, "error", None)

        if status == IngestStatus.INVALID:
            logger.info("telegram ingress invalid message: %s", error)
            return IngressOutcome(
                status_code=HTTP_BAD_REQUEST,
                error=error or "invalid Telegram message",
            )

        if status == IngestStatus.FAILURE or not durable:
            # Durable persistence was NOT confirmed: never acknowledge.
            logger.warning(
                "telegram ingress durability not confirmed (status=%s): %s",
                status,
                error,
            )
            return IngressOutcome(
                status_code=HTTP_SERVICE_UNAVAILABLE,
                error=error or "durable persistence not confirmed",
            )

        event_id = getattr(result, "event_id", None)
        event_ids: Tuple[str, ...] = ()
        if event_id is not None:
            event_ids = (event_id,)

        return IngressOutcome(
            status_code=HTTP_OK,
            event_ids=event_ids,
            duplicate=status == IngestStatus.DUPLICATE,
        )

    def health(self) -> dict[str, Any]:
        """Read-only ingress health (never mutates lifecycle)."""
        try:
            return self._runtime.health()
        except Exception as exc:  # noqa: BLE001 - health must never raise
            return {"healthy": False, "error": str(exc)}
