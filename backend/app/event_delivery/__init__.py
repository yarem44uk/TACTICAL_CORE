"""WO-027 — Durable post-commit event delivery (transactional outbox).

This package implements the canonical durable delivery boundary for the
TACTICAL_CORE event pipeline.  The authoritative event log
(``durable_canonical_events``) remains the source of truth; a durable
outbox (``durable_event_delivery``) records, transactionally with the event
commit, which consumers must receive each canonical event.  Delivery happens
strictly AFTER the canonical event has durably committed.

Invariants:
  * No consumer side effect may execute before the canonical event commit.
  * Delivery is AT-LEAST-ONCE; exactly-once transport is never claimed.
  * Consumers achieve effectively-once side effects only where they persist
    a durable idempotency record keyed on the canonical ``event_id``.
  * A single ``DatabaseSessionManager`` remains the ONLY database owner.
"""

from app.event_delivery.delivery_dispatcher import DurableDeliveryDispatcher
from app.event_delivery.outbox_repository import SQLAlchemyOutboxRepository

__all__ = [
    "DurableDeliveryDispatcher",
    "SQLAlchemyOutboxRepository",
]
