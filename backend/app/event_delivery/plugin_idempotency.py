"""WO-029 — Durable plugin-delivery idempotency boundary.

The plugin delivery path provides AT-LEAST-ONCE delivery: after a plugin side
effect, a process crash (stale IN_FLIGHT reclaim) can cause the same event to
be redelivered.  To let plugin consumers suppress a duplicate *durable* side
effect, this module provides a durable idempotency ledger keyed on the
canonical identity ``(event_id, plugin_id)``.

Guarantees:

  * ``UNIQUE(event_id, plugin_id)`` is DB-enforced — exactly one durable
    idempotency record per event/plugin pair, so a redelivery can never create
    a second durable idempotency record.
  * The ledger is written AFTER the plugin's side effect succeeds, and is
    checked BEFORE invoking the plugin, so an idempotency-capable consumer is
    not re-executed once its durable record exists.
  * AT-LEAST-ONCE is preserved: if the process crashes before the ledger write
    (after the side effect), redelivery re-runs the plugin — the arbitrary
    external plugin side effect is NOT atomically bounded by this ledger.  This
    distinction is explicit: the ledger provides a durable idempotency boundary
    for the delivery record, not atomic exactly-once external side effects.

Ownership: single ``DatabaseSessionManager`` (no second engine/sessionmaker/
database owner).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class DurablePluginDelivery(Base):
    """One durable idempotency record per (event_id, plugin_id)."""

    __tablename__ = "durable_plugin_delivery"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: uuid.uuid4().hex
    )
    event_id: Mapped[str] = mapped_column(String(36), nullable=False)
    plugin_id: Mapped[str] = mapped_column(String(100), nullable=False)
    delivered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        # Canonical plugin idempotency boundary: exactly one durable record per
        # event/plugin pair (prevents duplicate durable idempotency records).
        UniqueConstraint(
            "event_id", "plugin_id", name="uq_durable_plugin_delivery_event_plugin"
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return (
            f"<DurablePluginDelivery(event_id={self.event_id!r}, "
            f"plugin_id={self.plugin_id!r})>"
        )
