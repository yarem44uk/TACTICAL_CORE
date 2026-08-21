"""WO-025 — Canonical event identity resolution.

Deterministic, source-aware canonical event identity for end-to-end
idempotency.

Rationale (WO-025 PHASE 1 forensic audit):
  The canonical durable persistence layer already guarantees
  ``UNIQUE(event_id)`` and idempotent duplicate persistence, and
  ``Event.to_dict()/from_dict()`` preserve ``event_id`` exactly.  The
  confirmed architectural gap was at ingestion: ``Event.event_id`` defaulted
  to a fresh random ``str(uuid4())`` per ``EventFactory.create_event()`` call,
  so two deliveries of the same logical source message produced two different
  ``event_id`` values and the database constraint could not deduplicate them.

WO-025 architecture decision (approved):
  1. PRIMARY IDENTITY  — prefer a stable source-provided identity.
  2. DETERMINISTIC FALLBACK — when a source has no native identity, derive a
     deterministic identity from an explicitly documented identity key that
     excludes unstable / non-identity fields (never hash the whole payload).
  3. EXPLICIT NON-DEDUPLICABLE — unknown/undocumented sources keep a fresh
     UUID4 (non-deduplicable).

Identity representation:
  ``event_id`` is emitted as a deterministic ``uuid.UUID5`` string (36 chars),
  which fits the authoritative ``DurableCanonicalEvent.event_id String(36)``
  column exactly.  No schema change is required.
"""

from __future__ import annotations

import json
from typing import Any, Optional
from uuid import NAMESPACE_URL, uuid5

# Namespace so UUID5 values are stable and domain-scoped to TACTICAL_CORE.
_EVENT_NAMESPACE = uuid5(NAMESPACE_URL, "https://tacticalcore.dev/event")


def _canonicalize(value: Any) -> str:
    """Deterministic string form of an identity-material value.

    Dicts are canonicalized with sorted keys so equivalent payloads (different
    insertion order) yield the same string.  Non-JSON-serializable values
    (e.g. bytes) fall back to ``str``.
    """
    try:
        return json.dumps(value, sort_keys=True, default=str, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(value)


def _native(raw: dict[str, Any], *keys: str) -> Optional[str]:
    """Join the first present, non-None, non-empty of ``keys`` from raw."""
    parts: list[str] = []
    for key in keys:
        value = raw.get(key)
        if value is None:
            return None
        s = _canonicalize(value)
        if not s:
            return None
        parts.append(s)
    return "|".join(parts)


# --- Per-source identity material policies --------------------------------
#
# Each policy returns the canonical identity-material string, or None when the
# source is non-deduplicable (fall back to UUID4 in Event).


def _atak_identity(raw: dict[str, Any]) -> Optional[str]:
    # CoT `uid` is the authoritative unique event identifier (required by the
    # ATAK parser), stable across retries/restarts.
    uid = raw.get("uid")
    if uid is None:
        return None
    return f"atak|{_canonicalize(uid)}"


def _telegram_identity(raw: dict[str, Any]) -> Optional[str]:
    # Telegram `message_id` is unique per chat and monotonic; `chat_id`
    # scopes it.  Both are required by the Telegram parser.
    return _native(raw, "chat_id", "message_id")


def _signal_identity(raw: dict[str, Any]) -> Optional[str]:
    # Signal `message_id` is the source message id (required by the Signal
    # parser); `chat_id` scopes it.
    return _native(raw, "chat_id", "message_id")


def _mqtt_identity(raw: dict[str, Any]) -> Optional[str]:
    # MQTT has no retained native message id in the normalized dict, so use a
    # deterministic fallback over the explicit identity key `topic + payload`.
    # qos / retain / client_id / timestamp are transport metadata and are
    # excluded (they do not identify the logical message).
    topic = raw.get("topic")
    if topic is None:
        return None
    return f"mqtt|{_canonicalize(topic)}|{_canonicalize(raw.get('payload'))}"


def _radio_identity(raw: dict[str, Any]) -> Optional[str]:
    # Radio has no native message id.  Deterministic fallback over the explicit
    # identity key `frequency + callsign`.  signal_strength / modulation /
    # source / timestamp are reception/transport metadata and are excluded.
    frequency = raw.get("frequency")
    callsign = raw.get("callsign")
    if frequency is None or callsign is None:
        return None
    return f"radio|{_canonicalize(frequency)}|{_canonicalize(callsign)}"


# Mapping: adapter source_name -> identity-material policy.
_IDENTITY_POLICIES: dict[str, Any] = {
    "atak": _atak_identity,
    "telegram": _telegram_identity,
    "signal": _signal_identity,
    "mqtt": _mqtt_identity,
    "radio": _radio_identity,
}


class EventIdentityResolver:
    """Resolves a deterministic canonical ``event_id`` for a raw source message.

    The resolver is a pure function of ``(raw_data, source_name)``.  It is
    stateless, thread-safe, and introduces no database owner, cache, or
    persistence.
    """

    def resolve(self, raw_data: dict[str, Any], source_name: str) -> Optional[str]:
        """Return the deterministic canonical ``event_id`` for the message.

        Args:
            raw_data: The raw source event dict (as produced by an adapter
                normalizer).
            source_name: The source adapter name (e.g. ``"atak"``).

        Returns:
            A deterministic UUID5 string (36 chars), or None when the source is
            non-deduplicable (caller falls back to ``Event.event_id`` UUID4).
        """
        if not isinstance(raw_data, dict):
            return None

        policy = _IDENTITY_POLICIES.get(source_name)
        if policy is None:
            # Unknown / undocumented source -> non-deduplicable.
            return None

        material = policy(raw_data)
        if material is None:
            return None

        return str(uuid5(_EVENT_NAMESPACE, material))


def resolve_event_identity(
    raw_data: dict[str, Any], source_name: str
) -> Optional[str]:
    """Module-level convenience for the deterministic identity resolution."""
    return EventIdentityResolver().resolve(raw_data, source_name)
