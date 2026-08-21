"""WO-025 — Canonical event identity resolution.

Deterministic, source-aware canonical event identity for end-to-end
idempotency (duplicate delivery of the same logical source message maps to
the same durable ``event_id``, so the database UNIQUE(event_id) constraint
deduplicates it).

The resolver is a pure, side-effect-free function of ``(raw_data,
source_name)``.  It introduces no second database owner, no global state,
no cache, and no persistence.
"""

from .event_identity import EventIdentityResolver, resolve_event_identity

__all__ = [
    "EventIdentityResolver",
    "resolve_event_identity",
]
