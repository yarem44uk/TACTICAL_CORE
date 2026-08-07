from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable

import threading
import uuid

if TYPE_CHECKING:
    from backend.app.event.event_types import EventType

__all__ = ["Subscription"]


@dataclass(frozen=True)
class Subscription:
    """Immutable handle for a single subscription."""
    event_type: "EventType"
    callback: Callable[[object], None]
    id: str
