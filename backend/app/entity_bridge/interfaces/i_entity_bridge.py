"""
IEntityBridge Interface.

Contract that EntityBridge implements.  Allows test doubles (mocks,
stubs) to stand in for the real bridge during unit tests of upstream
consumers (e.g. PersistenceStage).

Author: Tactical Core Engineering Team
Version: 1.0
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict


class IEntityBridge(ABC):
    """
    Bridge between the event pipeline and the entity management layer.

    Receives pipeline events, translates them into structured
    :class:`EntityUpdateRequest` objects, and delegates to
    :class:`IEntityManager`.
    """

    @abstractmethod
    def process_event(
        self,
        event_data: Dict[str, Any],
        event_id: str | int | None = None,
        correlation_id: str | None = None,
    ) -> None:
        """
        Translate a raw pipeline event into entity updates.

        This is a *best-effort* operation: exceptions are logged
        internally and **never** propagated to the caller.  A failed
        bridge call must NOT interrupt the pipeline.

        Args:
            event_data: Parsed event payload from the pipeline.
            event_id: Optional pipeline event identifier.
            correlation_id: Optional correlation ID for tracing.
        """
        ...
