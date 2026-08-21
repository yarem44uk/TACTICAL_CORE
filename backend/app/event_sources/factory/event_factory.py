"""
TACTICAL CORE — Event Factory
WO-013-001 (updated WO-013-002)

Converts raw source data into canonical Event objects compatible with
the WO-012 Event Processing Layer.

After WO-013-002: returns real Event instances instead of dictionaries.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.event.event import Event
from app.event.event_metadata import EventMetadata
from app.event.event_types import EventType

from ..identity.event_identity import EventIdentityResolver
from ..interfaces.i_event_factory import IEventFactory


class EventFactory(IEventFactory):
    """Factory for creating canonical Event objects from raw source data.

    Responsibilities:
    - Normalize timestamps to UTC
    - Attach source identification
    - Preserve protocol-specific metadata without leaking structure
    - Resolve a deterministic canonical ``event_id`` (WO-025) when an identity
      resolver is configured and a stable identity can be derived
    - Return immutable Event instances (frozen dataclass)

    The resulting Event is fully compatible with WO-012 Event Processing Layer,
    Event Pipeline, Event Filter, Event Dispatcher, and Event Repository.
    """

    def __init__(self, identity_resolver: EventIdentityResolver | None = None):
        """Create an EventFactory.

        Args:
            identity_resolver: Optional WO-025 identity resolver.  When set, a
                deterministic canonical ``event_id`` is derived from the raw
                source message and source name so duplicate deliveries of the
                same logical message map to the same durable identity.  When
                ``None`` (default), ``Event.event_id``'s UUID4 default is used
                (full backward compatibility; non-deduplicable).
        """
        self._identity_resolver = identity_resolver

    def create_event(
        self,
        raw_data: dict[str, Any],
        source_name: str,
        event_type: EventType | None = None,
        metadata: dict[str, Any] | None = None,
        event_id: str | None = None,
    ) -> Event:
        """Create a canonical Event from raw source data.

        Args:
            raw_data: Protocol-specific raw event from the adapter.
            source_name: Name of the source adapter.
            event_type: Explicit event type. Falls back to EventType.CUSTOM.
            metadata: Optional additional metadata.
            event_id: Explicit canonical event identity. When provided it takes
                precedence. Otherwise a deterministic identity is resolved via
                the configured resolver (WO-025); if neither yields an identity,
                ``Event.event_id``'s UUID4 default is used.

        Returns:
            A canonical Event instance compatible with WO-012.

        Raises:
            ValueError: If source_name is empty.
            TypeError: If raw_data is not a dict.
        """
        self._validate_inputs(raw_data, source_name)

        timestamp = self._normalize_timestamp(raw_data)
        event_data = self._extract_data(raw_data)
        event_metadata = self._build_metadata(raw_data, source_name, metadata)

        if event_type is None:
            event_type = EventType.CUSTOM

        resolved_event_id = event_id
        if resolved_event_id is None and self._identity_resolver is not None:
            resolved_event_id = self._identity_resolver.resolve(
                raw_data, source_name
            )

        if resolved_event_id is not None:
            return Event(
                event_id=resolved_event_id,
                event_type=event_type,
                timestamp=timestamp,
                source=source_name,
                payload=event_data,
                metadata=event_metadata,
            )

        # No explicit / resolved identity: rely on Event.event_id's UUID4
        # default (non-deduplicable).
        return Event(
            event_type=event_type,
            timestamp=timestamp,
            source=source_name,
            payload=event_data,
            metadata=event_metadata,
        )

    @staticmethod
    def _validate_inputs(raw_data: dict[str, Any], source_name: str) -> None:
        """Validate factory inputs."""
        if not isinstance(raw_data, dict):
            raise TypeError(
                f"raw_data must be a dict, got {type(raw_data).__name__}"
            )
        if not source_name or not isinstance(source_name, str) or not source_name.strip():
            raise ValueError("source_name must be a non-empty string")

    @staticmethod
    def _normalize_timestamp(raw_data: dict[str, Any]) -> datetime:
        """Normalize timestamp to UTC datetime.

        Tries common timestamp keys, falls back to now().
        """
        for key in ("timestamp", "time", "datetime", "date", "ts", "created_at"):
            if key in raw_data:
                value = raw_data[key]
                if isinstance(value, datetime):
                    return value.astimezone(timezone.utc)
                if isinstance(value, (int, float)):
                    return datetime.fromtimestamp(value, tz=timezone.utc)
                if isinstance(value, str):
                    try:
                        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
                        return dt.astimezone(timezone.utc)
                    except ValueError:
                        pass
        return datetime.now(timezone.utc)

    @staticmethod
    def _extract_data(raw_data: dict[str, Any]) -> dict[str, Any]:
        """Extract event payload, removing known protocol metadata.

        Protocol-specific fields are moved to metadata, not leaked into payload.
        """
        protocol_keys = {"timestamp", "time", "datetime", "date", "ts", "created_at"}
        return {k: v for k, v in raw_data.items() if k not in protocol_keys}

    @staticmethod
    def _build_metadata(
        raw_data: dict[str, Any],
        source_name: str,
        extra_metadata: dict[str, Any] | None,
    ) -> EventMetadata:
        """Build EventMetadata from source data."""
        protocol_keys = {"timestamp", "time", "datetime", "date", "ts", "created_at"}
        properties: dict[str, Any] = {
            k: v for k, v in raw_data.items() if k in protocol_keys
        }
        properties["source_name"] = source_name

        if extra_metadata:
            properties.update(extra_metadata)

        correlation_id = raw_data.get("correlation_id")

        return EventMetadata(
            tags=[],
            properties=properties,
            correlation_id=correlation_id,
        )
