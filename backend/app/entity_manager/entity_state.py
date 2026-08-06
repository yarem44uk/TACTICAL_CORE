from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict


class EntityState(Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    DELETED = "deleted"


@dataclass
class EntityStateInfo:
    """Tracks entity lifecycle state and history."""

    state: EntityState = EntityState.ACTIVE
    last_modified: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    modified_by: str | None = None
    history: list[Dict[str, Any]] = field(default_factory=list)
