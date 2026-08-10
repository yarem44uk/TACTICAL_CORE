"""
TACTICAL CORE — Signal Adapter Payload Normalizer
WO-013-005

Adapter-local helper that normalizes raw Signal payloads into raw
dictionaries compatible with the canonical EventFactory.

This is an INDEPENDENT implementation. It reuses the field SEMANTICS of
the legacy Signal connector (message_id, sender, chat_id, timestamp,
message_text, attachments) but does NOT import or depend on
`app.connectors.signal`. It never touches EventBus, the API layer, the
database, or the event pipeline.

The normalized raw dict is shaped for `EventFactory.create_event`:

    timestamp      -> Event.timestamp        (normalized to UTC by factory)
    correlation_id -> Event.metadata.correlation_id
    all other keys -> Event.payload
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Field names that the EventFactory recognizes as timestamp keys and moves
# into metadata. Kept local to this helper for clarity.
_TIMESTAMP_KEYS = ("timestamp", "time", "datetime", "date", "ts", "created_at")


class SignalParseError(Exception):
    """Raised when a Signal payload cannot be normalized.

    A single malformed message raising this error is isolated and dropped
    by the adapter's read path without killing the adapter runtime.
    """


class SignalPayloadNormalizer:
    """Normalizes raw Signal payloads into EventFactory-compatible dicts.

    This mirrors the field semantics of the legacy Signal connector while
    remaining fully independent of it (no cross-import).
    """

    def __init__(self) -> None:
        self._required_fields = ("message_id", "sender", "chat_id")

    def normalize(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Normalize a single raw Signal payload into a raw event dict.

        Args:
            payload: Raw Signal message payload (dict).

        Returns:
            A raw dict suitable for `EventFactory.create_event`. The dict
            carries a recognized timestamp key plus the message fields.

        Raises:
            SignalParseError: If the payload is empty or lacks required
                fields. The caller isolates this error per-message.
        """
        if not isinstance(payload, dict) or not payload:
            raise SignalParseError("Signal payload is empty or not a dict")

        missing = [f for f in self._required_fields if payload.get(f) is None]
        if missing:
            raise SignalParseError(
                f"Signal payload missing required fields: {missing}"
            )

        # Normalize attachments (list of dicts) into EventFactory-friendly
        # dicts. Non-dict attachment entries are dropped defensively.
        attachments = self._normalize_attachments(payload.get("attachments"))

        # Build the raw event dict. The timestamp key is preserved so the
        # EventFactory normalizes it to a UTC datetime and moves it to
        # metadata; all other fields land in Event.payload.
        raw: dict[str, Any] = {
            "message_id": str(payload["message_id"]),
            "sender": str(payload["sender"]),
            "chat_id": str(payload["chat_id"]),
            "message_text": str(
                payload.get("message_text", payload.get("body", ""))
            ),
        }

        if attachments:
            raw["attachments"] = attachments

        # Preserve timestamp through the factory-recognized keys.
        if "timestamp" in payload:
            raw["timestamp"] = payload["timestamp"]
        else:
            # Fall back to any other factory-recognized timestamp key.
            for key in _TIMESTAMP_KEYS:
                if key in payload:
                    raw[key] = payload[key]
                    break

        # Preserve an optional correlation identifier for EventMetadata.
        if "correlation_id" in payload and payload["correlation_id"] is not None:
            raw["correlation_id"] = payload["correlation_id"]

        return raw

    @staticmethod
    def _normalize_attachments(
        attachments: Any,
    ) -> list[dict[str, Any]]:
        """Normalize an attachment list into list[dict].

        Accepts a list of dicts (or dict-like objects with keys
        content_type/contentType, filename, size, url). Non-dict or invalid
        entries are skipped.
        """
        if not isinstance(attachments, list):
            return []

        result: list[dict[str, Any]] = []
        for att in attachments:
            if not isinstance(att, dict):
                continue
            content_type = att.get(
                "content_type", att.get("contentType")
            )
            result.append(
                {
                    "content_type": (
                        content_type if content_type is not None
                        else "application/octet-stream"
                    ),
                    "filename": att.get("filename"),
                    "size": att.get("size"),
                    "url": att.get("url"),
                }
            )
        return result

    def normalize_batch(self, payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Normalize a batch of payloads, isolating malformed ones.

        Returns only the successfully normalized raw dicts. Malformed
        payloads are logged and skipped so a single bad message cannot
        break the batch/read path.
        """
        raw_events: list[dict[str, Any]] = []
        for idx, payload in enumerate(payloads):
            try:
                raw_events.append(self.normalize(payload))
            except SignalParseError as exc:
                logger.warning("Signal payload %d dropped: %s", idx, exc)
        return raw_events
