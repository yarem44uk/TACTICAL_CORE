"""WO-014-024 — Canonical Entity Read-Side + Projection Observability.

Public exports for the thin canonical read-side facade over EntityManager and
the projection health signal.
"""

from __future__ import annotations

from .entity_read_service import EntityReadService
from .projection_observability import ProjectionObservability

__all__ = [
    "EntityReadService",
    "ProjectionObservability",
]
