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

State machine (durable): PENDING -> IN_FLIGHT -> DELIVERED | FAILED.  A
FAILED delivery is retried with deterministic backoff (WO-029) and retired to
DEAD_LETTER once ``max_attempts`` is exceeded; DEAD_LETTER is terminal unless
explicitly requeued.  A delivery left IN_FLIGHT beyond the stale lease is
reclaimed by ``claim_pending`` and retried, so a crash mid-delivery never
permanently loses an event.

ORDERING CONTRACT (WO-029)
--------------------------
Delivery ordering is guaranteed ONLY within a single dispatcher for a given
consumer: ``claim_pending`` orders eligible records by ``created_at`` and a
single dispatcher processes them sequentially, so one consumer observes its
deliveries in enqueue order.  Global ordering across multiple independent
dispatcher processes is NOT guaranteed (each dispatcher claims independently);
the durable canonical ``seq`` remains the authoritative event order for
replay/projection.  No distributed ordering protocol is implemented.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

from app.event_delivery.outbox_model import DurableDeliveryRecord
from app.event_delivery.outbox_repository import SQLAlchemyOutboxRepository

logger = logging.getLogger(__name__)


class DurableDeliveryDispatcher:
    """Deliver committed canonical events to durable consumers post-commit."""

    def __init__(
        self,
        outbox_repository: Optional[SQLAlchemyOutboxRepository] = None,
        *,
        event_repository: Optional[Any] = None,
        max_attempts: int = 5,
        backoff_base_seconds: float = 2.0,
        stale_lease_seconds: int = 60,
    ) -> None:
        self._outbox = outbox_repository or SQLAlchemyOutboxRepository(
            max_attempts=max_attempts,
            backoff_base_seconds=backoff_base_seconds,
            stale_lease_seconds=stale_lease_seconds,
        )
        # Ensure the retry policy applies even when an outbox_repository was
        # injected (WO-029: the dispatcher is the single owner of the delivery
        # policy regardless of how the repository was provided).
        self._outbox.set_retry_policy(
            max_attempts=max_attempts,
            backoff_base_seconds=backoff_base_seconds,
            stale_lease_seconds=stale_lease_seconds,
        )
        # WO-031 — durable canonical event repository used to reconstruct the
        # canonical app.event.Event from record.event_id before invoking a
        # consumer.  When None (lightweight/test-only dispatcher), the consumer
        # callback is invoked with the DurableDeliveryRecord as before.
        self._event_repository = event_repository
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
            if self._event_repository is not None:
                # WO-031 — reconstruct the canonical Event from the durable
                # store by record.event_id.  The DurableDeliveryRecord is
                # delivery metadata only; consumers require a canonical
                # app.event.Event.
                try:
                    event = self._event_repository.get(record.event_id)
                except Exception:  # noqa: BLE001 - a repository read failure is
                    # recorded, not fatal; WO-029 retry/DEAD_LETTER owns it.
                    logger.exception(
                        "event lookup failed for event_id=%s consumer=%s",
                        record.event_id,
                        record.consumer_id,
                    )
                    self._outbox.mark_failed(
                        record.event_id, record.consumer_id, "event lookup failed"
                    )
                    processed += 1
                    continue
                if event is None:
                    # The canonical event is missing: do NOT mark successful,
                    # do NOT pass None to a consumer.  Mark FAILED so the
                    # existing WO-029 retry / DEAD_LETTER mechanism operates.
                    self._outbox.mark_failed(
                        record.event_id, record.consumer_id, "canonical event not found"
                    )
                    processed += 1
                    continue
                target = event
            else:
                # No event repository injected (lightweight/test-only
                # dispatcher): preserve the legacy record-based callback.
                target = record
            try:
                callback(target)
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
