"""WO-027 — Durable post-commit delivery dispatcher.

``DurableDeliveryDispatcher`` is the post-commit delivery engine of the
transactional outbox.  It runs AFTER the canonical event has durably committed,
reads eligible PENDING / stale-IN_FLIGHT delivery records from the outbox
repository, and invokes the registered consumer callable for each.

Delivery contract:
  * AT-LEAST-ONCE — a consumer may be invoked more than once if the process
    crashes after the consumer side effect but before the DELIVERED state is
    durably committed.
  * Effectively-once side effects are the consumer's responsibility, using the
    canonical ``event_id`` as the idempotency key (the consumer persists a
    durable idempotency record keyed on ``event_id``).
  * Independent consumers: each ``consumer_id`` has its own delivery record and
    its own state; failure of one never blocks delivery to another.

State machine (durable): PENDING -> IN_FLIGHT -> DELIVERED | FAILED.
A delivery left IN_FLIGHT beyond the stale lease is reclaimed by
``claim_pending`` and retried, so a crash mid-delivery never permanently loses
an event.
"""

from __future__ import annotations

import logging
from typing import Callable, Dict, List, Optional

from app.event_delivery.outbox_model import DurableDeliveryRecord
from app.event_delivery.outbox_repository import SQLAlchemyOutboxRepository

logger = logging.getLogger(__name__)


class DurableDeliveryDispatcher:
    """Deliver committed canonical events to durable consumers post-commit."""

    def __init__(
        self,
        outbox_repository: Optional[SQLAlchemyOutboxRepository] = None,
    ) -> None:
        self._outbox = outbox_repository or SQLAlchemyOutboxRepository()
        # consumer_id -> callable(event) that performs the durable side effect.
        self._consumers: Dict[str, Callable[[object], None]] = {}

    @property
    def outbox(self) -> SQLAlchemyOutboxRepository:
        return self._outbox

    def register_consumer(self, consumer_id: str, callback: Callable[[object], None]) -> None:
        """Register the delivery callable for ``consumer_id``.

        The callback is invoked with the canonical Event.  It must perform its
        durable side effect idempotently with respect to ``event.event_id``.
        """
        self._consumers[consumer_id] = callback

    def unregister_consumer(self, consumer_id: str) -> bool:
        """Remove a registered consumer.  Returns True if it was present."""
        return self._consumers.pop(consumer_id, None) is not None

    def has_consumer(self, consumer_id: str) -> bool:
        return consumer_id in self._consumers

    def consumer_ids(self) -> List[str]:
        return list(self._consumers.keys())

    def enqueue(self, event_id: str, consumer_ids: List[str]) -> int:
        """Create PENDING delivery records (idempotent)."""
        return self._outbox.enqueue_many(event_id, consumer_ids)

    def deliver_pending(
        self,
        limit: int = 100,
        *,
        consumer_ids: Optional[List[str]] = None,
    ) -> int:
        """Deliver all eligible pending/stale deliveries for registered consumers.

        For each claimed record whose consumer is registered, invoke the
        consumer callable, then durably mark the record DELIVERED on success or
        FAILED on failure (so it remains retryable).  Records whose consumer is
        not (yet) registered are transitioned back to PENDING so they are not
        lost and can be delivered once the consumer registers.

        Returns the number of records processed (successful or failed).
        """
        claimed = self._outbox.claim_pending(limit, consumer_ids=consumer_ids)
        processed = 0
        for record in claimed:
            callback = self._consumers.get(record.consumer_id)
            if callback is None:
                # Consumer not registered yet: put back to PENDING so the
                # record is not lost and can be delivered later.
                self._requeue(record)
                continue
            try:
                callback(record)
            except Exception:  # noqa: BLE001 - consumer failure is recorded, not fatal
                logger.exception(
                    "delivery failed for event_id=%s consumer=%s",
                    record.event_id,
                    record.consumer_id,
                )
                self._outbox.mark_failed(
                    record.event_id, record.consumer_id, "consumer raised"
                )
            else:
                self._outbox.mark_delivered(record.event_id, record.consumer_id)
            processed += 1
        return processed

    def _requeue(self, record: DurableDeliveryRecord) -> None:
        """Return an unregistered-consumer record to PENDING (not lost)."""
        self._outbox.mark_pending(record.event_id, record.consumer_id)
