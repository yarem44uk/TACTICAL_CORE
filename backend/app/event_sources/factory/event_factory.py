"""
TACTICAL CORE — Event Factory
WO-013-001

Converts raw source data into canonical Event structures compatible with
the WO-012 Event Processing Layer.
"""

import uuid
from datetime import datetime, timezone
from typing import Any

from ..interfaces.i_event_factory import IEventFactory


class EventFactory(IEventFactory):
    """Factory for creating canonical events from raw source data.

    Responsibilities:
    - Normalize timestamps to UTC ISO-8601
    - Attach source identification
    - Preserve protocol-specific metadata without leaking structure
    - Generate unique correlation IDs

    The resulting event dict is compatible with WO-012 Event Processing Layer.
    """

    def create_event(
        self,
        raw_data: dict[str, Any],
        source_name: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a canonical event from raw source data.

        Args:
            raw_data: Protocol-specific raw event from the adapter.
            source_name: Name of the source adapter.
            metadata: Optional additional metadata.

        Returns:
            Canonical event dictionary with:
            - id: unique event identifier
            - source: source adapter name
            - timestamp: UTC ISO-8601 string
            - data: normalized event payload
            - metadata: merged source + user metadata
        """
        timestamp = self._normalize_timestamp(raw_data)
        event_id = str(uuid.uuid4())

        event_data = self._extract_data(raw_data)
        event_metadata = self._build_metadata(raw_data, source_name, metadata)

        return {
            "id": event_id,
            "source": source_name,
            "timestamp": timestamp,
            "data": event_data,
            "metadata": event_metadata,
        }

    @staticmethod
    def _normalize_timestamp(raw_data: dict[str, Any]) -> str:
        """Normalize timestamp to UTC ISO-8601.

        Tries common timestamp keys, falls back to now().
        """
        for key in ("timestamp", "time", "datetime", "date", "ts", "created_at"):
            if key in raw_data:
                value = raw_data[key]
                if isinstance(value, datetime):
                    return value.astimezone(timezone.utc).isoformat()
                if isinstance(value, (int, float)):
                    return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()
                if isinstance(value, str):
                    try:
                        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
                        return dt.astimezone(timezone.utc).isoformat()
                    except ValueError:
                        pass
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _extract_data(raw_data: dict[str, Any]) -> dict[str, Any]:
        """Extract event payload, removing known protocol metadata.

        Protocol-specific fields are moved to metadata, not leaked into data.
        """
        protocol_keys = {"timestamp", "time", "datetime", "date", "ts", "created_at"}
        return {k: v for k, v in raw_data.items() if k not in protocol_keys}

    @staticmethod
    def _build_metadata(
        raw_data: dict[str, Any],
        source_name: str,
        extra_metadata: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Build merged metadata dict."""
        protocol_keys = {"timestamp", "time", "datetime", "date", "ts", "created_at"}
        protocol_metadata = {k: v for k, v in raw_data.items() if k in protocol_keys}
        protocol_metadata["source_name"] = source_name

        if extra_metadata:
            protocol_metadata.update(extra_metadata)

        return protocol_metadata
