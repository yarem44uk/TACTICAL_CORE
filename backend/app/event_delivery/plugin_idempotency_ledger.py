"""WO-029 — Durable plugin-delivery idempotency helper (single DB owner).

``PluginDeliveryLedger`` provides the durable ``(event_id, plugin_id)``
idempotency boundary used by plugin delivery.  It operates exclusively through
the existing ``DatabaseSessionManager`` — no second engine, sessionmaker, or
database owner.

The core operation is ``run_idempotent(event_id, plugin_id, fn)``: it invokes
``fn`` only if no durable idempotency record exists for the pair, and records
the pair durably after ``fn`` succeeds.  On a duplicate call (record present)
``fn`` is not invoked again (the consumer's durable side effect is not
duplicated).  AT-LEAST-ONCE is preserved: a crash between ``fn`` and the
ledger write means the record is absent and the plugin may run again.
"""

from __future__ import annotations

from typing import Callable, Optional, TypeVar

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.database.session import DatabaseSessionManager, get_session_manager
from app.event_delivery.plugin_idempotency import DurablePluginDelivery

_T = TypeVar("_T")


class PluginDeliveryLedger:
    """Durable (event_id, plugin_id) idempotency ledger over the single owner."""

    def __init__(
        self,
        session_manager: Optional[DatabaseSessionManager] = None,
    ) -> None:
        self._session_manager = session_manager

    @property
    def session_manager(self) -> DatabaseSessionManager:
        if self._session_manager is None:
            return get_session_manager()
        return self._session_manager

    def initialize(self) -> None:
        """Ensure the plugin-delivery ledger table exists on the shared owner."""
        from app.database.base import Base

        Base.metadata.create_all(bind=self.session_manager.engine)

    def has_delivered(self, event_id: str, plugin_id: str) -> bool:
        """Return True if a durable idempotency record already exists."""
        with self.session_manager.session(commit=False) as session:
            row = session.execute(
                select(DurablePluginDelivery).where(
                    DurablePluginDelivery.event_id == event_id,
                    DurablePluginDelivery.plugin_id == plugin_id,
                )
            ).scalar_one_or_none()
            return row is not None

    def record_delivery(self, event_id: str, plugin_id: str) -> bool:
        """Durably record that ``plugin_id`` handled ``event_id``.

        Idempotent: returns False if the record already exists (UNIQUE), True
        if a new record was written.  A concurrent duplicate write is a benign
        no-op (exactly one durable record per event/plugin pair).
        """
        try:
            with self.session_manager.session(commit=True) as session:
                session.add(
                    DurablePluginDelivery(event_id=event_id, plugin_id=plugin_id)
                )
        except IntegrityError:  # already recorded (UNIQUE) -> benign no-op
            return False
        return True

    def run_idempotent(
        self,
        event_id: str,
        plugin_id: str,
        fn: Callable[[], _T],
    ) -> tuple[bool, Optional[_T]]:
        """Run ``fn`` at most once per (event_id, plugin_id).

        If a durable idempotency record already exists for the pair, ``fn`` is
        NOT invoked and ``(False, None)`` is returned.  Otherwise ``fn`` is
        invoked, the record is durably written, and ``(True, result)`` is
        returned.

        Note: a process crash between ``fn`` completing and the ledger write
        leaves the record absent, so AT-LEAST-ONCE means ``fn`` may run again —
        this is the documented, unavoidable boundary for arbitrary external
        plugin side effects (not atomically bounded by this ledger).
        """
        if self.has_delivered(event_id, plugin_id):
            return False, None
        result = fn()
        self.record_delivery(event_id, plugin_id)
        return True, result
